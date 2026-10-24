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
