"""Strict source and generated-index models for the Workshop Registry."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-"
    r"(?:0|[1-9]\d*|[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|[A-Za-z-][0-9A-Za-z-]*))*"
    r")?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
MODULE_ID_PATTERN = re.compile(
    r"^[a-z0-9]+(?:[.-][a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?)*$"
)
ALLOWED_PERMISSION_NAMES = frozenset(
    {
        "image.pick",
        "project.storage",
        "color-library.read",
        "handoff.image",
    }
)
# Manifest v2 backend declarations; must stay identical to Lumina's host.
BACKEND_API_VERSION = "1.1.0"
BACKEND_PYTHON_VERSIONS = frozenset({"3.12"})
BACKEND_PLATFORMS = frozenset({"windows-x86_64", "linux-x86_64", "macos-arm64"})
BACKEND_CAPABILITY_NAMES = frozenset({"network", "subprocess", "external-files"})
_BACKEND_ID = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
_MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SAFE_FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_BACKEND_PATH = re.compile(
    r"^backend/(?:[A-Za-z0-9_][A-Za-z0-9._-]{0,127}/){0,8}"
    r"[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$"
)
_PYLOCK_NAME = re.compile(r"^pylock(?:\.[A-Za-z0-9_-]+)?\.toml$")


def validate_semver(value: str) -> str:
    """Return an exact SemVer value."""

    if SEMVER_PATTERN.fullmatch(value) is None:
        raise ValueError("value must be valid SemVer")
    return value


def semver_sort_key(
    value: str,
) -> tuple[int, int, int, int, tuple[tuple[int, int | str], ...]]:
    """Return a SemVer precedence key that ignores build metadata."""

    validate_semver(value)
    without_build = value.split("+", 1)[0]
    core, separator, prerelease = without_build.partition("-")
    major, minor, patch = (int(part) for part in core.split("."))
    if not separator:
        return major, minor, patch, 1, ()
    identifiers: list[tuple[int, int | str]] = []
    for identifier in prerelease.split("."):
        if identifier.isdigit():
            identifiers.append((0, int(identifier)))
        else:
            identifiers.append((1, identifier))
    return major, minor, patch, 0, tuple(identifiers)


def compare_semver(left: str, right: str) -> int:
    """Compare two valid SemVer values by precedence."""

    left_key = semver_sort_key(left)
    right_key = semver_sort_key(right)
    return (left_key > right_key) - (left_key < right_key)


class StrictFrozenModel(BaseModel):
    """Immutable model with a closed schema and JSON aliases."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=False,
    )


class LocalizedText(StrictFrozenModel):
    zh_cn: str = Field(alias="zh-CN", min_length=1, max_length=200)
    en_us: str = Field(alias="en-US", min_length=1, max_length=200)

    @field_validator("zh_cn", "en_us")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("localized text must not be blank")
        return normalized


class ApiRange(StrictFrozenModel):
    minimum: str = Field(alias="min")
    max_exclusive: str = Field(alias="maxExclusive")

    @field_validator("minimum", "max_exclusive")
    @classmethod
    def versions_are_semver(cls, value: str) -> str:
        return validate_semver(value)

    @model_validator(mode="after")
    def maximum_is_after_minimum(self) -> ApiRange:
        if compare_semver(self.max_exclusive, self.minimum) <= 0:
            raise ValueError("Workshop API maxExclusive must exceed min")
        return self


class LuminaRange(StrictFrozenModel):
    minimum: str = Field(alias="min")

    @field_validator("minimum")
    @classmethod
    def version_is_semver(cls, value: str) -> str:
        return validate_semver(value)


class Permission(StrictFrozenModel):
    name: str
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("name")
    @classmethod
    def permission_is_known(cls, value: str) -> str:
        if value not in ALLOWED_PERMISSION_NAMES:
            raise ValueError(f"unknown permission: {value}")
        return value

    @field_validator("reason")
    @classmethod
    def reason_is_not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("permission reason must not be blank")
        return normalized


class Entrypoints(StrictFrozenModel):
    ui: str

    @field_validator("ui")
    @classmethod
    def entry_is_fixed(cls, value: str) -> str:
        if value != "ui/index.html":
            raise ValueError("UI entrypoint must be ui/index.html")
        return value


def _backend_path(value: str, suffix: str) -> str:
    if (
        _BACKEND_PATH.fullmatch(value) is None
        or ".." in value.split("/")
        or not value.endswith(suffix)
    ):
        raise ValueError(f"backend path must be backend/...{suffix}")
    return value


def _backend_lock(value: str) -> str:
    _backend_path(value, ".toml")
    if _PYLOCK_NAME.fullmatch(value.rsplit("/", 1)[-1]) is None:
        raise ValueError(
            "backend lock must be named pylock.toml or pylock.<name>.toml"
        )
    return value


