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

The exact third-party dependency set in a produced compiler still needs an artifact-level notice audit before publication. These primary notices are a starting inventory, not a claim that every vendored dependency is covered.
