# Reproducibility method

The source lock is validated before a release build. `fetch-sources.sh --locked` verifies Git revisions and downloaded SHA-256 bytes. A controlled Linux environment digest is still needed. The build uses `SOURCE_DATE_EPOCH` from the pinned Rust commit, UTC, C locale and offline Cargo mode. The packager writes sorted ZIP entries with fixed 1980 timestamps and fixed file permissions.

Run two builds in separate clean directories with the same lock and environment. Preserve both raw compiler/sysroot hashes, logs, host tool versions and output inventories. If hashes differ, inspect archive metadata, build paths, generated code and custom Wasm sections before making any stripping change. The current packager deliberately keeps all Wasm custom sections until their compatibility and diagnostic impact is tested.

The earlier upstream recipe used prebuilt CI LLVM. Its matching archive is unavailable, so this version builds the pinned LLVM source. A source-pinned build may differ from `artifacts-test-7`; compatibility must be shown by tests. Bit-identical reproducibility is not claimed until two independent builds match.
