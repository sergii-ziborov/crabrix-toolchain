import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("candidate_builder", ROOT / "scripts/build-macos-compiler-candidate.py")
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)
import verify_artifacts


class CandidateSysrootTests(unittest.TestCase):
    def test_captures_source_built_public_api_with_a_matching_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root / "rust", root / "artifact"
            library = source / "build/aarch64-apple-darwin/stage1/lib/rustlib/wasm32-wasip1/lib"
            (library / "self-contained").mkdir(parents=True)
            output.mkdir()
            for name in ("libstd-probe.rlib", "libproc_macro-probe.rlib", "librustc_literal_escaper-probe.rlib",
                         "self-contained/libc.a", "self-contained/crt1-command.o", "librustc_driver-private.rlib"):
                (library / name).write_bytes(name.encode())
            result = BUILDER.export_candidate_sysroot(source, output, "arm64")
            self.assertEqual(verify_artifacts.verify_sysroot(output), 6)
            self.assertEqual(result["fileCount"], 6)
            exported = output / "sysroot-wasip1/lib/rustlib/wasm32-wasip1/lib"
            self.assertEqual((exported / "libproc_macro-probe.rlib").read_bytes(), b"libproc_macro-probe.rlib")
            self.assertFalse((exported / "librustc_driver-private.rlib").exists())
            manifest = json.loads((output / "sysroot-wasip1/manifest.json").read_text())
            self.assertEqual(len(manifest["files"]), 5)

    def test_never_substitutes_stage0_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root / "rust", root / "artifact"
            (source / "build/aarch64-apple-darwin/stage0/lib").mkdir(parents=True)
            output.mkdir()
            with self.assertRaisesRegex(ValueError, "stage1"):
                BUILDER.export_candidate_sysroot(source, output, "arm64")
            library = source / "build/aarch64-apple-darwin/stage1/lib/rustlib/wasm32-wasip1/lib"
            library.mkdir(parents=True)
            (root / "outside").write_bytes(b"outside")
            (library / "libstd-probe.rlib").symlink_to(root / "outside")
            with self.assertRaisesRegex(ValueError, "symlink"):
                BUILDER.export_candidate_sysroot(source, output, "arm64")


if __name__ == "__main__":
    unittest.main()
