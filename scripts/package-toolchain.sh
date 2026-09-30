#!/usr/bin/env bash
set -euo pipefail
[[ "${1:-}" == --deterministic ]] || { echo "usage: $0 --deterministic" >&2; exit 2; }
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$root/scripts/validate-lock.py"
python3 "$root/scripts/package_toolchain.py"
