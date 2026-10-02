"""Catch accidental changes to the pinned third-party notice inputs."""

import hashlib
from pathlib import Path
import runpy
import unittest


ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = runpy.run_path(str(ROOT / "scripts/collect-vendor-notices.py"))


class ReleaseNoticeInputTests(unittest.TestCase):
    def test_spdx_standard_texts_match_reviewed_source_bytes(self):
        directory = ROOT / "release-notices/spdx-v3.29.0"
        expected = COLLECTOR["STANDARD_SHA256"]
        self.assertEqual({path.name for path in directory.iterdir()},
                         {name + ".txt" for name in expected})
        for name, checksum in expected.items():
            self.assertEqual(hashlib.sha256((directory / (name + ".txt")).read_bytes()).hexdigest(),
                             checksum, name)

    def test_wasi_libc_source_notices_match_reviewed_source_bytes(self):
        directory = ROOT / "release-notices/source-notices"
        expected = COLLECTOR["EXTRA_SHA256"]
        self.assertEqual({path.name for path in directory.iterdir()}, set(expected))
        for name, checksum in expected.items():
            self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(),
                             checksum, name)


if __name__ == "__main__":
    unittest.main()
