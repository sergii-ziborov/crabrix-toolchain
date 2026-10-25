import base64
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import qualified_macos as policy


class QualifiedMacTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.dist = Path(self.temporary.name)
        self.spec = policy.profile()
        for name, data in [("rustc.wasm", b"\0asm\1\0\0\0test fixture"),
                           ("sysroot-wasip1.zip", b"unit fixture, not a real sysroot")]:
            (self.dist / name).write_bytes(data)
        inventory = {"schemaVersion": 1, "files": [
            {"path": f"sysroot-wasip1/lib/rustlib/wasm32-wasip1/lib/lib{crate}-fixture.rlib"}
            for crate in ("std", "core", "alloc", "compiler_builtins", "proc_macro", "rustc_literal_escaper")
        ]}
        inventory["files"] += [{"path": "sysroot-wasip1/lib/rustlib/wasm32-wasip1/lib/self-contained/" + name}
                               for name in ("libc.a", "crt1-command.o")]
        inventory["files"] += [{"path": f"sysroot-wasip1/unit-fixture-{number}"}
                               for number in range(self.spec["sysrootFileCount"] - len(inventory["files"]))]
        (self.dist / "sysroot-files.json").write_text(json.dumps(inventory))
        self.sources = [self.source(f"00000000-0000-4000-8000-{number:012d}") for number in (1, 2)]
        self.provenance = {
            "candidate": False, "productionReplacement": True,
            "buildProfile": policy.PROFILE_ID, "qualificationWorkingTreeClean": True,
            "qualificationSourceCommit": "c" * 40,
            "qualificationProfileSHA256": policy.digest(policy.PROFILE),
            "builderSourceCommit": self.spec["recipeCommit"],
            "sourceLockSHA256": self.spec["sourceLockSHA256"],
            "rustRevision": self.spec["rustRevision"], "rustVersion": self.spec["rustVersion"],
        }
        self.repro = {
            "schemaVersion": 2, "buildProfile": policy.PROFILE_ID, "status": "identical",
            "sourceLockSHA256": self.spec["sourceLockSHA256"],
            "qualificationProfileSHA256": policy.digest(policy.PROFILE),
            "builderSourceCommit": self.spec["recipeCommit"], "outputTarget": "wasm32-wasip1",
            "independentCloudBuildIDs": sorted(source["cloudBuildID"] for source in self.sources),
            "compilerSHA256": policy.digest(self.dist / "rustc.wasm"),
            "sysrootArchiveSHA256": policy.digest(self.dist / "sysroot-wasip1.zip"),
            "sysrootInventorySHA256": policy.digest(self.dist / "sysroot-files.json"),
            "compilerRawMatch": True, "sysrootRawMatch": True, "inventoryRawMatch": True,
        }
        import check_compatibility
        self.compat = {
            "schemaVersion": 1, "status": "passed",
            "compilerSHA256": policy.digest(self.dist / "rustc.wasm"),
            "sysrootArchiveSHA256": policy.digest(self.dist / "sysroot-wasip1.zip"),
            "runtimeRevision": "a" * 40, "appBuildInputCommit": "b" * 40,
            "environment": {"configuration": "Release", "platform": "iOS device", "dispatch": "software-direct"},
            "gates": [{"id": name, "test": "BundledCompilerGateTests/testUnitFixture",
                       "executed": 1, "passed": 1, "failed": 0, "skipped": 0}
                      for name in sorted(check_compatibility.REQUIRED | set(self.spec["requiredAdditionalGates"]))],
        }

    def source(self, build_id):
        settings = dict(self.spec["settings"], **{key: json.dumps(value) for key, value in policy.PATH_SETTINGS.items()})
        return {
            "candidate": True, "productionReplacement": False,
            "toolchainRepositoryCommit": self.spec["recipeCommit"],
            "rustRevision": self.spec["rustRevision"], "rustVersion": self.spec["rustVersion"],
            "configSourceSHA256": self.spec["configSourceSHA256"],
            "patchDigests": self.spec["basePatchDigests"],
            "stage0ManifestSHA256": self.spec["stage0ManifestSHA256"],
            "sdk": self.spec["sdk"], "nativeLLVM": self.spec["nativeLLVM"],
            "experimentalProcMacroBridge": {"schemaVersion": 1,
                "patch": "0005-wasi-proc-macro-bridge.candidate.patch",
                "sha256": self.spec["bridgePatchSHA256"], "compilerOptInEnvironment": "CRABRIX_WASM_PROC_MACROS=1"},
            "settings": settings,
            "command": ["/fixture/python3.13", "x.py", "build", "compiler/rustc", "--stage", "2", "--jobs", "3"]
                + [item for key, value in settings.items() for item in ("--set", f"{key}={value}")],
            "cloudBuildID": build_id, "compilerBuildSeconds": 1.0,
            "compilerSHA256": policy.digest(self.dist / "rustc.wasm"),
            "compilerBytes": (self.dist / "rustc.wasm").stat().st_size,
            "candidateSysroot": {"sourceStage": "build/aarch64-apple-darwin/stage1/lib/rustlib/wasm32-wasip1/lib",
                "fileCount": self.spec["sysrootFileCount"], "archiveSHA256": policy.digest(self.dist / "sysroot-wasip1.zip"),
                "inventorySHA256": policy.digest(self.dist / "sysroot-files.json")},
        }

    def check(self):
        self.provenance["sourceBuilds"] = []
        for source in self.sources:
            data = (json.dumps(source, indent=2) + "\n").encode()
            self.provenance["sourceBuilds"].append({"provenanceBase64": base64.b64encode(data).decode(),
                                                  "provenanceSHA256": hashlib.sha256(data).hexdigest()})
        for name, data in [("toolchain-provenance.json", self.provenance),
                           ("reproducibility-results.json", self.repro),
                           ("compatibility-results.json", self.compat)]:
            (self.dist / name).write_text(json.dumps(data))
        return policy.check(self.dist, ROOT / "toolchain.lock.json")

    def test_accepts_qualified_record_without_relabeling_raw_candidates(self):
        self.assertEqual(self.check()["status"], "identical")
        self.assertTrue(all(source["candidate"] is True for source in self.sources))

    def test_rejects_changed_sources_flags_or_claimed_origin(self):
        cases = [
            lambda s: s.update(candidate=False),
            lambda s: s.update(toolchainRepositoryCommit="d" * 40),
            lambda s: s["experimentalProcMacroBridge"].update(sha256="0" * 64),
            lambda s: s["settings"].update({"rust.lto": "off"}),
            lambda s: s["command"].append("--unrecorded-option"),
            lambda s: s["candidateSysroot"].update(sourceStage="stage0"),
            lambda s: s["candidateSysroot"].update(archiveSHA256="e" * 64),
        ]
        original = copy.deepcopy(self.sources[1])
        for change in cases:
            self.sources[1] = copy.deepcopy(original)
            change(self.sources[1])
            with self.assertRaises(ValueError): self.check()

    def test_rejects_one_build_reused_twice(self):
        self.sources[1] = copy.deepcopy(self.sources[0])
        with self.assertRaisesRegex(ValueError, "independent"): self.check()

    def test_rejects_unsigned_policy_change_dirty_qualification_and_unknown_profile(self):
        original = copy.deepcopy(self.provenance)
        for key, value in [("qualificationProfileSHA256", "0" * 64),
                           ("qualificationWorkingTreeClean", False), ("buildProfile", "unapproved")]:
            self.provenance = copy.deepcopy(original)
            self.provenance[key] = value
            with self.assertRaises(ValueError): self.check()

    def test_rejects_missing_skipped_or_token_only_macro_acceptance(self):
        original = copy.deepcopy(self.compat)
        for change in (lambda c: c.update(gates=[g for g in c["gates"] if g["id"] != "serde-derive"]),
                       lambda c: c["gates"][0].update(skipped=1),
                       lambda c: c["environment"].update(dispatch="token")):
            self.compat = copy.deepcopy(original)
            change(self.compat)
            with self.assertRaises(ValueError): self.check()

    def test_rejects_modified_artifacts_and_misreported_reproducibility(self):
        self.repro["compilerRawMatch"] = False
        with self.assertRaises(ValueError): self.check()
        self.repro["compilerRawMatch"] = True
        (self.dist / "rustc.wasm").write_bytes(b"\0asm\1\0\0\0different")
        with self.assertRaises(ValueError): self.check()


if __name__ == "__main__": unittest.main()
