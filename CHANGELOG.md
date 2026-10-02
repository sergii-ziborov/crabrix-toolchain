# Changelog

## Unreleased

- Forked the MIT builder at `d7c1a08a60816ed824bb04f75fe79fa797996deb`.
- Pinned the selected Rust source and all Git submodule revisions.
- Removed floating-branch and wild default-branch build paths.
- Added source lock validation and deterministic artifact packaging tools.
- Selected a Cranelift-only candidate bootstrap after the matching CI LLVM archive became unavailable; an initial source LLVM attempt produced no toolchain artifact.
- Added digest-pinned backend patches for observed narrow integer conversions and missing high-half i64 multiplication. The first candidate passed E0502 and all 46 Academy Examples; dependency-rich compilation needs a revised candidate and build-script support for affected crates.
- Selected GNU `as` for Cranelift inline assembly. Removed a trial bootstrap sysroot patch after it attempted to install a WASI `.so` for a statically linked backend.
- Made the deterministic sysroot ZIP compatible with the app's manifest reader and added a package-level ZIP/inventory verifier.
- Added an isolated, explicitly marked candidate artifact staging path for compatibility tests; release builds require a clean committed builder checkout.
- Added a pinned-base Linux x86_64 Docker candidate and an 8 GiB build preflight.
- Verified the Rust source, WASI SDK, bootstrap archives and offline Cargo vendor tree; the extra rustfmt bootstrap archives are now locked.
- Recorded the input-preparation evidence in `docs/BUILD-STATUS-2026-09-30.md`.
- No source-built Crabrix toolchain release has been produced yet.
