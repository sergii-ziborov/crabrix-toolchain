# Upstream provenance

- Builder fork: <https://github.com/AngelOnFira/wasm-rustc>
- Baseline commit: `d7c1a08a60816ed824bb04f75fe79fa797996deb`
- License: MIT, preserved in [`LICENSE`](LICENSE)
- Former release for functional comparison: `artifacts-test-7`, 22 July 2026
- Rust source fork selected for the first own build: <https://github.com/AngelOnFira/rust> at `abc48c0b8aba37d3f3862a9d5c76eb4e78f90e88`
- WASI SDK 32.0 source association: <https://github.com/WebAssembly/wasi-sdk> tag `wasi-sdk-32`, peeled commit `249054e5427023344c1906afde0e9073714d1930`; pinned `src/wasi-libc` commit `2fc32bc81b9f07f8d9525edea59bfbaf760c06d6`. The downloaded SDK archive is verified separately by SHA-256 in the lock.

The old `build-local.sh` followed `bjorn3/rust`'s moving branch and fell back to wild-linker's default branch when its revision could not be parsed. The July workflow used `AngelOnFira/rust` instead. Neither floating recipe is used for a Crabrix release. The old script and workflow remain accessible in Git history.

The selected Rust source was the latest commit on `riw-wasm20` before the successful [22 July workflow run](https://github.com/AngelOnFira/wasm-rustc/actions/runs/29926092091) started at 13:55 UTC. That run's log shows a checkout of `riw-wasm20`, but does not print the checkout SHA; the mapping to `abc48c0b8aba37d3f3862a9d5c76eb4e78f90e88` remains an inference, not binary provenance. The source's `src/version` is `1.96.0`; the source-built candidate carries `1.96.0-dev` strings. Exact `rustc -Vv` output is still to be recorded before release.

The source's bootstrap config requested a prebuilt CI LLVM artifact, but its URL returned HTTP 404 on 30 September 2026. The current candidate pins `rust.codegen-backends=["llvm","cranelift"]`, sets `llvm.download-ci-llvm=false`, and builds LLVM from the pinned `src/llvm-project` submodule instead. The prebuilt stage0 Rust compiler is SHA-256 verified. This changed bootstrap path requires a fresh compatibility gate.

The stopped Cranelift-only trial needed the fork's `CLIF2WASM_LENIENT=1` mode while producing WASI sysroot metadata and emitted more than one thousand unresolved-symbol trap stubs. Those experimental objects are not release inputs. The source-LLVM candidate does not enable lenient mode; its first build passed app E0502 and 46 Academy Examples but reached another backend lowering gap during a dependency-rich Cargo build. [PATCHES.md](PATCHES.md) records the revised candidate patch and its pending regression gate.
