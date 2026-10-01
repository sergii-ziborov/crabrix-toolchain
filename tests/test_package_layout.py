import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "package_toolchain", ROOT / "scripts/package_toolchain.py"
)
PACKAGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGER)
VERIFY_SPEC = importlib.util.spec_from_file_location(
    "verify_artifacts", ROOT / "scripts/verify_artifacts.py"
)
VERIFIER = importlib.util.module_from_spec(VERIFY_SPEC)
VERIFY_SPEC.loader.exec_module(VERIFIER)


class PackageLayoutTests(unittest.TestCase):
    def test_sysroot_archive_is_deterministic_and_app_readable(self):
        with tempfile.TemporaryDirectory(prefix="crabrix-sysroot-layout-") as temporary:
            root = Path(temporary)
            files = {}
            for name, data in (
                ("lib/rustlib/wasm32-wasip1/lib/libstd-test.rlib", b"std"),
                ("lib/rustlib/wasm32-wasip1/lib/self-contained/crt1-command.o", b"crt"),
            ):
                path = root / "inputs" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                files[name] = path

            first = root / "sysroot-wasip1.zip"
            second = root / "second.zip"
            inventory = PACKAGER.write_sysroot_archive(files, first)
            self.assertEqual(inventory, PACKAGER.write_sysroot_archive(files, second))
            self.assertEqual(first.read_bytes(), second.read_bytes())

            with zipfile.ZipFile(first) as archive:
                self.assertEqual(archive.namelist(), sorted([*files, "manifest.json"]))
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest, {"files": sorted(files)})
                self.assertTrue(all(archive.getinfo(name).date_time == (1980, 1, 1, 0, 0, 0)
                                    for name in archive.namelist()))
                for entry in inventory:
                    payload = archive.read(entry["path"])
                    self.assertEqual(len(payload), entry["bytes"])
                    self.assertEqual(hashlib.sha256(payload).hexdigest(), entry["sha256"])

            (root / "sysroot-files.json").write_text(json.dumps({
                "schemaVersion": 1, "files": inventory,
            }))
            checksum = root / "sysroot-wasip1.sha256"
            checksum.write_text(hashlib.sha256(first.read_bytes()).hexdigest() + "\n")
            self.assertEqual(VERIFIER.verify_sysroot(root), len(inventory))
            checksum.write_text("0" * 64 + "\n")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                VERIFIER.verify_sysroot(root)


if __name__ == "__main__":
    unittest.main()
