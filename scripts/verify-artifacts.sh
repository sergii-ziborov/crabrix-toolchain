#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$root/scripts/validate-lock.py"
[[ -f "$root/dist/SHA256SUMS" ]] || { echo "No source-built release artifacts exist" >&2; exit 1; }
if command -v sha256sum >/dev/null; then
  (cd "$root/dist" && sha256sum -c SHA256SUMS)
elif command -v shasum >/dev/null; then
  (cd "$root/dist" && shasum -a 256 -c SHA256SUMS)
else
  echo "Need sha256sum or shasum to verify release checksums" >&2
  exit 1
fi
python3 "$root/scripts/verify_artifacts.py" "$root/dist"
