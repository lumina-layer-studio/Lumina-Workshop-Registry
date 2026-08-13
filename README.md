# Lumina Workshop Registry

The public, signed catalogue for installable Lumina Studio Workshop modules.
Reviewed source records are validated against immutable GitHub Release assets,
compiled into deterministic JSON, and signed with an offline-managed Ed25519
key before publication.

Registry source never contains private signing material, mutable download URLs,
or executable code. Official and community modules use the same validation,
permission, update, rollback, and uninstall contract.

## Published endpoints

- `https://lumina-layer-studio.github.io/Lumina-Workshop-Registry/registry-v1.json`
- `https://lumina-layer-studio.github.io/Lumina-Workshop-Registry/registry-v1.sig`

The detached Ed25519 signature covers the exact JSON bytes, including the
single trailing newline. Lumina owns the trusted public-key set; a Registry PR
cannot introduce its own verification key.

## Review model

Each module ID is permanently bound to one reviewed GitHub repository.
Historical version records are append-only, and every new version is
downloaded twice and statically inspected without extraction or execution.
Registry CI validates exact asset bytes, manifest bytes, compatibility,
permissions, and deterministic output before a maintainer may merge.

Pull-request jobs are read-only and never receive signing material. Publishing
runs only from protected `main` through the `registry-production` Environment.
The scheduled scanner may open an append-only PR, but cannot sign, publish, or
merge it.

See [review policy](docs/review-policy.md) and
[key rotation](docs/key-rotation.md) for operational details.

## Local verification

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
PYTHONPATH=src .venv/bin/ruff check src scripts tests
PYTHONPATH=src .venv/bin/python -m pytest tests -v
PYTHONPATH=src .venv/bin/python scripts/validate_sources.py
```

No private key, GitHub token, generated signature, downloaded module, or
mutable `latest` URL belongs in this repository.

