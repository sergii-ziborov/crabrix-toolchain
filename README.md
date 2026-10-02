# Crabrix toolchain

The source-built Rust compiler and `wasm32-wasip1` sysroot bundled with
[Crabrix](https://github.com/sergii-ziborov/Crabrix). This repository maintains
the pinned build recipe, source patches, artifact inventories and release
verification tools. It is a fork of
[AngelOnFira/wasm-rustc](https://github.com/AngelOnFira/wasm-rustc) with its
history and MIT terms preserved. Rust, LLVM, WASI SDK and vendored crates keep
their own licenses.

The current compiler derives from Rust source commit
`abc48c0b8aba37d3f3862a9d5c76eb4e78f90e88` (`1.96.0-dev`). It uses
Cranelift and the in-process `riwl` linker. The selected source revision's
connection to the older `artifacts-test-7` binary is inferred from the builder
history; these new artifacts are produced by this pipeline and have their own
digests. The build compiles LLVM from the pinned Rust submodule and uses a
verified prebuilt stage0 compiler and WASI SDK. It does not claim a bootstrap
from bare metal.

## Current release

[toolchain-2026-10-02.1](https://github.com/sergii-ziborov/crabrix-toolchain/releases/tag/toolchain-2026-10-02.1)
contains `rustc.wasm`, the `wasm32-wasip1` sysroot ZIP and per-file inventory,
primary and vendored notices, source lock, provenance, compatibility results,
two-build comparison, SHA-256 sums and an Ed25519 signed descriptor. The app
pins this exact release and verifies the signature and asset hashes on its
build Mac before bundling; a CoursePack cannot replace the compiler on a phone.

The release compiler passed 13 selected Release iOS 18.2 Simulator gates using
CrabrixRuntime at `d996f0d11dff54734b5670d58062e22c6e01f949`: Check,
Run, E0502, root features, offline pin, Vendor, all 46 Academy Examples,
multi-file projects using `clap`, `regex`, `hashbrown`, `smallvec`, `petgraph`
and `itertools`, Stop, bounded output and warning-cache parity. See the
[compatibility report](https://github.com/sergii-ziborov/crabrix-toolchain/releases/download/toolchain-2026-10-02.1/compatibility-results.json)
for exact tests, source and artifact identities. A separate `serde_json`
probe failed because its `serde_core` dependency needs build-script-generated
`OUT_DIR` content. Crabrix's supported Cargo subset does not execute build
scripts; success on the named crates is not a claim about arbitrary crates.

The [two-build report](https://github.com/sergii-ziborov/crabrix-toolchain/releases/download/toolchain-2026-10-02.1/reproducibility-results.json)
records raw compiler and sysroot digests from separate clean build-output
directories in the same pinned Linux amd64 image. Read its status before
claiming byte-for-byte reproducibility. The current release keeps Wasm name
and debug sections; a smaller stripped candidate remains an experiment.

## Build inputs and commands

[`toolchain.lock.json`](toolchain.lock.json) pins the builder and Rust commits,
submodules, backend patches, WASI SDK, bootstrap archives, Docker image,
target and packaging format. Missing revisions or digests stop the build. The
completed [Linux amd64 build image](https://github.com/sergii-ziborov/crabrix-toolchain/releases/tag/build-env-2026-10-02)
is pinned by ID and archive SHA-256 in the lock. The source/build pipeline
requires Linux amd64, at least 8 GiB RAM and 30 GiB free disk. On Apple
Silicon, the pinned image runs through Docker's amd64 emulation. Xcode app
archives are a separate macOS step.

Run the following inside that pinned image, with a writable repository and
a fresh `work/` directory (or set `CRABRIX_TOOLCHAIN_WORK` to another fresh
directory). Fetch and vendoring
are the explicit network phases; `build-toolchain.sh` then uses Cargo offline.

```sh
./scripts/doctor.sh --locked
./scripts/fetch-sources.sh --locked
./scripts/vendor-deps.sh --locked
./scripts/build-toolchain.sh --locked
./scripts/package-toolchain.sh --deterministic
./scripts/verify-artifacts.sh
```

To inventory vendored notices from those exact fetched sources:

```sh
python3 scripts/collect-vendor-notices.py \
  --vendor "${CRABRIX_TOOLCHAIN_WORK:-work}/rust/vendor" --lock toolchain.lock.json \
  --extra-notices release-notices/source-notices \
  --standard-licenses release-notices/spdx-v3.29.0 \
  --out dist/vendor-notices.zip
python3 scripts/verify_vendor_notices.py \
  --archive dist/vendor-notices.zip --lock toolchain.lock.json
```

The collector records every one of 1592 vendored packages, retaining original
notice files and supplementing 142 packages that have only license metadata
with SHA-pinned standard SPDX texts. The index distinguishes these sources.
See [release-notices](release-notices/README.md) and [primary notices](licenses/README.md).

The app's Release Simulator compatibility report is generated from actual
`.xcresult` bundles by `scripts/generate-compatibility.py`, not by a written
test alone. A second clean build is compared with
`scripts/compare-build-outputs.py`; the raw difference report and concise
public build summary accompany the release. Signing uses
`scripts/sign-toolchain-release.py` in a protected publish step with an
owner-only key outside this repository. Ordinary pull requests never receive
that key. The verifier requires Python 3.11+ and the pinned
[`requirements-publish.txt`](requirements-publish.txt) package. Anyone can
verify the published files:

```sh
python3 scripts/verify-signed-release.py \
  --dist dist --keys keys/production-keyring.json
./scripts/smoke-toolchain.sh
```

`smoke-toolchain.sh` is a release gate and requires the signed descriptor and
all evidence files in `dist/`. CI runs fast source-lock and script tests on
ordinary pull requests; the full Rust/LLVM build is controlled rather than
repeated on each documentation edit.

## Integration and limits

Crabrix's app repository records the toolchain ID, descriptor key, source
lock and exact compiler/sysroot digests in one release-input manifest. The
compiler and runtime ship in the reviewed app. Courses deliver readable
learning content and editable Rust source. The compiler targets
`wasm32-wasip1`; native linking, procedural macros and executable Cargo build
scripts are outside the supported on-device subset.

For the full build method and honest raw-output comparison, see
[REPRODUCIBILITY.md](REPRODUCIBILITY.md). [SECURITY.md](SECURITY.md) explains
the source and signature boundaries, [UPSTREAM.md](UPSTREAM.md) records fork
provenance, and [PATCHES.md](PATCHES.md) lists each local patch. The MIT
[LICENSE](LICENSE) covers this builder recipe, not the Rust compiler or
third-party components.
