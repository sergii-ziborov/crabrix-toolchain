#!/usr/bin/env python3
"""Inspect inherited Rust bootstrap settings without starting a compiler build."""
import argparse
import hashlib
import json
from pathlib import Path
import tomllib

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("source", type=Path)
parser.add_argument("--performance-profile", action="store_true")
args = parser.parse_args()
source = args.source.resolve()
config_path = source / "bootstrap.toml"
config = tomllib.loads(config_path.read_text())
if config.get("include"):
    parser.error("included bootstrap configs require an explicit audit before using this helper")
profile = config.get("profile")
if not isinstance(profile, str) or not profile.replace("-", "").isalnum():
    parser.error("expected one named upstream bootstrap profile")
defaults_path = source / "src/bootstrap/defaults" / f"bootstrap.{profile}.toml"
defaults = tomllib.loads(defaults_path.read_text())
# Bootstrap fills unspecified fields from the named profile; explicit fields win.
inherited = dict(defaults.get("rust", {}))
inherited.update(config.get("rust", {}))
overrides = {
    "optimize": True,
    "debug-assertions": False,
    "debug-assertions-std": False,
    "debug-assertions-tools": False,
    "debug-logging": False,
    "incremental": False,
    "frame-pointers": False,
    "lto": "thin",
} if args.performance_profile else {}
effective = inherited | overrides
print(json.dumps({
    "source": str(source),
    "bootstrapSHA256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
    "profile": profile,
    "profileDefaultsSHA256": hashlib.sha256(defaults_path.read_bytes()).hexdigest(),
    "mergedRustSettings": inherited,
    "candidateOverrides": overrides,
    "settingsAfterOverrides": effective,
    "scope": "raw named-profile merge and explicit overrides; not a completed bootstrap build",
}, indent=2, sort_keys=True))
