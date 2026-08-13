"""Fail-closed inspection for installable Creative Workshop packages."""

from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import struct
import unicodedata
from collections.abc import Iterable
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import (
    ZIP_DEFLATED,
    ZIP_STORED,
    BadZipFile,
    LargeZipFile,
    ZipFile,
    ZipInfo,
)

from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

from .models import InspectedPackage, WorkshopManifest

MAX_PACKAGE_BYTES = 100 * 1024 * 1024
MAX_UNPACKED_BYTES = 300 * 1024 * 1024
MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_FILE_COUNT = 2_000
MAX_COMPRESSION_RATIO = 100.0
MAX_IMAGE_EDGE = 16_384
MAX_MANIFEST_BYTES = 256 * 1024
MAX_ICON_BYTES = 2 * 1024 * 1024
MAX_ICON_PIXELS = 1_048_576
MAX_GALLERY_FILES = 20
MAX_GALLERY_FILE_BYTES = 5 * 1024 * 1024
MAX_GALLERY_PIXELS = 16_000_000
MAX_TEXT_DOCUMENT_BYTES = 1024 * 1024
REQUIRED_PACKAGE_FILES = frozenset(
    {
        "manifest.json",
        "ui/index.html",
        "assets/icon.png",
        "README.md",
        "LICENSE",
    }
)


class PackageInspectionError(ValueError):
    """A Workshop archive failed the static trust-boundary inspection."""


_READ_CHUNK_BYTES = 1024 * 1024
_ALLOWED_COMPRESSION_METHODS = frozenset({ZIP_STORED, ZIP_DEFLATED})
_GALLERY_PREFIX = "assets/gallery/"
_GALLERY_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})
_RESERVED_DEVICE_NAMES = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{index}" for index in range(1, 10)),
        *(f"lpt{index}" for index in range(1, 10)),
    }
)
_CSS_URL = re.compile(r"url\s*\(\s*([^)]+?)\s*\)", flags=re.IGNORECASE)
_HEAD_TAG = re.compile(r"<head(?:\s|>)", flags=re.IGNORECASE)
_SCRIPT_TAG = re.compile(r"<script(?:\s|>)", flags=re.IGNORECASE)
_DYNAMIC_CODE = re.compile(r"\b(?:eval|import)\s*\(", flags=re.IGNORECASE)
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_SUSPICIOUS_MEDIA_MARKERS = (
    b"http://",
    b"https://",
    b"file://",
    b"javascript:",
    b"<script",
    b"<svg",
    b"<html",
)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_READ_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _is_symlink(info: ZipInfo) -> bool:
    if info.create_system != 3:
        return False
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def _has_unsupported_file_type(info: ZipInfo) -> bool:
    if info.create_system != 3:
        return False
    mode = (info.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(mode)
    return file_type not in {0, stat.S_IFREG}


def _validate_member_path(info: ZipInfo, seen: set[str]) -> str:
    name = info.filename
    if (
        not name
        or "\x00" in name
        or "\\" in name
        or name.startswith("/")
        or name.endswith("/")
        or unicodedata.normalize("NFC", name) != name
    ):
        raise PackageInspectionError(f"unsafe archive path: {name!r}")

    raw_parts = name.split("/")
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or any(part in {"", ".", ".."} for part in raw_parts)
        or len(path.parts) != len(raw_parts)
    ):
        raise PackageInspectionError(f"unsafe archive path: {name!r}")

    for part in raw_parts:
        if ":" in part or part.endswith((" ", ".")):
            raise PackageInspectionError(f"unsafe archive path: {name!r}")
        device_name = part.split(".", 1)[0].casefold()
        if device_name in _RESERVED_DEVICE_NAMES:
            raise PackageInspectionError(
                f"unsafe archive path uses a device name: {name!r}"
            )

    collision_key = name.casefold()
    if collision_key in seen:
        raise PackageInspectionError(
            f"case-insensitive duplicate archive path: {name!r}"
        )
    seen.add(collision_key)

    if _is_symlink(info):
        raise PackageInspectionError(
            f"symbolic link archive member is not allowed: {name!r}"
        )
    if _has_unsupported_file_type(info):
        raise PackageInspectionError(
            f"unsupported archive member type: {name!r}"
        )
    if info.flag_bits & 0x1:
        raise PackageInspectionError(
            f"encrypted archive member is not allowed: {name!r}"
        )
    if info.compress_type not in _ALLOWED_COMPRESSION_METHODS:
        raise PackageInspectionError(
            f"unsupported archive compression method: {name!r}"
        )
    return name


