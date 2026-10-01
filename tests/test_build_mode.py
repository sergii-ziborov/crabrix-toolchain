import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BuildModeTests(unittest.TestCase):
    def test_candidate_outputs_cannot_be_packaged_after_lock_completion(self):
        with tempfile.TemporaryDirectory(prefix="crabrix-package-guard-") as temporary:
            root = Path(temporary)
            (root / "scripts").mkdir()
            for name in ("package-toolchain.sh", "validate-lock.py"):
                shutil.copy2(ROOT / "scripts" / name, root / "scripts" / name)
            shutil.copytree(ROOT / "patches", root / "patches")

            # The synthetic environment identity reaches the packaging guard.
            # It is never used to build or publish an artifact.
            lock = json.loads((ROOT / "toolchain.lock.json").read_text())
            lock["buildEnvironment"] = {
                "imageDigest": "0" * 64,
                "hostToolVersions": {"test-host": "1"},
            }
            (root / "toolchain.lock.json").write_text(json.dumps(lock))
            work = root / "work"
            work.mkdir()
            (work / ".candidate-build").write_text("trial\n")

            result = subprocess.run(
                [str(root / "scripts/package-toolchain.sh"), "--deterministic"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("Candidate build outputs cannot be packaged", result.stderr)


if __name__ == "__main__":
    unittest.main()
