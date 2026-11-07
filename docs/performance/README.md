# Compiler build profile investigation — 2026-10-24

The locked fork’s `bootstrap.toml` selects upstream `profile = "compiler"`. That profile is intended for compiler contributors. Its explicit defaults enable compiler debug assertions and logging, disable LTO, retain frame pointers, and enable bootstrap incremental rebuilding. The root `rust.debug = false` setting does not override those other explicit fields. See the independently recorded [named-profile merge](bootstrap-profile-2026-10-24.json) and upstream bootstrap configuration code at the locked source revision.

These are compiler-build settings. The evidence establishes inherited configuration; a new compiled artifact and device timing are still required to establish its effect.

A separate candidate invocation now applies explicit performance settings to both bootstrap commands:

```sh
scripts/build-toolchain.sh --candidate --performance-profile
```

The candidate disables compiler-development assertions/logging, uses ThinLTO, omits forced frame pointers and disables bootstrap incremental compilation. It keeps normal optimization enabled. Exact overrides and source/profile hashes are saved to `work/logs/compiler-performance-profile.json`.

Normal `--locked` and plain `--candidate` invocations retain their existing behavior. The existing candidate marker prevents packaging these experiment outputs as a locked production release. The app’s signed compiler has not been replaced by this recipe, and no 30-second claim is made.

Build prerequisites remain a controlled Linux x86_64 environment, at least 8 GiB RAM and 30 GiB free disk; no GitHub Actions are enabled. `audit-build-profile.py` runs on the source checkout alone and rejects unreviewed included configuration files.

The physical target and reproducible Kameo/Tokio driver live in the app repository under `docs/benchmarks/kameo-actors`. Procedural macro loading and persistent guest incremental-cache locking are separate compatibility requirements.

## Manual macOS compiler-only candidate

`scripts/build-macos-compiler-candidate.py` is a separate experiment for the
explicitly started **Compiler performance candidate (manual)** Xcode Cloud
workflow. It cross-compiles the WASI rustc using the pinned source,
four checksum-verified patches, the source's pinned Darwin stage0 manifest and
checksum-verified WASI SDK 32. A native stage1 compiler built from the same
source is required before cross-compiling its standard library and stage2 WASI
compiler. The intermediate Darwin compiler uses external LLVM 22.1.8; the final
WASI compiler has only Cranelift. Building native LLVM from source and
repackaging the target sysroot are outside this path.
It applies the same performance overrides listed above.

The script requires a fresh work/output directory and 30 GiB free. It records
the complete command, hashes and provenance and emits progress every 30 seconds.
`--plan` prints inputs without fetching or compiling. It never alters the Linux
release recipe, the app's signed toolchain, or production release inventories.

This is an unqualified candidate until the app's separate test bundle proves
compatibility with the signed target sysroot and representative diagnostics and
programs. A successful Cloud build is not an iPhone performance measurement.

### Whole-compiler LTO comparison

The macOS candidate accepts `--lto thin|fat`, with the measured ThinLTO
baseline remaining the default. `--lto fat` is a separate experimental build:
the pinned bootstrap applies whole-program LTO to the stage2 WASI compiler.
All other source, patch, SDK, target-backend and sysroot constraints stay the
same, and the exact setting is retained in the artifact's provenance. The
underlying Cargo release profile already uses optimization level 3; simply
changing `rust.optimize = true` to `3` would not introduce another optimization.
No speedup is asserted until the resulting artifact passes the app's gates and
a matched physical measurement.

### Physical qualification, October 25

The full-LTO artifact is 79,051,505 bytes, SHA256
`8f1b313ccb59bf43546e36cfcdbd04dac9b5c8388a6ffec23efe2148564c17e6`.
The app snapshot `7c0bbf1`, using runtime source `2b97c92`, passed six
physical iPhone 13 mini/iOS 26.5 gates with this artifact and the signed target
sysroot. The isolated cold Tokio `rt,sync,time,io-util` profile took 29.778 s,
with all dependency artifacts uncached and output checked. This individual
sample does not establish the large Kameo/30-second acceptance target; general
macro loading remains unsupported. These artifacts have not been promoted
into the signed production toolchain. See the
[app evidence](https://github.com/sergii-ziborov/Crabrix/blob/915cc1df41814c9c3637fd1a9366b7f50ad87888/docs/performance/2026-10-25-direct-emission.json)
for device, thermal, correctness and timing limits.

### Completed cold repeats, October 25

Two same-process physical iPhone repeats passed with fresh root source and all three dependency artifacts asserted uncached: **27.881 s** and **28.537 s**, nominal thermal state at both ends. Both checked `tokio offline: 42`; 2/2 runs, zero failures. The first six-gate session measured 29.778 s. These are the selected Tokio `rt,sync,time,io-util` profile, not the unchanged 32-package Kameo target or Axum. Evidence: app `build/compiler-optimization-20261024/direct-emission-cold-repeat-device.xcresult`; machine-readable public record `docs/performance/2026-10-25-direct-emission.json`.