def _validate_declared_limits(
    members: list[ZipInfo],
    *,
    max_ratio: float,
) -> int:
    if len(members) > MAX_FILE_COUNT:
        raise PackageInspectionError(
            f"archive file count exceeds {MAX_FILE_COUNT}"
        )
    if max_ratio <= 0:
        raise PackageInspectionError("compression ratio limit must be positive")

    unpacked_bytes = 0
    compressed_payload_bytes = 0
    for info in members:
        if info.file_size < 0 or info.compress_size < 0:
            raise PackageInspectionError("archive contains a negative file size")
        if info.file_size > MAX_FILE_BYTES:
            raise PackageInspectionError(
                f"declared file size exceeds limit: {info.filename!r}"
            )
        unpacked_bytes += info.file_size
        compressed_payload_bytes += info.compress_size
        if unpacked_bytes > MAX_UNPACKED_BYTES:
            raise PackageInspectionError(
                "declared unpacked size exceeds package limit"
            )
        if info.file_size and (
            info.file_size / max(info.compress_size, 1) > max_ratio
        ):
            raise PackageInspectionError(
                f"archive compression ratio exceeds limit: {info.filename!r}"
            )

    if unpacked_bytes and (
        unpacked_bytes / max(compressed_payload_bytes, 1) > max_ratio
    ):
        raise PackageInspectionError(
            "aggregate archive compression ratio exceeds limit"
        )
    return unpacked_bytes


def _validate_package_file_set(member_names: set[str]) -> list[str]:
    missing = REQUIRED_PACKAGE_FILES - member_names
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise PackageInspectionError(
            f"missing required file: {missing_list}"
        )

    gallery_names: list[str] = []
    for name in member_names:
        if name in REQUIRED_PACKAGE_FILES:
            continue
        if name.startswith(_GALLERY_PREFIX):
            gallery_names.append(name)
            continue
        raise PackageInspectionError(f"unexpected package file: {name!r}")

    if len(gallery_names) > MAX_GALLERY_FILES:
        raise PackageInspectionError(
            f"gallery file count exceeds {MAX_GALLERY_FILES}"
        )
    return sorted(gallery_names)


def _validate_specific_declared_limits(
    members_by_name: dict[str, ZipInfo],
    gallery_names: Iterable[str],
) -> None:
    checks = (
        ("manifest.json", MAX_MANIFEST_BYTES, "manifest.json size"),
        ("assets/icon.png", MAX_ICON_BYTES, "icon size"),
        ("README.md", MAX_TEXT_DOCUMENT_BYTES, "README.md size"),
        ("LICENSE", MAX_TEXT_DOCUMENT_BYTES, "LICENSE size"),
    )
    for name, maximum, label in checks:
        if members_by_name[name].file_size > maximum:
            raise PackageInspectionError(f"{label} exceeds limit")

    for name in gallery_names:
        if members_by_name[name].file_size > MAX_GALLERY_FILE_BYTES:
            raise PackageInspectionError(
                f"gallery image size exceeds limit: {name!r}"
            )


def _read_member(package: ZipFile, info: ZipInfo) -> bytes:
    try:
        with package.open(info, "r") as stream:
            value = stream.read(info.file_size + 1)
            if stream.read(1):
                raise PackageInspectionError(
                    f"actual file size exceeds declaration: {info.filename!r}"
                )
    except PackageInspectionError:
        raise
    except (BadZipFile, OSError, RuntimeError, EOFError) as exc:
        raise PackageInspectionError(
            f"archive member could not be read: {info.filename!r}"
        ) from exc

    if len(value) != info.file_size:
        raise PackageInspectionError(
            f"actual file size does not match declaration: {info.filename!r}"
        )
    return value


def _decode_utf8(name: str, value: bytes) -> str:
    try:
        text = value.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise PackageInspectionError(f"{name} must be valid UTF-8") from exc
    if "\x00" in text:
        raise PackageInspectionError(f"{name} must not contain NUL bytes")
    return text


