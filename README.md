# Crabrix toolchain

Crabrix builds the Rust compiler and `wasm32-wasip1` standard library used by the native Crabrix app from pinned Rust sources. This repository carries the build recipe, source lock, packaging tools, and release verification gates. It is a fork of [AngelOnFira/wasm-rustc](https://github.com/AngelOnFira/wasm-rustc), with upstream history and MIT terms preserved.

The compiler is a Rust fork with Cranelift and in-process `riwl` linking. It runs as a WebAssembly module inside the reviewed app; course downloads cannot update or replace it. The Rust compiler itself is upstream-derived software, not a new Crabrix compiler implementation.

## Build inputs

[`toolchain.lock.json`](toolchain.lock.json) pins the builder and Rust source commits, 12 Git submodules, WASI SDK 32 digest, bootstrap Rust and rustfmt archives, target, and packaging version. Archive digests are also checked against the selected Rust source's `src/stage0`. The selected Rust revision is `abc48c0b8aba37d3f3862a9d5c76eb4e78f90e88`, which declares version `1.96.0-dev`. Its association with the old `artifacts-test-7` binary is an inference from the July 2026 workflow chronology, not proven binary provenance.

The recipe's CI LLVM archive for that source revision is no longer available. The current candidate therefore builds LLVM from the pinned Rust submodule and enables both LLVM and Cranelift backends. The stage0 bootstrap compiler remains a verified prebuilt input. The exact backend selection is recorded in the lock. A controlled Linux x86_64 build environment must be pinned and the resulting compiler must pass the app's Check/Run/Cargo gates before a release can be made. There is currently **no Crabrix-produced release artifact**.

The pinned [backend patches](PATCHES.md) cover narrow integer conversions observed in `aho-corasick`, `regex-automata`, and `itoa`, high-half i64 multiplication exposed by `clap_builder`, i128 byte swap exposed by `regex-automata`, sign-extended i128 comparisons, and the float-to-i128 libcall ABI. GNU `as` is selected for Cranelift inline assembly. The first source-built candidate passed app E0502 and all 46 Academy Examples on an iOS 18.2 Release Simulator, then failed the four-crate CLI at high-half multiplication. The second passed checked multiplication and a real `smallvec` crate, then failed the same CLI at i128 byte swap. The third, `e7c94685d0f6cc217d57f9d1ae1d2b005ddd718f03f6ff30bfa1596730aae775`, passed standalone `regex`, the three-file `clap`/`regex`/`hashbrown`/`smallvec` CLI, all 46 Academy Examples, and eight further compiler/Cargo/sandbox gates on the Release Simulator. The fifth candidate, `d243f2ac041ce7892da9ee7e03a361d63259645d796e67c25ce08938ecd62591`, passed its float-to-i128 regression, a multi-file route planner using `petgraph` and `itertools`, and all 46 Academy Examples in separate Release Simulator runs. [The candidate report](docs/candidate-v5-compatibility.json) records the exact gates. These results prove those workloads, not arbitrary crate support. Current `serde_core` still needs generated build-script output that the app's Cargo subset does not provide.

## Commands

Source pin verification (works on macOS or Linux):

```sh
python3 scripts/validate-lock.py --source-only
```

Production build sequence on a controlled Linux x86_64 host with enough RAM and disk:

```sh
./scripts/doctor.sh
./scripts/fetch-sources.sh --locked
./scripts/vendor-deps.sh --locked
./scripts/apply-patches.sh --locked
./scripts/build-toolchain.sh --locked
./scripts/package-toolchain.sh --deterministic
./scripts/verify-artifacts.sh
./scripts/smoke-toolchain.sh
```

The release sequence is intentionally fail-closed while `buildEnvironment.imageDigest` is unresolved. `fetch-sources.sh --locked` can materialize pinned Rust source, submodules, SDK and bootstrap compiler inputs for investigation. `vendor-deps.sh --locked` is the explicit network phase for Rust workspace crates; the later build requires its vendor tree and runs Cargo offline. Once the resource preflight passes, `./scripts/build-toolchain.sh --candidate` permits a trial source build with the pinned source inputs while the release environment lock is being finalized. It marks that work directory as a candidate before compilation. Release packaging refuses candidate outputs even if the lock is filled later; run `--locked` in a fresh work directory for a publishable build.

After a successful candidate build, `./scripts/stage-candidate.sh` creates test-only artifacts under ignored `work/candidate-artifacts/`, with an explicit candidate marker and provenance flag. It never writes `dist/` and cannot serve as a release package. This permits app compatibility probes before the controlled release build.

### Docker build host

The repository includes a candidate Linux x86_64 build environment in [`docker/Dockerfile`](docker/Dockerfile). Its Ubuntu base is pinned by an amd64 manifest digest. Build the image and verify the source lock on a Docker host:

```sh
docker buildx build --platform linux/amd64 --load \
  -t crabrix-toolchain-builder:local -f docker/Dockerfile .
docker run --rm --platform linux/amd64 \
  --mount "type=bind,src=$PWD,dst=/workspace,readonly" \
  crabrix-toolchain-builder:local \
  python3 scripts/validate-lock.py --source-only
```

The local image is a candidate, not the release build environment. Record and distribute its completed image digest before filling `buildEnvironment.imageDigest`; the lock must identify the exact image used for a source build. On Apple Silicon, Docker can run this x86_64 image through emulation, but the Docker VM still needs enough RAM and disk for Rust. The [Rust compiler development guide](https://rustc-dev-guide.rust-lang.org/building/prerequisites.html) recommends at least 8 GB RAM and 30 GB free disk for a compiler build. Do not infer a successful compiler build from a passing image or source-lock check.

`package-toolchain.sh` emits unstripped `rustc.wasm`, deterministic `sysroot-wasip1.zip` with an app-readable manifest, per-file SHA-256 inventory, ZIP checksum, source provenance and checksums after a successful own build. `verify-artifacts.sh` checks the ZIP contents against both inventories. Signing is a separate protected release step. No source-built output is copied from the previous `artifacts-test-7` release.

The separate `scripts/strip-wasm-custom.py` is a test-only size experiment. On the second candidate it removed 41,503,919 bytes of function-name and debug sections (129,337,555 → 87,833,636 bytes), while retaining `producers`, `target_features` and every executable section byte for byte. The release packager still keeps the original module until the smaller candidate passes the same compiler, diagnostics and performance gates.
Set `CRABRIX_TOOLCHAIN_STRIP_EXPERIMENT=1` only with `./scripts/stage-candidate.sh` to produce a separately checksummed candidate from the same compiler source. Its provenance records the full compiler digest and strip policy. The release packager rejects this switch. The third candidate's smaller file is 87,833,739 bytes (SHA-256 `5da690fe77625d55602e400ebdb0d57fb496c1f3e26d1376c1a8ef0e56e378bd`). On iOS 18.2 Release Simulator it passed E0502, byte swap, all 46 Academy Examples, and the three-file `clap`/`regex`/`hashbrown`/`smallvec` CLI. Five warning-Check observations per variant measured 1.37× median parse and 1.22× first Check, with essentially unchanged changed-Check time. The fixed-order Simulator samples do not establish device or whole-app speed; the stripped file remains test-only until release gates and controlled comparisons are complete.

## Compatibility and verification

The intended output target is `wasm32-wasip1`. Functional release gates cover Crabrix Check and Run, E0502 diagnostics, root features, a real crate, offline compilation, and Vendor. Two independent clean builds must be compared; identical raw digests are not claimed in advance. See [REPRODUCIBILITY.md](REPRODUCIBILITY.md) and [SECURITY.md](SECURITY.md).

The MIT license applies to this builder recipe. Rust, LLVM, WASI SDK and their dependencies retain their own licenses. [licenses/README.md](licenses/README.md) identifies the notice collection required for each produced release. See [UPSTREAM.md](UPSTREAM.md) for the exact fork baseline and recipe changes.
