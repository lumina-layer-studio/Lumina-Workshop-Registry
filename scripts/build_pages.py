"""Construct the exact non-executable GitHub Pages publication directory."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

PAGE_FILENAMES = frozenset(
    {
        "index.html",
        "registry-v1.json",
        "registry-v1.sig",
    }
)

INDEX_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Lumina Workshop Registry</title></head>
<body>
<h1>Lumina Workshop Registry</h1>
<p>This site publishes a signed machine-readable module catalogue.</p>
<ul>
<li><a href="registry-v1.json">registry-v1.json</a></li>
<li><a href="registry-v1.sig">registry-v1.sig</a></li>
</ul>
</body>
</html>
"""


def build_pages(
    *,
    index: Path,
    signature: Path,
    output: Path,
) -> None:
    """Create exactly the public index, signature, and minimal HTML page."""

    if output.is_symlink():
        raise ValueError("Pages output must not be a symlink")
    if output.exists():
        if not output.is_dir():
            raise ValueError("Pages output must be a directory")
        existing = tuple(output.iterdir())
        unknown = sorted(
            path.name for path in existing if path.name not in PAGE_FILENAMES
        )
        if unknown:
            raise ValueError(
                "Pages output contains unknown content: "
                + ", ".join(unknown)
            )
        for path in existing:
            if not path.is_file() or path.is_symlink():
                raise ValueError("generated Pages entries must be regular files")
            path.unlink()
    else:
        output.mkdir(parents=True)
    shutil.copyfile(index, output / "registry-v1.json")
    shutil.copyfile(signature, output / "registry-v1.sig")
    (output / "index.html").write_text(
        INDEX_HTML,
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    """Build one bounded Pages directory."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--signature", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    build_pages(
        index=arguments.index,
        signature=arguments.signature,
        output=arguments.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
