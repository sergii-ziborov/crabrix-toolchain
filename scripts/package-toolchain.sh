#!/usr/bin/env bash
set -euo pipefail
[[ "${1:-}" == --deterministic ]] || { echo "usage: $0 --deterministic" >&2; exit 2; }
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$root/scripts/validate-lock.py"
work="${CRABRIX_TOOLCHAIN_WORK:-$root/work}"
if [[ -e "$work/.candidate-build" ]]; then
  echo "Candidate build outputs cannot be packaged; build --locked in a fresh work directory." >&2
  exit 1
fi
python3 "$root/scripts/package_toolchain.py"