def _json_object_without_duplicates(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise PackageInspectionError(
                f"invalid manifest: duplicate JSON field {key!r}"
            )
        value[key] = item
    return value


def _parse_manifest(value: bytes) -> WorkshopManifest:
    text = _decode_utf8("manifest.json", value)
    try:
        raw = json.loads(
            text,
            object_pairs_hook=_json_object_without_duplicates,
        )
    except PackageInspectionError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise PackageInspectionError("invalid manifest JSON") from exc
    if not isinstance(raw, dict):
        raise PackageInspectionError("invalid manifest: root must be an object")
    try:
        return WorkshopManifest.model_validate(raw)
    except ValidationError as exc:
        raise PackageInspectionError(f"invalid manifest: {exc}") from exc


def _is_inline_resource(value: str) -> bool:
    normalized = value.strip().strip("\"'").strip()
    lowered = normalized.casefold()
    return (
        not normalized
        or normalized.startswith("#")
        or lowered.startswith("data:")
        or lowered.startswith("blob:")
        or lowered == "about:blank"
    )


class _RuntimeHtmlResourceValidator(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._inside_style = False

    @staticmethod
    def _validate_css(value: str) -> None:
        for match in _CSS_URL.finditer(value):
            if not _is_inline_resource(match.group(1)):
                raise PackageInspectionError(
                    "runtime HTML CSS must use only inline resources"
                )

    @classmethod
    def _validate_attributes(
        cls,
        attributes: list[tuple[str, str | None]],
    ) -> None:
        for name, value in attributes:
            if value is None:
                continue
            normalized_name = name.casefold()
            if (
                normalized_name in {"src", "href"}
                and not _is_inline_resource(value)
            ):
                raise PackageInspectionError(
                    "runtime HTML must not reference package or network files"
                )
            if normalized_name == "style":
                cls._validate_css(value)

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self._validate_attributes(attrs)
        if tag.casefold() == "style":
            self._inside_style = True

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self._validate_attributes(attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "style":
            self._inside_style = False

    def handle_data(self, data: str) -> None:
        if self._inside_style:
            self._validate_css(data)


def _validate_runtime_html(value: bytes) -> None:
    try:
        html = value.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise PackageInspectionError(
            "runtime HTML must be valid UTF-8"
        ) from exc
    if "\x00" in html:
        raise PackageInspectionError("runtime HTML must not contain NUL bytes")

    head = _HEAD_TAG.search(html)
    script = _SCRIPT_TAG.search(html)
    if head is None or (script is not None and script.start() < head.start()):
        raise PackageInspectionError(
            "runtime HTML must place <head> before the first <script>"
        )
    if _DYNAMIC_CODE.search(html):
        raise PackageInspectionError(
            "runtime HTML must not use eval or dynamic import"
        )

    validator = _RuntimeHtmlResourceValidator()
    validator.feed(html)
    validator.close()


def _png_dimensions(value: bytes) -> tuple[int, int] | None:
    if not value.startswith(_PNG_SIGNATURE) or len(value) < 33:
        return None
    if value[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", value[16:24])


def _validate_dimensions(
    *,
    width: int,
    height: int,
    max_pixels: int,
    label: str,
) -> None:
    if (
        width <= 0
        or height <= 0
        or width > MAX_IMAGE_EDGE
        or height > MAX_IMAGE_EDGE
        or width * height > max_pixels
    ):
        raise PackageInspectionError(f"{label} dimensions exceed limit")


def _contains_suspicious_media_metadata(value: bytes) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _SUSPICIOUS_MEDIA_MARKERS)


def _validate_image(
    *,
    name: str,
    value: bytes,
    icon: bool,
) -> None:
    suffix = Path(name).suffix.casefold()
    if icon:
        if suffix != ".png" or not value.startswith(_PNG_SIGNATURE):
            raise PackageInspectionError("icon must be a static PNG")
        expected_format = "PNG"
        max_pixels = MAX_ICON_PIXELS
        label = "icon"
    else:
        if suffix not in _GALLERY_SUFFIXES:
            raise PackageInspectionError(
                "gallery image must be PNG, JPEG, or WebP"
            )
        signatures_match = (
            suffix == ".png"
            and value.startswith(_PNG_SIGNATURE)
        ) or (
            suffix in {".jpg", ".jpeg"}
            and value.startswith(b"\xff\xd8\xff")
        ) or (
            suffix == ".webp"
            and len(value) >= 12
            and value.startswith(b"RIFF")
            and value[8:12] == b"WEBP"
        )
        if not signatures_match:
            raise PackageInspectionError(
                "gallery image signature does not match its extension"
            )
        expected_formats_by_suffix = {
            ".png": "PNG",
            ".jpg": "JPEG",
            ".jpeg": "JPEG",
            ".webp": "WEBP",
        }
        expected_format = expected_formats_by_suffix[suffix]
        max_pixels = MAX_GALLERY_PIXELS
        label = "gallery image"

    png_size = _png_dimensions(value)
    if png_size is not None:
        _validate_dimensions(
            width=png_size[0],
            height=png_size[1],
            max_pixels=max_pixels,
            label=label,
        )
    if b"acTL" in value or (
        suffix == ".webp" and b"ANIM" in value[:64]
    ):
        raise PackageInspectionError(f"{label} must not be animated")
    if _contains_suspicious_media_metadata(value):
        raise PackageInspectionError(
            f"{label} contains an external metadata reference"
        )

    try:
        with io.BytesIO(value) as io_path, Image.open(io_path) as image:
            if image.format != expected_format:
                raise PackageInspectionError(
                    f"{label} format does not match its package path"
                )
            width, height = image.size
            _validate_dimensions(
                width=width,
                height=height,
                max_pixels=max_pixels,
                label=label,
            )
            if getattr(image, "n_frames", 1) != 1:
                raise PackageInspectionError(f"{label} must not be animated")
            if any(
                key in image.info
                for key in (
                    "exif",
                    "xmp",
                    "XML:com.adobe.xmp",
                    "icc_profile",
                    "comment",
                )
            ):
                raise PackageInspectionError(
                    f"{label} contains unsupported metadata"
                )
            image.verify()
    except PackageInspectionError:
        raise
    except Image.DecompressionBombError as exc:
        raise PackageInspectionError(
            f"{label} dimensions exceed limit"
        ) from exc
    except (
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ) as exc:
        raise PackageInspectionError(f"{label} is malformed") from exc


def _inspect_open_zip(
    package: ZipFile,
    *,
    archive_path: Path,
    compressed_bytes: int,
    archive_sha256: str,
    max_ratio: float,
) -> InspectedPackage:
    members = package.infolist()
    seen: set[str] = set()
    members_by_name: dict[str, ZipInfo] = {}
    for info in members:
        name = _validate_member_path(info, seen)
        members_by_name[name] = info

    unpacked_bytes = _validate_declared_limits(
        members,
        max_ratio=max_ratio,
    )
    gallery_names = _validate_package_file_set(set(members_by_name))
    _validate_specific_declared_limits(members_by_name, gallery_names)

    manifest_bytes = _read_member(package, members_by_name["manifest.json"])
    runtime_html = _read_member(package, members_by_name["ui/index.html"])
    icon_bytes = _read_member(package, members_by_name["assets/icon.png"])
    readme_bytes = _read_member(package, members_by_name["README.md"])
    license_bytes = _read_member(package, members_by_name["LICENSE"])

    manifest = _parse_manifest(manifest_bytes)
    _validate_runtime_html(runtime_html)
    _validate_image(
        name="assets/icon.png",
        value=icon_bytes,
        icon=True,
    )
    _decode_utf8("README.md", readme_bytes)
    _decode_utf8("LICENSE", license_bytes)

    for name in gallery_names:
        _validate_image(
            name=name,
            value=_read_member(package, members_by_name[name]),
            icon=False,
        )

    return InspectedPackage(
        archive_path=archive_path,
        manifest=manifest,
        entry_html=manifest.entrypoints.ui,
        compressed_bytes=compressed_bytes,
        unpacked_bytes=unpacked_bytes,
        archive_sha256=archive_sha256,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        member_names=tuple(sorted(members_by_name)),
    )


def inspect_package(
    archive_path: str | Path,
    *,
    max_ratio: float = MAX_COMPRESSION_RATIO,
) -> InspectedPackage:
    """Inspect one Workshop package without executing module code.

    在不执行模块代码的前提下检查一个创意工坊安装包。
    """

    path = Path(archive_path).expanduser().resolve()
    if path.suffix != ".lumina-workshop":
        raise PackageInspectionError(
            "Workshop packages must use the .lumina-workshop extension"
        )
    try:
        compressed_bytes = path.stat().st_size
    except OSError as exc:
        raise PackageInspectionError("Workshop package is not readable") from exc
    if not path.is_file():
        raise PackageInspectionError("Workshop package is not a regular file")
    if compressed_bytes > MAX_PACKAGE_BYTES:
        raise PackageInspectionError("compressed package size exceeds limit")

    try:
        archive_sha256 = _hash_file(path)
        with ZipFile(path, "r", allowZip64=True) as package:
            inspected = _inspect_open_zip(
                package,
                archive_path=path,
                compressed_bytes=compressed_bytes,
                archive_sha256=archive_sha256,
                max_ratio=max_ratio,
            )
    except PackageInspectionError:
        raise
    except (BadZipFile, LargeZipFile, OSError, RuntimeError) as exc:
        raise PackageInspectionError("invalid Workshop ZIP package") from exc

    if _hash_file(path) != archive_sha256:
        raise PackageInspectionError("package changed during inspection")
    return inspected

