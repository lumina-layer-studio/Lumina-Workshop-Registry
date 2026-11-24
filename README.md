# Lumina Workshop Registry

[English](README.md) · [简体中文](README_CN.md) · [Published endpoints](#published-endpoints) · [Submitting a module](#submitting-a-module) · [Local validation](#local-validation) · [Workshop SDK](https://github.com/lumina-layer-studio/Lumina-Workshop-SDK)

The signed public catalog of installable Creative Workshop modules for [Lumina Studio](https://github.com/lumina-layer-studio/Lumina-Layers).

Each entry in [`modules/`](modules/) points to immutable GitHub Release packages built with [`@lumina/workshop-sdk`](https://github.com/lumina-layer-studio/Lumina-Workshop-SDK). Source records are validated in CI, compiled into deterministic JSON indices, and signed with Ed25519 before publication.

## How it works with Lumina Studio

Lumina Studio fetches this catalog to show available official and community Workshop modules, check version compatibility and declared permissions, verify package SHA-256 digests before installation, and manage updates or rollbacks. Official and community modules follow the same package layout, permission declarations, and lifecycle rules.

## Published endpoints

| Endpoint | Purpose |
| --- | --- |
| `https://lumina-layer-studio.github.io/Lumina-Workshop-Registry/registry-v1.json` | Deterministic v1 catalog of approved modules and release versions |
| `https://lumina-layer-studio.github.io/Lumina-Workshop-Registry/registry-v1.sig` | Detached Ed25519 signature over `registry-v1.json` |
| `https://lumina-layer-studio.github.io/Lumina-Workshop-Registry/reviews-v1.json` | Exact module versions whose Python backend code has been reviewed by a maintainer |
| `https://lumina-layer-studio.github.io/Lumina-Workshop-Registry/reviews-v1.sig` | Detached Ed25519 signature over `reviews-v1.json` |

Each `.sig` file covers the exact JSON bytes, including the trailing newline. Lumina Studio verifies catalog signatures against its built-in set of trusted public keys; the corresponding public-key record lives in [`keys/`](keys/). Key rotation and recovery steps are documented in [docs/key-rotation.md](docs/key-rotation.md).

## Submitting a module

1. **Build and release your package.** Develop your module with [`Lumina-Workshop-SDK`](https://github.com/lumina-layer-studio/Lumina-Workshop-SDK), package it as `<module-id>-<version>.lumina-workshop`, and publish it on a non-draft, non-prerelease GitHub Release tag.
2. **Add or append a source record.** Create or update `modules/<module-id>.json` matching [`schemas/module-source-v1.schema.json`](schemas/module-source-v1.schema.json) with the release tag, asset URL, byte length, archive `sha256`, `manifestSha256`, compatibility ranges, and requested permissions (plus optional capabilities such as [project snapshots](docs/project-snapshots.md)).
3. **Run local checks and open a Pull Request** against `main`.

### Review and publication flow

- **Permanent identity & append-only versions:** Each module ID stays bound to its registered GitHub repository, and new releases are appended without rewriting earlier version records.
- **Automated PR verification:** Pull-request CI downloads newly added release assets twice to confirm stable bytes, verifies archive and manifest SHA-256 digests statically, checks schema conformance, and builds the unsigned candidate index twice to confirm deterministic output.
- **Maintainer review & signing:** Changes to permissions, host compatibility, or backend declarations appear directly in the PR diff for maintainer review. After merge to `main`, the protected release environment signs and publishes the updated catalog.
- **Backend code review (`reviews-v1.json`):** For manifest v2 modules that include a local Python backend, static validation checks package structure, while maintainer source review of a specific version is recorded explicitly via `backendReview`.

See [docs/review-policy.md](docs/review-policy.md) for full details on version checks, redirects, backend review records, and release revocation.

## Repository layout

```text
modules/    Reviewed per-module source records (<module-id>.json)
schemas/    JSON Schemas for source records, registry-v1, and reviews-v1
keys/       Public Ed25519 key records corresponding to Lumina's trusted key set
src/        Catalog builder, static package inspector, and schema validators
scripts/    CLI entry points for source validation, diff checks, and builds
docs/       Review policy, key rotation, and capability specifications
tests/      Pytest suite covering package inspection, schemas, and signing
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

Code and tooling in this repository are licensed under the [MIT License](LICENSE). Individual Workshop modules linked in the catalog retain their own licenses.
