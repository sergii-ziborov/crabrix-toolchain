# Bundled native compiler candidate

This build path translates **only the bundled, trusted `rustc.wasm`** into C with WABT 1.0.42. Clang compiles that C for the actual destination Apple SDK. The resulting static library is linked into the signed app executable. User projects, build scripts and downloaded procedural macro crates continue to execute as WasmKit guests. There is no JIT, runtime native-code download or dynamic native-library loader.

This directory is a candidate implementation. Generated provenance keeps `candidate: true` and `productionReplacement: false`. A generated archive or a successful host benchmark alone does not qualify an app release.

## Rebuild

1. Obtain two independently built, matching WASM compiler/sysroot candidates from the approved `macos-wasi-rpc-fat-2026-10-25` recipe.
2. Run `scripts/build-native-compiler-source.py` for each input, using the pinned official WABT archive. Fresh output directories are required.
3. Run `scripts/package-native-compiler-source.py`. It checks every C/header hash and requires matching translations with distinct original Cloud build IDs.
4. Run `scripts/compile-native-compiler.py --source /path/to/verified-native-source --output build/native-iphoneos --sdk iphoneos --target arm64-apple-ios18.0 --jobs 2`. Select the actual Xcode installation through `DEVELOPER_DIR`. The object inventory, Clang version, SDK, flags and final archive digest are retained. Host objects must never be relabelled as iOS objects.
5. Run the real iPhone compiler, procedural macro, Stop, memory, responsiveness and offline WebKit gates before enabling a production app input. Measure cold dependencies separately from cache reuse.

When a phone is unavailable, use `--sdk iphonesimulator --target arm64-apple-ios18.0-simulator` and a separate output directory for a simulator test library. Its object platform and executable ABI symbols are checked before linking. Simulator timings describe the host Mac and cannot satisfy the physical iPhone performance gate. The app enables this backend only in an explicit test build with Swift conditions `CRABRIX_NATIVE_COMPILER` and `CRABRIX_LEGACY_FIXTURES`, C definition `CRABRIX_NATIVE_COMPILER_SIMULATOR=1`, and `CRABRIX_NATIVE_COMPILER_CANDIDATE_LIBRARY` pointing to the verified library.

All source files and notices are public build inputs. The app fetches neither this archive nor the static library while running. A build Mac may fetch pinned release assets before Xcode signs the final executable.

## Native guards

- Explicit WABT linear-memory bounds checks; signal-based traps are disabled.
- At most 2 GiB compiler linear memory, with separate smaller WasmKit limits for user programs and macros.
- One owned native compiler invocation at a time, on a 32 MiB worker stack.
- Function/loop checkpoints charge finite work, poll cancellation and check the native stack margin. Work is a checkpoint budget, not a claim of native instruction counting.
- Clang rejects frames above 128 KiB. A 512 KiB margin protects the next stack prologue; a separate 4,096-call depth limit remains enabled.
- Native C objects retain frame pointers but omit unwind tables: all traps use the guarded C ABI, and very large generated functions exceed Apple's compact-unwind offset encoding. Swift and Objective-C app objects retain their ordinary unwind metadata.
- Every native exported operation installs its own C trap frame, including reentrant procedural macro dispatch. Swift callbacks report errors by returning. No `longjmp` crosses Swift frames.
- WASI checks declared guest ranges and nested vectors before obtaining unsafe memory views. Blocking polls use bounded wait slices when configured with cancellation.
- The instance's tables and memory are freed after completion or a trap; the process-wide immutable WABT type registry remains alive for later invocations.

`tests/native_compiler_guards.c` exercises the actual wrapper with a hostile mock module: work exhaustion, Stop polling, out-of-bounds traps, reentrant traps, stack margin, the memory ceiling and repeated teardown. This mock is never shipped in the app and never stands in for real compiler acceptance.

## Licenses

WABT runtime: copyright WebAssembly Community Group participants, Apache-2.0. See `WABT-LICENSE.txt`. Original runtime source notices remain intact. The source package documents Crabrix's added checkpoints and platform guards. Rust and compiler dependencies retain the separately published toolchain notice inventory and license archives.
