# Changelog

## Unreleased

- Forked the MIT builder at `d7c1a08a60816ed824bb04f75fe79fa797996deb`.
- Pinned the selected Rust source and all Git submodule revisions.
- Removed floating-branch and wild default-branch build paths.
- Added source lock validation and deterministic artifact packaging tools.
- Selected a Cranelift-only candidate bootstrap after the matching CI LLVM archive became unavailable; an initial source LLVM attempt produced no toolchain artifact.
- Added a digest-pinned backend patch for observed narrow integer conversion gaps; heavy-crate compatibility is pending a new compiler build and Check/Run results.
- Made the deterministic sysroot ZIP compatible with the app's manifest reader and added a package-level ZIP/inventory verifier.
- Added an isolated, explicitly marked candidate artifact staging path for compatibility tests; release builds require a clean committed builder checkout.
- Added a pinned-base Linux x86_64 Docker candidate and an 8 GiB build preflight.
- Verified the Rust source, WASI SDK, bootstrap archives and offline Cargo vendor tree; the extra rustfmt bootstrap archives are now locked.
- Recorded the input-preparation evidence in `docs/BUILD-STATUS-2026-09-30.md`.
- No source-built Crabrix toolchain release has been produced yet.
