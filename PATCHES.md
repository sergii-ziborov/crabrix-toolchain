# Backend patches

## 0001: narrow integer casts

Source: `compiler/rustc_codegen_cranelift/clif2wasm/src/ops.rs` in the pinned Rust fork. The exact patch bytes and SHA-256 are recorded in [`toolchain.lock.json`](toolchain.lock.json).

The previous app compiler failed while emitting `aho-corasick` (`uextend.i16` from an i8), `regex-automata` (`ireduce.i8` from an i16), and `itoa` (the same reduction). The patch keeps narrow CLIF integers in wasm i32 values, masks a signed i8-to-i16 extension to 16 bits, and masks i16-to-i8 and i128-to-narrow reductions. It does not change the guest language or accepted package policy.

The patch applies cleanly to the selected source and its diff matches the locked file. Functional compatibility is **pending** a successful own compiler build followed by the app's real dependency Check/Run tests. Do not describe `regex` or `serde_json` as supported based on this source change alone. If this code is merged upstream, remove the patch in a separately tested source revision update.

## 0002: install Cranelift into the bootstrap sysroot

Source: `src/bootstrap/src/core/build_steps/compile.rs` at the same pinned Rust revision. The bootstrap builds `rustc_codegen_cranelift` but does not put it in the stage1 compiler's `codegen-backends` directory when Cranelift is the only enabled backend. The stage1 compiler then fails while building its standard library. This patch uses the existing backend build and sysroot-copy helpers before that standard-library step. The recipe also sets `CG_CLIF_FORCE_GNU_AS=1`: without LLVM in this build, Cranelift must send inline assembly to the Linux host assembler instead of invoking a missing LLVM backend.

The patch is a bootstrap correction for this source-pinned candidate. A complete compiler and app compatibility result are still pending. If the selected Rust fork gains a supported Cranelift-only bootstrap path, remove this patch with a fresh source lock and tests.
