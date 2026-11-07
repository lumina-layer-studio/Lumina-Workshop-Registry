# Optional project snapshot capability

Module manifests may declare `projectSnapshots` with protocol `1` and a nonempty, unique list of at most 32 schema names (each at most 128 characters). This declaration requires the existing `project.storage` permission. Invalid declarations fail package validation before catalog publication.

The field describes the module's ability to capture current unsaved state and transactionally restore a host `.lum` document. It does not grant file access, introduce code from a project file, or change registry signature and release ownership. Existing packages without this field remain valid.

Validation: all 122 registry tests passed, including capability validation and existing package/release contracts. No source record, signed catalog, release asset or published endpoint is changed here. Companion protocol: [Workshop SDK PR #3](https://github.com/lumina-layer-studio/Lumina-Workshop-SDK/pull/3).