def _known_platforms(values: tuple[str, ...]) -> bool:
    return set(values) <= BACKEND_PLATFORMS and len(set(values)) == len(values)


class BackendCapability(StrictFrozenModel):
    name: str
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("name")
    @classmethod
    def capability_is_known(cls, value: str) -> str:
        if value not in BACKEND_CAPABILITY_NAMES:
            raise ValueError(f"unknown backend capability: {value}")
        return value


class BackendModelFile(StrictFrozenModel):
    id: str
    file_name: str = Field(alias="fileName")
    url: str = Field(max_length=2048)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(alias="bytes", gt=0, le=16 * 1024 * 1024 * 1024)
    license: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def fields_are_safe(self) -> BackendModelFile:
        parsed = urlsplit(self.url)
        if (
            _MODEL_ID.fullmatch(self.id) is None
            or _SAFE_FILE_NAME.fullmatch(self.file_name) is None
            or self.file_name.endswith(".")
            or parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError("backend model declaration is invalid")
        return self


class BackendVariant(StrictFrozenModel):
    id: str
    name: LocalizedText
    description: LocalizedText
    lock: str
    platforms: tuple[str, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def variant_is_valid(self) -> BackendVariant:
        _backend_lock(self.lock)
        if _BACKEND_ID.fullmatch(self.id) is None or self.id == "cpu":
            raise ValueError("variant id is invalid or reserved")
        if not _known_platforms(self.platforms):
            raise ValueError("variant platforms are invalid")
        return self


class BackendDeclaration(StrictFrozenModel):
    entry: str
    python: str
    lock: str
    platforms: tuple[str, ...] = Field(min_length=1, max_length=8)
    capabilities: tuple[BackendCapability, ...] = Field(default=(), max_length=8)
    models: tuple[BackendModelFile, ...] = Field(default=(), max_length=32)
    variants: tuple[BackendVariant, ...] = Field(default=(), max_length=4)
    idle_timeout_seconds: int | None = Field(
        default=None,
        alias="idleTimeoutSeconds",
        ge=30,
        le=3600,
    )

    @model_validator(mode="after")
    def declaration_is_consistent(self) -> BackendDeclaration:
        _backend_path(self.entry, ".py")
        _backend_lock(self.lock)
        if self.python not in BACKEND_PYTHON_VERSIONS:
            raise ValueError("backend Python version is not supported")
        if not _known_platforms(self.platforms):
            raise ValueError("backend platforms are invalid")
        for label, values in (
            ("capabilities", [item.name for item in self.capabilities]),
            ("model ids", [item.id for item in self.models]),
            ("model file names", [item.file_name.casefold() for item in self.models]),
            ("variant ids", [item.id for item in self.variants]),
            ("locks", [self.lock, *(item.lock for item in self.variants)]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"backend {label} must be unique")
        for variant in self.variants:
            if not set(variant.platforms) <= set(self.platforms):
                raise ValueError("variant platforms must be backend platforms")
        return self

    def referenced_files(self) -> tuple[str, ...]:
        locks = {self.lock, *(item.lock for item in self.variants)}
        return tuple(sorted({self.entry, *locks}))


class WorkshopProjectSnapshots(StrictFrozenModel):
    protocol: Literal[1]
    schemas: tuple[str, ...] = Field(min_length=1, max_length=32)

    @field_validator("schemas")
    @classmethod
    def schemas_are_bounded(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value) or any(
            not item or len(item) > 128 for item in value
        ):
            raise ValueError("invalid project snapshot schemas")
        return value


class WorkshopManifest(StrictFrozenModel):
    manifest_version: Literal[1] = Field(alias="manifestVersion")
    id: str = Field(min_length=3, max_length=128)
    version: str
    name: LocalizedText
    description: LocalizedText
    publisher: str = Field(min_length=1, max_length=200)
    workshop_api: ApiRange = Field(alias="workshopApi")
    lumina_version: LuminaRange = Field(alias="luminaVersion")
    entrypoints: Entrypoints
    permissions: tuple[Permission, ...] = Field(max_length=32)
    project_snapshots: WorkshopProjectSnapshots | None = Field(
        default=None, alias="projectSnapshots"
    )

    @field_validator("id")
    @classmethod
    def module_id_is_safe(cls, value: str) -> str:
        return _validate_module_id(value)

    @field_validator("version")
    @classmethod
    def version_is_semver(cls, value: str) -> str:
        return validate_semver(value)

    @field_validator("publisher")
    @classmethod
    def publisher_is_not_blank(cls, value: str) -> str:
        return _validate_publisher(value)

    @model_validator(mode="after")
    def permissions_are_unique(self) -> WorkshopManifest:
        permission_names = [
            permission.name for permission in self.permissions
        ]
        if len(permission_names) != len(set(permission_names)):
            raise ValueError("manifest contains duplicate permissions")
        if self.project_snapshots and "project.storage" not in permission_names:
            raise ValueError("project snapshots require project.storage permission")
        return self


class WorkshopManifestV2(StrictFrozenModel):
    """Manifest with a host-managed backend (Workshop API >= 1.1.0)."""

    manifest_version: Literal[2] = Field(alias="manifestVersion")
    id: str = Field(min_length=3, max_length=128)
    version: str
    name: LocalizedText
    description: LocalizedText
    publisher: str = Field(min_length=1, max_length=200)
    workshop_api: ApiRange = Field(alias="workshopApi")
    lumina_version: LuminaRange = Field(alias="luminaVersion")
    entrypoints: Entrypoints
    permissions: tuple[Permission, ...] = Field(max_length=32)
    # The host accepts project snapshots on v1 and v2 manifests alike.
    project_snapshots: WorkshopProjectSnapshots | None = Field(
        default=None, alias="projectSnapshots"
    )
    backend: BackendDeclaration

    @model_validator(mode="after")
    def backend_requires_backend_api(self) -> WorkshopManifestV2:
        _validate_module_id(self.id)
        validate_semver(self.version)
        _validate_publisher(self.publisher)
        names = [permission.name for permission in self.permissions]
        if len(names) != len(set(names)):
            raise ValueError("manifest contains duplicate permissions")
        if self.project_snapshots and "project.storage" not in names:
            raise ValueError("project snapshots require project.storage permission")
        if compare_semver(self.workshop_api.minimum, BACKEND_API_VERSION) < 0:
            raise ValueError(
                f"backend modules require workshopApi.min >= {BACKEND_API_VERSION}"
            )
        return self


AnyWorkshopManifest = WorkshopManifest | WorkshopManifestV2


class InspectedPackage(StrictFrozenModel):
    archive_path: Path
    manifest: WorkshopManifest | WorkshopManifestV2
    entry_html: str
    compressed_bytes: int = Field(ge=0)
    unpacked_bytes: int = Field(ge=0)
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    member_names: tuple[str, ...]


class Revocation(StrictFrozenModel):
    reason_code: str = Field(
        alias="reasonCode",
        pattern=r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$",
        min_length=2,
        max_length=80,
    )
    severity: Literal["low", "medium", "high", "critical"]
    message: LocalizedText


class VersionBase(StrictFrozenModel):
    version: str
    release_tag: str = Field(alias="releaseTag", min_length=2, max_length=160)
    asset_name: str = Field(alias="assetName", min_length=1, max_length=240)
    asset_bytes: int = Field(
        alias="assetBytes",
        gt=0,
        le=100 * 1024 * 1024,
    )
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(
        alias="manifestSha256",
        pattern=r"^[0-9a-f]{64}$",
    )
    workshop_api: ApiRange = Field(alias="workshopApi")
    lumina_version: LuminaRange = Field(alias="luminaVersion")
    permissions: tuple[Permission, ...] = Field(max_length=32)
    state: Literal["active", "deprecated", "blocked"]
    revocation: Revocation | None

    @field_validator("version")
    @classmethod
    def version_is_semver(cls, value: str) -> str:
        return validate_semver(value)

    @model_validator(mode="after")
    def identity_and_revocation_are_consistent(self) -> VersionBase:
        if self.release_tag != f"v{self.version}":
            raise ValueError("releaseTag must equal v<version>")
        if self.state == "blocked" and self.revocation is None:
            raise ValueError("blocked version requires revocation")
        if self.state != "blocked" and self.revocation is not None:
            raise ValueError("only blocked versions may carry revocation")
        permission_names = [
            permission.name for permission in self.permissions
        ]
        if len(permission_names) != len(set(permission_names)):
            raise ValueError("version has duplicate permissions")
        return self


class BackendReview(StrictFrozenModel):
    """A maintainer's review of one exact version's backend code.

    It binds to the version record's ``sha256``/``manifestSha256`` and is
    published only in the separately signed ``reviews-v1.json``.
    """

    scope: Literal["backend-code"]
    reviewer: str = Field(pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
    reviewed_at: str = Field(alias="reviewedAt", pattern=r"^\d{4}-\d{2}-\d{2}$")


class SourceVersion(VersionBase):
    """One reviewed immutable release record."""

    backend_review: BackendReview | None = Field(default=None, alias="backendReview")


class ReviewAttestation(StrictFrozenModel):
    module_id: str = Field(alias="moduleId", min_length=3, max_length=128)
    version: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(alias="manifestSha256", pattern=r"^[0-9a-f]{64}$")
    scope: Literal["backend-code"]
    reviewed_at: str = Field(alias="reviewedAt", pattern=r"^\d{4}-\d{2}-\d{2}$")

    @model_validator(mode="after")
    def identity_is_valid(self) -> ReviewAttestation:
        _validate_module_id(self.module_id)
        validate_semver(self.version)
        return self


class ReviewIndex(StrictFrozenModel):
    """Signed list of reviewed backend versions (``reviews-v1.json``)."""

    schema_version: Literal[1] = Field(alias="schemaVersion")
    generated_at: datetime = Field(alias="generatedAt")
    reviews: tuple[ReviewAttestation, ...] = Field(max_length=20_000)

    @model_validator(mode="after")
    def reviews_are_unique(self) -> ReviewIndex:
        keys = [(item.module_id, item.version) for item in self.reviews]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate review attestation")
        return self


def _validate_repository(value: str) -> str:
    parsed = urlsplit(value)
    parts = tuple(part for part in parsed.path.split("/") if part)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or value.endswith("/")
        or len(parts) != 2
        or parts[1].endswith(".git")
    ):
        raise ValueError(
            "repository must be an exact HTTPS GitHub repository URL"
        )
    return value


def _validate_module_id(value: str) -> str:
    if MODULE_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("moduleId must be lowercase reverse-domain style")
    return value


def _validate_publisher(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("publisher must not be blank")
    return normalized


def _validate_versions(
    module_id: str,
    versions: tuple[VersionBase, ...],
) -> None:
    previous: str | None = None
    for version in versions:
        if (
            previous is not None
            and compare_semver(version.version, previous) <= 0
        ):
            raise ValueError(
                "duplicate module version or versions not increasing"
            )
        previous = version.version
        expected_asset = f"{module_id}-{version.version}.lumina-workshop"
        if version.asset_name != expected_asset:
            raise ValueError("assetName must match moduleId and version")


class ModuleSource(StrictFrozenModel):
    schema_version: Literal[1] = Field(alias="schemaVersion")
    module_id: str = Field(alias="moduleId", min_length=3, max_length=128)
    repository: str = Field(min_length=1, max_length=500)
    official: bool
    publisher: str = Field(min_length=1, max_length=200)
    versions: tuple[SourceVersion, ...] = Field(max_length=100)

    _module_id_is_safe = field_validator("module_id")(_validate_module_id)
    _repository_is_github_https = field_validator("repository")(
        _validate_repository
    )
    _publisher_is_not_blank = field_validator("publisher")(
        _validate_publisher
    )

    @model_validator(mode="after")
    def versions_match_module_identity(self) -> ModuleSource:
        _validate_versions(self.module_id, self.versions)
        return self


class RegistryVersion(VersionBase):
    download_url: str = Field(alias="downloadUrl", min_length=1, max_length=2048)

    @field_validator("download_url")
    @classmethod
    def download_is_an_exact_github_https_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "github.com"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("downloadUrl must be an HTTPS GitHub URL")
        return value


class RegistryModule(StrictFrozenModel):
    module_id: str = Field(alias="moduleId", min_length=3, max_length=128)
    repository: str = Field(min_length=1, max_length=500)
    official: bool
    publisher: str = Field(min_length=1, max_length=200)
    name: LocalizedText
    description: LocalizedText
    versions: tuple[RegistryVersion, ...] = Field(
        min_length=1,
        max_length=100,
    )

    _module_id_is_safe = field_validator("module_id")(_validate_module_id)
    _repository_is_github_https = field_validator("repository")(
        _validate_repository
    )
    _publisher_is_not_blank = field_validator("publisher")(
        _validate_publisher
    )

    @model_validator(mode="after")
    def versions_match_module_identity(self) -> RegistryModule:
        _validate_versions(self.module_id, self.versions)
        for version in self.versions:
            expected_download = (
                f"{self.repository}/releases/download/"
                f"{version.release_tag}/{version.asset_name}"
            )
            if version.download_url != expected_download:
                raise ValueError(
                    "downloadUrl must match repository release identity"
                )
        return self


class RegistryIndex(StrictFrozenModel):
    schema_version: Literal[1] = Field(alias="schemaVersion")
    generated_at: datetime = Field(alias="generatedAt")
    modules: tuple[RegistryModule, ...] = Field(max_length=5_000)

    @field_validator("generated_at")
    @classmethod
    def generated_at_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generatedAt must include a timezone")
        return value

    @model_validator(mode="after")
    def module_ids_are_unique(self) -> RegistryIndex:
        module_ids = [module.module_id for module in self.modules]
        if len(module_ids) != len(set(module_ids)):
            raise ValueError("duplicate module id in Registry")
        return self
