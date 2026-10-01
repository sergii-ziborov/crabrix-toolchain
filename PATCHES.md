# Backend patches

## 0001: narrow integer casts and high multiplication dispatch

Source: `compiler/rustc_codegen_cranelift/clif2wasm/src/ops.rs` in the pinned Rust fork. The exact patch bytes and SHA-256 are recorded in [`toolchain.lock.json`](toolchain.lock.json).

The previous app compiler failed while emitting `aho-corasick` (`uextend.i16` from an i8), `regex-automata` (`ireduce.i8` from an i16), and `itoa` (the same reduction). The patch keeps narrow CLIF integers in wasm i32 values, masks a signed i8-to-i16 extension to 16 bits, and masks i16-to-i8 and i128-to-narrow reductions. A second candidate reached `regex-automata 0.4.18` and failed on `bswap.i128`. The patch now lowers that byte swap to two 64-bit swaps with the halves exchanged. It does not change the guest language or accepted package policy.

The first source-built candidate passed E0502 and Check/Run for all 46 Academy Examples. A cold dependency-rich app then progressed through 15 crates and exposed a missing `smulhi.i64` lowering while compiling `clap_builder 4.5.50`. The revised patch dispatches CLIF `umulhi` and `smulhi` through the helpers in patch 0002. The second source-built candidate is `61478aefaa4d26e1de217dcf427b68d09203695f9055b92689011014bcd61e16`; its app-level checked-multiplication regression passed on iOS 18.2 Release Simulator (one executed test, zero failures, 4.625 seconds). The four-crate CLI then failed in `regex-automata` on `bswap.i128` after 515.204 seconds. The third source-built candidate, `e7c94685d0f6cc217d57f9d1ae1d2b005ddd718f03f6ff30bfa1596730aae775`, passed the exact byte-swap regression, standalone `regex 1.13.1`, the complete three-file four-crate CLI with exact output, and all 46 Academy Examples on iOS 18.2 Release Simulator. Device and release gates remain separate.

## 0002: upper half of i64 multiplication

Source: `compiler/rustc_codegen_cranelift/clif2wasm/src/i128_lower.rs` in the same pinned Rust fork. The exact patch bytes and SHA-256 are recorded in the lock.

Core Wasm has no widening i64 multiply. This patch exposes the already used carry-correct 32-bit partial-product calculation as `umulhi64` and derives the signed high half by subtracting one cross term for each negative operand. The signed and unsigned arithmetic was compared with independent Python arbitrary-precision products for 20,100 edge and seeded random pairs. The rebuilt Wasm compiler then passed an app-level checked-multiplication regression that had failed on the first candidate with `smulhi.i64`.

If either change is merged upstream, remove its patch in a separately tested source revision update. The app gates above establish the tested `clap` and `regex` versions only. They do not establish `serde_json`, whose current `serde_core` needs build-script generated output.

An earlier bootstrap sysroot patch was removed. It assumed Cranelift must be installed as a separate dynamic library, but the selected Rust fork's `rustc_features` enables Cranelift in `rustc-main` and `rustc_interface::get_codegen_backend` calls the linked backend directly. The WASI build produced only an `.rlib`; the patch caused bootstrap to panic while looking for a `.so`. The source LLVM candidate uses the unmodified upstream bootstrap path.
