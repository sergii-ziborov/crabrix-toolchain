# Crabrix toolchain

Crabrix builds the Rust compiler and `wasm32-wasip1` standard library used by the native Crabrix app from pinned Rust sources. This repository carries the build recipe, source lock, packaging tools, and release verification gates. It is a fork of [AngelOnFira/wasm-rustc](https://github.com/AngelOnFira/wasm-rustc), with upstream history and MIT terms preserved.

The compiler is a Rust fork with Cranelift and in-process `riwl` linking. It runs as a WebAssembly module inside the reviewed app; course downloads cannot update or replace it. The Rust compiler itself is upstream-derived software, not a new Crabrix compiler implementation.

## Build inputs

[`toolchain.lock.json`](toolchain.lock.json) pins the builder and Rust source commits, 12 Git submodules, WASI SDK 32 digest, bootstrap Rust archives, target, and packaging version. The selected Rust revision is `abc48c0b8aba37d3f3862a9d5c76eb4e78f90e88`, which declares version `1.96.0-dev`. Its association with the old `artifacts-test-7` binary is an inference from the July 2026 workflow chronology, not proven binary provenance.

The recipe's CI LLVM archive for that source revision is no longer available. This fork selects the pinned LLVM source submodule instead. A controlled Linux x86_64 build environment must be pinned and the resulting compiler must pass the app's Check/Run/Cargo gates before a release can be made. There is currently **no Crabrix-produced release artifact**.

## Commands

Source pin verification (works on macOS or Linux):

```sh
python3 scripts/validate-lock.py --source-only
```

Production build sequence on a controlled Linux x86_64 host with enough RAM and disk:

```sh
./scripts/doctor.sh
./scripts/fetch-sources.sh --locked
./scripts/build-toolchain.sh --locked
./scripts/package-toolchain.sh --deterministic
./scripts/verify-artifacts.sh
./scripts/smoke-toolchain.sh
```

The full sequence is intentionally fail-closed while `buildEnvironment.imageDigest` is unresolved; `doctor.sh` reports the missing lock field. `fetch-sources.sh --locked` can already materialize pinned Rust source, submodules, SDK and bootstrap compiler inputs for investigation. These commands are not presented as a completed smoke result.

`package-toolchain.sh` emits unstripped `rustc.wasm`, deterministic `sysroot-wasip1.zip`, per-file SHA-256 inventory, source provenance and checksums after a successful own build. Signing is a separate protected release step. No source-built output is copied from the previous `artifacts-test-7` release.

## Compatibility and verification

The intended output target is `wasm32-wasip1`. Functional release gates cover Crabrix Check and Run, E0502 diagnostics, root features, a real crate, offline compilation, and Vendor. Two independent clean builds must be compared; identical raw digests are not claimed in advance. See [REPRODUCIBILITY.md](REPRODUCIBILITY.md) and [SECURITY.md](SECURITY.md).

The MIT license applies to this builder recipe. Rust, LLVM, WASI SDK and their dependencies retain their own licenses. [licenses/README.md](licenses/README.md) identifies the notice collection required for each produced release. See [UPSTREAM.md](UPSTREAM.md) for the exact fork baseline and recipe changes.
