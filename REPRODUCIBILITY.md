# Reproducibility method

The source lock is validated before a release build. `fetch-sources.sh --locked` verifies Git revisions and downloaded SHA-256 bytes. `vendor-deps.sh --locked` materializes Cargo dependencies from the checked-in lockfiles as a separate network phase, and the build requires that vendor tree and Cargo offline mode. `apply-patches.sh --locked` checks every patch digest and requires each resulting tracked source diff to match its pinned patch exactly. The build compiles LLVM from the pinned Rust submodule and uses the verified prebuilt stage0 compiler. Cranelift global assembly uses GNU `as`, recorded in the lock and selected by the build script. The exact completed Linux amd64 builder image and public image archive are pinned in `toolchain.lock.json`; rebuilding [`docker/Dockerfile`](docker/Dockerfile) against live Ubuntu packages could give different package versions. The build uses `SOURCE_DATE_EPOCH` from the pinned Rust commit, UTC and C locale. The packager writes sorted ZIP entries with fixed 1980 timestamps and fixed file permissions.

Release build and packaging commands require a clean committed builder checkout. Artifact provenance records the actual builder Git commit, its dirty flag, the upstream baseline commit, source-lock digest, and whether output is a candidate. Candidate staging writes only to ignored `work/candidate-artifacts/` and includes an explicit warning file in its checksummed output.

`build-toolchain.sh --candidate` checks the complete source lock and the same host resource limits, then marks trial output before compilation. The release build and packager refuse that directory; use a separate clean work directory for `--locked`. Candidate output cannot enter `dist/` or be published as a release.

The patch applicator checks every exact patched file in candidate mode. The locked release mode also scans all tracked source changes and rejects files outside the declared patches. The broader scan is expensive through x86 emulation over a macOS bind mount, so candidate runs use the narrow check after a host-side full diff check.

Run two builds in separate clean directories with the same lock and environment. Preserve both raw compiler/sysroot hashes, logs, host tool versions and output inventories. If hashes differ, inspect archive metadata, build paths, generated code and custom Wasm sections before making any stripping change. The current packager deliberately keeps all Wasm custom sections until their compatibility and diagnostic impact is tested.

The earlier upstream recipe used prebuilt CI LLVM. Its matching archive is unavailable, so this release builds LLVM from the pinned submodule alongside Cranelift. A source-pinned build may differ from `artifacts-test-7`; compatibility is shown by app tests, not inferred from version names.

## First release comparison, 2 October 2026

Two separate directories started with no compiled build outputs. Both used
builder input `079b2dabbac02f8e5de452765c4bb89e0c4fc6ff`, source-lock
SHA-256 `7c44029b80757b80fe5bfb54614bc09e967917506bc28a275dc694eb404bf97a`,
Rust commit `abc48c0b8aba37d3f3862a9d5c76eb4e78f90e88`, and Docker image ID
`sha256:b82320d0f0c28f7ae2b0cacfad950582da63bee178715e5d8fa93aa5efac48b1`.
The second directory retained two SHA-verified rustfmt bootstrap archive inputs
after its first local-mirror lookup failed; it was reset before compilation and
contained no compiled outputs. The first directory's preexisting candidate
`dist/` file was quarantined before `x.py install` produced the release compiler.

| Artifact | First build, used in app gates | Second build |
| --- | --- | --- |
| `rustc.wasm` SHA-256 | `0286dc52064283ef78ba153a554d86ae742e6c8cd638aea8662e07d3529233fc` | `a14e50fc0421ff52d1e1b6812d8e760f108283b3bf37a9ce9a07edddac23be6a` |
| sysroot ZIP SHA-256 | `085fece5602fdd3af4efde3e08388090928c33b03fc874d99aba741a0b85283b` | `2ede8a0afc35c9b33ee3392b8eb66ea5175ab407a46b64d17e6874679a6e0794` |

The compiler files have the same length. Their only different Wasm section is
data: replacing the 568 embedded `release-1` source-root tokens with
`release-2` in a diagnostic copy makes the complete modules identical. Neither
release artifact was rewritten. The ZIPs have the same names and order; 20
`.rmeta` and 20 `.rlib` files differ. All `.rlib` members retain equal Wasm
code sections; metadata identities and, in six object members, data and
`.llvmbc` sections differ. The app-readable manifest and two self-contained
WASI files match. See the signed release's
[`reproducibility-results.json`](https://github.com/sergii-ziborov/crabrix-toolchain/releases/download/toolchain-2026-10-02.1/reproducibility-results.json)
and `build-log-summary.txt` for the precise result.

This is a **source-pinned**, functionally tested release. Raw binary
reproducibility is not established. A future build may remap the source root
before compilation and then repeat the two-build comparison and app gates.
