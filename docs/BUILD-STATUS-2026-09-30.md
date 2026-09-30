# Toolchain build status — 2026-09-30

This record covers input preparation on an Apple Silicon Mac using Docker Desktop's `linux/amd64` emulation. It does not represent a source-built compiler release.

## Identities

- Rust source: `abc48c0b8aba37d3f3862a9d5c76eb4e78f90e88` (`1.96.0-dev`). All 12 Git submodules matched `toolchain.lock.json`.
- Local candidate builder image ID: `sha256:b82320d0f0c28f7ae2b0cacfad950582da63bee178715e5d8fa93aa5efac48b1` (`linux/amd64`, 560,024,788 bytes). This is a local image ID, not a published registry manifest digest.
- Builder base: Ubuntu 24.04 amd64 manifest `sha256:496754492fb28b4d3049432f2ca787449331e23fb14f0dd3fffea86bf5a93eb4`.
- WASI SDK: 32.0, downloaded archive matched the SHA-256 in the lock.
- Bootstrap: beta rustc, standard library, Cargo, rustfmt and matching nightly rustc matched both the lock and pinned Rust `src/stage0` checksums.

## Executed checks

| Check | Result |
| --- | --- |
| `docker buildx build --platform linux/amd64 --load -t crabrix-toolchain-builder:local -f docker/Dockerfile .` | Passed; local candidate image created |
| `docker run --platform linux/amd64 ... uname -m` | Passed; reported `x86_64` |
| `python3 scripts/validate-lock.py --source-only` | Passed |
| `./scripts/fetch-sources.sh --locked` in the candidate image | Passed, including an idempotent rerun and archive checksum checks |
| `./scripts/vendor-deps.sh --locked` in the candidate image | Passed; Rust `x.py vendor` completed and pinned rustfmt archives verified |
| Cargo `metadata --locked --offline` using the vendored tree | Passed for Rust root (673 packages), library (53), Cranelift (673), and Cargo (506) |
| `bash -n` for changed shell scripts; `git diff --check` | Passed |
| `./scripts/doctor.sh` in the candidate image | Expected refusal: Docker VM exposed 1,974 MiB, below the recipe's 8 GiB preflight |

The first vendoring attempts exposed missing rustfmt bootstrap inputs, an unsupported `file://` URL in the Rust bootstrap downloader, the need for WASI SDK `clang++` during sanity checks, and the fact that `x.py vendor` does not write `.cargo/config.toml`. The recipe now pins those extra archives, separates explicit fetch and vendoring phases, provides the SDK and writes the vendor config. Cargo resolves the tested workspaces offline; full build network isolation remains unverified. The final full vendoring command passed after those fixes.

## Still required

- Increase memory available to the Linux builder and reserve enough disk for source LLVM plus Rust. The current Docker Desktop VM had about 2 GiB RAM and disk free space fell below 20 GiB during input preparation. The [Rust compiler guide](https://rustc-dev-guide.rust-lang.org/building/prerequisites.html) recommends at least 8 GiB RAM and 30 GiB free disk for a compiler build; this recipe builds LLVM from source as well.
- Produce and distribute a fixed builder image, then record its pullable image digest and tool versions in `toolchain.lock.json`. The local candidate image ID alone does not close the release environment lock.
- Run `build-toolchain.sh`, packaging, artifact verification, two clean build comparison, and Crabrix Check/Run/Cargo integration gates. None of these has passed yet; no `rustc.wasm` or sysroot release was produced.

Before preparation, 12.18 GB of regenerable Docker build cache was pruned. No simulator, Docker volume, project container, or user file was deleted. A SweepLoom CLI dry run over this task's work directory returned no generated cleanup candidates.
