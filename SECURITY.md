# Security

Report vulnerabilities privately to the repository owner through GitHub's private vulnerability reporting when available. Do not attach credentials, private app projects, signing keys or user data to public issues.

Release inputs are pinned and verified before extraction. Unknown revisions, missing digests, unavailable bootstrap archives and unpinned build environments stop the build. The normal source build has no publishing credential. The protected publish step signs the exact descriptor payload bytes with Ed25519 under the `Crabrix.ToolchainDescriptor.v1\n` domain, after source-lock, sysroot, notices, compatibility and two-build comparison checks. The production private key is outside this repository; only its public key is in [`keys/production-keyring.json`](keys/production-keyring.json). Untrusted pull requests do not receive the key. The app verifies signature and exact hashes before bundling compiler assets; phones do not download compiler updates.

The compiler still processes untrusted Rust source inside the app's Wasm runtime. Runtime memory, fuel, deadlines, filesystem rights, output quotas and cancellation are enforced by the app/runtime integration, not by a toolchain archive signature alone.
