import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import toolchain_descriptor as descriptor


class ToolchainDescriptorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.dist = self.root / "dist"
        self.dist.mkdir()
        for name, value in {
            "rustc.wasm": b"\0asm\1\0\0\0",
            "sysroot-wasip1.zip": b"test ZIP bytes",
            "sysroot-files.json": b"{}\n",
            "SHA256SUMS": b"test fixture\n",
            "toolchain-provenance.json": json.dumps({
                "candidate": False, "builderWorkingTreeDirty": False,
                "sourceLockSHA256": "b" * 64, "rustRevision": "a" * 40,
            }).encode() + b"\n",
            "build-log-summary.txt": b"test fixture\n",
            "licenses/LICENSE": b"test fixture only\n",
        }.items():
            target = self.dist / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)
        for number in range(1, 7):
            evidence = self.dist / f"validation/T{number:02d}.txt"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text("test fixture only\n")
        (self.dist / "compatibility-results.json").write_text(json.dumps({
            "schemaVersion": 1,
            "rustcSHA256": hashlib.sha256((self.dist / "rustc.wasm").read_bytes()).hexdigest(),
            "sysrootSHA256": hashlib.sha256((self.dist / "sysroot-wasip1.zip").read_bytes()).hexdigest(),
            "appRevision": "c" * 40,
            "runtimeRevision": "d" * 40,
            "gates": [{
                "id": f"T{number:02d}", "status": "passed",
                "evidence": [f"validation/T{number:02d}.txt"],
            } for number in range(1, 7)],
        }))
        self.key = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
        public = self.key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        self.keyring = descriptor.ROOT / "tests/fixtures/test-keyring.json"
        self.assertEqual(
            json.loads(self.keyring.read_text())["keys"]["test-only"],
            base64.b64encode(public).decode("ascii"),
        )
        self.payload = (json.dumps({
            "schemaVersion": 1,
            "toolchainID": "test-toolchain",
            "target": "wasm32-wasip1",
            "rustVersion": "1.96.0-dev",
            "rustRevision": "a" * 40,
            "sourceLockSHA256": "b" * 64,
            "files": descriptor.inventory(self.dist),
        }, sort_keys=True, separators=(",", ":")) + "\n").encode()
        self.signed = self.dist / "toolchain.descriptor.json"
        self.signed.write_bytes(descriptor.envelope(self.payload, "test-only", self.key))

    def tearDown(self):
        self.temporary.cleanup()

    def verify(self):
        descriptor.verify(types.SimpleNamespace(
            dist=self.dist, descriptor=self.signed, keyring=self.keyring
        ))

    def test_valid_envelope_and_exact_file_inventory(self):
        self.verify()
        wrapper = json.loads(self.signed.read_bytes())
        self.assertEqual(base64.b64decode(wrapper["payloadBase64"]), self.payload)
        self.assertEqual(len(base64.b64decode(wrapper["signatureBase64"])), 64)

    def test_asset_tampering_is_rejected_after_signature_verification(self):
        (self.dist / "rustc.wasm").write_bytes(b"different compiler")
        with self.assertRaisesRegex(ValueError, "differ from the signed"):
            self.verify()

    def test_wrong_signature_and_domain_are_rejected(self):
        wrapper = json.loads(self.signed.read_bytes())
        wrapper["signatureBase64"] = base64.b64encode(
            self.key.sign(b"Wrong.Domain.v1\n" + self.payload)
        ).decode("ascii")
        self.signed.write_text(json.dumps(wrapper))
        with self.assertRaises(InvalidSignature):
            self.verify()

    def test_candidate_directory_cannot_be_signed(self):
        (self.dist / "CANDIDATE-NOT-FOR-RELEASE.txt").write_text("candidate\n")
        with self.assertRaisesRegex(ValueError, "candidate artifacts"):
            descriptor.payload_bytes(self.dist, "candidate")

    def test_failing_gate_is_rejected_even_with_valid_signature(self):
        results = self.dist / "compatibility-results.json"
        value = json.loads(results.read_text())
        value["gates"][-1]["status"] = "failed"
        results.write_text(json.dumps(value))
        payload = json.loads(self.payload)
        payload["files"] = descriptor.inventory(self.dist)
        signed_payload = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
        self.signed.write_bytes(descriptor.envelope(signed_payload, "test-only", self.key))
        with self.assertRaisesRegex(ValueError, "required toolchain gates"):
            self.verify()

    def test_key_from_repository_is_refused(self):
        args = types.SimpleNamespace(
            dist=self.dist, toolchain_id="test-toolchain", key_id="test-only",
            private_key=descriptor.ROOT / "tests/test-key.pem",
        )
        # Remove the vector descriptor so the key-location check is reached.
        self.signed.unlink()
        with self.assertRaisesRegex(ValueError, "outside this repository"):
            descriptor.sign(args)


if __name__ == "__main__":
    unittest.main()
