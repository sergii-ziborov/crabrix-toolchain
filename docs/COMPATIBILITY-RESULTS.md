# Toolchain compatibility results v1

`compatibility-results.json` is a release artifact, created only after the
source-built compiler and sysroot have been tested on the candidate app/runtime.
It is signed by the external descriptor along with the referenced redacted
evidence files. The signing tool checks structure, artifact hashes, required
gate status, and the presence of evidence files. A protected release job must
still verify that each result came from an actual completed run.

Required shape (the example values below are placeholders, not a passing run):

```json
{
  "schemaVersion": 1,
  "rustcSHA256": "<64 lowercase hex characters for rustc.wasm>",
  "sysrootSHA256": "<64 lowercase hex characters for sysroot-wasip1.zip>",
  "appRevision": "<40 lowercase hex characters>",
  "runtimeRevision": "<40 lowercase hex characters>",
  "gates": [
    {
      "id": "T01",
      "status": "passed",
      "evidence": ["validation/T01-source-lock.txt"]
    }
  ]
}
```

Record one unique gate object for each of T01–T06. Every required gate must be
`passed`, with at least one `validation/` evidence file included in the same
release. Additional failed or unrun observations may be listed separately and
must not be silently rewritten as passes. T03 may report either matching raw
digests or an examined difference report; it cannot claim bit reproduction from
source pins alone. T05 must name the exact app and runtime revisions used for
the Crabrix Check/Run, E0502, root-feature, real-crate, offline and Vendor gates.
Redact personal machine paths, credentials, user projects and private device
identifiers from public evidence.
