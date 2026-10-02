# Third-party notices for toolchain assets

The builder recipe is MIT licensed; see the root [`LICENSE`](../LICENSE). The notices in `third-party/` are copied from the exact source revisions identified in [`toolchain.lock.json`](../toolchain.lock.json), and the deterministic release `licenses.zip` includes this directory. They retain the original authors' terms; public access to this repository does not relicense Rust, LLVM, WASI SDK or Cranelift.

| Files | Source revision and path |
| --- | --- |
| `RUST-*` | `AngelOnFira/rust` `abc48c0b8aba37d3f3862a9d5c76eb4e78f90e88`, repository root |
| `CRANELIFT-*` | same Rust revision, `compiler/rustc_codegen_cranelift/` |
| `COMPILER-BUILTINS-*` | same Rust revision, `library/compiler-builtins/LICENSE.txt` |
| `LLVM-*` | Rust's pinned `src/llvm-project` submodule `1cb4e3833c1919c2e6fb579a23ac0e2b22587b7e`, `llvm/LICENSE.TXT` |
| `WASI-SDK-*` | `WebAssembly/wasi-sdk` `249054e5427023344c1906afde0e9073714d1930`, root `LICENSE` |
| `WASI-LIBC-*` | that SDK's `src/wasi-libc` submodule `2fc32bc81b9f07f8d9525edea59bfbaf760c06d6`, root license files |

The `toolchain-2026-10-02.1` release also includes `vendor-notices.zip`, a
deterministic inventory of all 1592 vendored Rust packages used by the locked
build. It contains 2628 notice files plus an index with each package name,
version, declared license expression, source of the notice and file digest.
For 142 packages that publish no separate license file in their crate archive,
the index identifies pinned standard SPDX texts for their declared expression.
Three additional notices from the pinned WASI libc source are included.
The exact standard-text and source-notice inputs are in
[`release-notices/`](../release-notices/README.md). The public verifier checks
the archive against the source lock, its index and all member digests.

This inventory preserves source notices; it does not relicense any dependency
under this builder's MIT license. Additional third-party terms remain attached
to their components and source repositories.
