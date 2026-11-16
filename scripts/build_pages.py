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
        "reviews-v1.json",
        "reviews-v1.sig",
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
{reviews}</ul>
</body>
</html>
"""
REVIEWS_HTML = (
    '<li><a href="reviews-v1.json">reviews-v1.json</a> '
    "(signed backend code reviews)</li>\n"
    '<li><a href="reviews-v1.sig">reviews-v1.sig</a></li>\n'
)


def build_pages(
    *,
    index: Path,
    signature: Path,
    output: Path,
    reviews: Path | None = None,
    reviews_signature: Path | None = None,
) -> None:
    """Create exactly the public index, signature, and minimal HTML page.

    Backend review attestations are published as a separately signed pair
    so the v1 index stays parseable by hosts that predate module backends.
    """

    if (reviews is None) != (reviews_signature is None):
        raise ValueError("reviews and reviews signature must be published together")

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
    if reviews is not None and reviews_signature is not None:
        shutil.copyfile(reviews, output / "reviews-v1.json")
        shutil.copyfile(reviews_signature, output / "reviews-v1.sig")
    (output / "index.html").write_text(
        INDEX_HTML.replace("{reviews}", REVIEWS_HTML if reviews is not None else ""),
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    """Build one bounded Pages directory."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--signature", type=Path, required=True)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--reviews-signature", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    build_pages(
        index=arguments.index,
        signature=arguments.signature,
        output=arguments.output,
        reviews=arguments.reviews,
        reviews_signature=arguments.reviews_signature,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
