# Lumina Workshop Registry

[English](README.md) · [简体中文](README_CN.md) · [Published endpoints](#published-endpoints) · [Submitting a module](#submitting-a-module) · [Local validation](#local-validation) · [Workshop SDK](https://github.com/lumina-layer-studio/Lumina-Workshop-SDK)

The signed public catalog of installable Creative Workshop modules for [Lumina Studio](https://github.com/lumina-layer-studio/Lumina-Layers).

Lumina Studio reads this catalog to browse official and community modules built with [`@lumina/workshop-sdk`](https://github.com/lumina-layer-studio/Lumina-Workshop-SDK), check version compatibility and permissions, verify package SHA-256 digests before installation, and manage updates or rollbacks.

## Published endpoints

| Endpoint | Purpose |
| --- | --- |
| `https://lumina-layer-studio.github.io/Lumina-Workshop-Registry/registry-v1.json` | v1 catalog of approved modules and versions |
| `https://lumina-layer-studio.github.io/Lumina-Workshop-Registry/registry-v1.sig` | Detached Ed25519 signature over `registry-v1.json` |
| `https://lumina-layer-studio.github.io/Lumina-Workshop-Registry/reviews-v1.json` | Exact module versions whose Python backend code has been reviewed by a maintainer |
| `https://lumina-layer-studio.github.io/Lumina-Workshop-Registry/reviews-v1.sig` | Detached Ed25519 signature over `reviews-v1.json` |

Lumina Studio verifies `.sig` files against its built-in trusted public keys; the matching public-key record lives in [`keys/`](keys/) (see [docs/key-rotation.md](docs/key-rotation.md)).

## Submitting a module

1. **Build and release your package:** Build `<module-id>-<version>.lumina-workshop` with [`Lumina-Workshop-SDK`](https://github.com/lumina-layer-studio/Lumina-Workshop-SDK) and publish it on a non-draft, non-prerelease GitHub Release tag.
2. **Add or append a source record:** Create or update `modules/<module-id>.json` matching [`schemas/module-source-v1.schema.json`](schemas/module-source-v1.schema.json) with the release tag, asset URL, byte size, `sha256`, `manifestSha256`, compatibility ranges, and permissions (plus optional [project snapshots](docs/project-snapshots.md)).
3. **Run local checks and open a Pull Request** against `main`.

### Review and publication flow

- Each module ID stays bound to its registered GitHub repository, and new versions are appended without modifying earlier entries.
- Pull-request CI validates schema conformance, release digests, and package structure, surfacing any permission or compatibility changes in the PR diff.
- After maintainer review and merge to `main`, the release workflow signs and publishes the updated catalog. For manifest v2 modules with a Python backend, maintainer source reviews are recorded per version via `backendReview` in `reviews-v1.json`.

Full rules are in [docs/review-policy.md](docs/review-policy.md).

## Repository layout

```text
modules/    Per-module source records (<module-id>.json)
schemas/    JSON Schemas for source records, registry-v1, and reviews-v1
keys/       Ed25519 public-key records
src/        Catalog builder, package inspector, and validators
scripts/    Validation and build entry points
docs/       Review policy, key rotation, and capability notes
tests/      Pytest suite
```

## Local validation

Requires Python 3.12:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
PYTHONPATH=src .venv/bin/ruff check src scripts tests
PYTHONPATH=src .venv/bin/python -m pytest tests -v
PYTHONPATH=src .venv/bin/python scripts/validate_sources.py
```

## License

Tooling in this repository is licensed under the [MIT License](LICENSE). Indexed Workshop modules retain their own licenses.
