from __future__ import annotations

from pathlib import Path

import pytest

from scripts.build_pages import build_pages


def write_inputs(directory: Path) -> tuple[Path, Path]:
    index = directory / "registry.json"
    signature = directory / "registry.sig"
    index.write_text('{"schemaVersion":1}\n', encoding="utf-8")
    signature.write_text('{"signature":"test"}\n', encoding="utf-8")
    return index, signature


def test_build_pages_replaces_only_known_generated_files(
    tmp_path: Path,
) -> None:
    index, signature = write_inputs(tmp_path)
    output = tmp_path / "pages"
    output.mkdir()
    (output / "index.html").write_text("stale", encoding="utf-8")
    (output / "registry-v1.json").write_text("stale", encoding="utf-8")
    (output / "registry-v1.sig").write_text("stale", encoding="utf-8")

    build_pages(index=index, signature=signature, output=output)

    assert sorted(path.name for path in output.iterdir()) == [
        "index.html",
        "registry-v1.json",
        "registry-v1.sig",
    ]
    assert (output / "registry-v1.json").read_bytes() == index.read_bytes()
    assert (output / "registry-v1.sig").read_bytes() == signature.read_bytes()


def test_build_pages_refuses_unknown_existing_content(
    tmp_path: Path,
) -> None:
    index, signature = write_inputs(tmp_path)
    output = tmp_path / "pages"
    output.mkdir()
    important = output / "keep-me.txt"
    important.write_text("user data", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown content"):
        build_pages(index=index, signature=signature, output=output)

    assert important.read_text(encoding="utf-8") == "user data"


def test_build_pages_refuses_symlink_output(tmp_path: Path) -> None:
    index, signature = write_inputs(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    output = tmp_path / "pages"
    output.symlink_to(target, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        build_pages(index=index, signature=signature, output=output)
