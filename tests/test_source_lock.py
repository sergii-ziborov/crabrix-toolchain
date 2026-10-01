import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_lock", ROOT / "scripts/validate-lock.py")
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class SourceLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = json.loads((ROOT / "toolchain.lock.json").read_text())

    def test_source_only_checks_all_available_source_inputs(self):
        self.assertEqual(VALIDATOR.validate(self.lock, source_only=True), [])

        broken = copy.deepcopy(self.lock)
        broken["bootstrap"]["rustfmt"]["components"]["rustfmt"]["sha256"] = "branch-main"
        errors = VALIDATOR.validate(broken, source_only=True)
        self.assertTrue(any("bootstrap.rustfmt.rustfmt.sha256" in error for error in errors))

        broken = copy.deepcopy(self.lock)
        broken["bootstrap"]["llvm"]["sourceCommit"] = self.lock["rust"]["revision"]
        errors = VALIDATOR.validate(broken, source_only=True)
        self.assertTrue(any("must match pinned LLVM submodule" in error for error in errors))

        broken = copy.deepcopy(self.lock)
        broken["patchDigests"][0]["sha256"] = "0" * 64
        errors = VALIDATOR.validate(broken, source_only=True)
        self.assertTrue(any("file missing or SHA-256 mismatch" in error for error in errors))

        broken = copy.deepcopy(self.lock)
        broken["bootstrap"]["craneliftGlobalAssembler"] = "llvm"
        errors = VALIDATOR.validate(broken, source_only=True)
        self.assertTrue(any("craneliftGlobalAssembler" in error for error in errors))

    def test_release_lock_remains_closed_without_builder_identity(self):
        errors = VALIDATOR.validate(self.lock)
        self.assertTrue(any("imageDigest" in error for error in errors))
        self.assertTrue(any("hostToolVersions" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
