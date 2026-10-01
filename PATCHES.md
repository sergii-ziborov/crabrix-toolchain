# Backend patches

## 0001: narrow integer casts and high multiplication dispatch

Source: `compiler/rustc_codegen_cranelift/clif2wasm/src/ops.rs` in the pinned Rust fork. The exact patch bytes and SHA-256 are recorded in [`toolchain.lock.json`](toolchain.lock.json).

The previous app compiler failed while emitting `aho-corasick` (`uextend.i16` from an i8), `regex-automata` (`ireduce.i8` from an i16), and `itoa` (the same reduction). The patch keeps narrow CLIF integers in wasm i32 values, masks a signed i8-to-i16 extension to 16 bits, and masks i16-to-i8 and i128-to-narrow reductions. It does not change the guest language or accepted package policy.

The first source-built candidate passed E0502 and Check/Run for all 46 Academy Examples. A cold dependency-rich app then progressed through 15 crates and exposed a missing `smulhi.i64` lowering while compiling `clap_builder 4.5.50`. The revised patch dispatches CLIF `umulhi` and `smulhi` through the helpers in patch 0002. The revised compiler is being built and is not yet a passing heavy-crate candidate.

## 0002: upper half of i64 multiplication

Source: `compiler/rustc_codegen_cranelift/clif2wasm/src/i128_lower.rs` in the same pinned Rust fork. The exact patch bytes and SHA-256 are recorded in the lock.

Core Wasm has no widening i64 multiply. This patch exposes the already used carry-correct 32-bit partial-product calculation as `umulhi64` and derives the signed high half by subtracting one cross term for each negative operand. The signed and unsigned arithmetic was compared with independent Python arbitrary-precision products for 20,100 edge and seeded random pairs. The actual rebuilt Wasm compiler and an app-level checked-multiplication regression still need to pass.

If either change is merged upstream, remove its patch in a separately tested source revision update. A source fix alone does not establish support for `clap`, `regex`, or `serde_json`.

An earlier bootstrap sysroot patch was removed. It assumed Cranelift must be installed as a separate dynamic library, but the selected Rust fork's `rustc_features` enables Cranelift in `rustc-main` and `rustc_interface::get_codegen_backend` calls the linked backend directly. The WASI build produced only an `.rlib`; the patch caused bootstrap to panic while looking for a `.so`. The source LLVM candidate uses the unmodified upstream bootstrap path.
