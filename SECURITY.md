# Security

Report vulnerabilities privately to the repository owner through GitHub's private vulnerability reporting when available. Do not attach credentials, private app projects, signing keys or user data to public issues.

Release inputs are pinned and verified before extraction. Unknown revisions, missing digests, unavailable bootstrap archives and unpinned build environments stop the build. The normal source build has no publishing credential. A protected publish step must sign the external artifact descriptor after functional and provenance verification. The app verifies signature and hashes before bundling compiler assets; phones do not download compiler updates.

The compiler still processes untrusted Rust source inside the app's Wasm runtime. Runtime memory, fuel, deadlines, filesystem rights, output quotas and cancellation are enforced by the app/runtime integration, not by a toolchain archive signature alone.
