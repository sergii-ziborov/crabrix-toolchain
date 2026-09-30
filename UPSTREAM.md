# Upstream provenance

- Builder fork: <https://github.com/AngelOnFira/wasm-rustc>
- Baseline commit: `d7c1a08a60816ed824bb04f75fe79fa797996deb`
- License: MIT, preserved in [`LICENSE`](LICENSE)
- Former release for functional comparison: `artifacts-test-7`, 22 July 2026
- Rust source fork selected for the first own build: <https://github.com/AngelOnFira/rust> at `abc48c0b8aba37d3f3862a9d5c76eb4e78f90e88`

The old `build-local.sh` followed `bjorn3/rust`'s moving branch and fell back to wild-linker's default branch when its revision could not be parsed. The July workflow used `AngelOnFira/rust` instead. Neither floating recipe is used for a Crabrix release. The old script and workflow remain accessible in Git history.

The selected Rust source was the latest observed commit before the `artifacts-test-7` workflow ran. No build log establishes the actual Rust SHA used by that binary, so the mapping is labelled inferred. The source's `src/version` is `1.96.0`; the compiler artifact carries `1.96.0-dev` strings. Exact `rustc -Vv` from the own build is pending.

The source's bootstrap config requested a prebuilt CI LLVM artifact, but its URL returned HTTP 404 on 30 September 2026. The new pipeline uses the exact `src/llvm-project` Git submodule revision from `toolchain.lock.json`, with `llvm.download-ci-llvm=false`. This changes the bootstrap path and requires a fresh compatibility gate.
