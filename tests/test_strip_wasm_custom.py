import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "strip_wasm_custom", ROOT / "scripts/strip-wasm-custom.py"
)
STRIPPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STRIPPER)


def section(identifier, payload):
    assert len(payload) < 128
    return bytes((identifier, len(payload))) + payload


def custom(name, payload):
    encoded = name.encode("utf-8")
    return section(0, bytes((len(encoded),)) + encoded + payload)


class StripWasmCustomTests(unittest.TestCase):
    def test_only_name_and_debug_sections_are_removed(self):
        preserved = [section(1, b"\x00"), custom("producers", b"origin"),
                     custom("target_features", b"+simd"), section(10, b"code"),
                     custom("project.provenance", b"author")]
        removed = [custom("name", b"names"), custom(".debug_info", b"debug")]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, destination = root / "in.wasm", root / "out.wasm"
            source.write_bytes(STRIPPER.MAGIC + b"".join(preserved[:2] + removed + preserved[2:]))
            dropped = STRIPPER.strip(source, destination)
            self.assertEqual([name for name, _ in dropped], ["name", ".debug_info"])
            self.assertEqual(destination.read_bytes(), STRIPPER.MAGIC + b"".join(preserved))

    def test_rejects_truncated_section_without_leaving_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, destination = root / "bad.wasm", root / "out.wasm"
            source.write_bytes(STRIPPER.MAGIC + b"\x0a\x08code")
            with self.assertRaisesRegex(ValueError, "exceeds input size"):
                STRIPPER.strip(source, destination)
            self.assertFalse(destination.exists())

    def test_rejects_in_place_edit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "same.wasm"
            path.write_bytes(STRIPPER.MAGIC)
            with self.assertRaisesRegex(ValueError, "different"):
                STRIPPER.strip(path, path)
            self.assertEqual(path.read_bytes(), STRIPPER.MAGIC)


if __name__ == "__main__":
    unittest.main()
