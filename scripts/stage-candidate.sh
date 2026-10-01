#!/usr/bin/env bash
set -euo pipefail
[[ $# == 0 ]] || { echo "usage: $0" >&2; exit 2; }
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$root/scripts/validate-lock.py" --source-only
work="${CRABRIX_TOOLCHAIN_WORK:-$root/work}"
[[ -f "$work/.candidate-build" ]] || {
  echo "No completed or attempted candidate build marker found" >&2
  exit 1
}
CRABRIX_TOOLCHAIN_CANDIDATE=1 \
CRABRIX_TOOLCHAIN_OUT="$work/candidate-artifacts" \
  python3 "$root/scripts/package_toolchain.py"
if command -v sha256sum >/dev/null 2>&1; then
  (cd "$work/candidate-artifacts" && sha256sum -c SHA256SUMS)
else
  (cd "$work/candidate-artifacts" && shasum -a 256 -c SHA256SUMS)
fi
python3 "$root/scripts/verify_artifacts.py" "$work/candidate-artifacts"
