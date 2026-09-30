#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$root/scripts/validate-lock.py"
[[ -f "$root/dist/SHA256SUMS" ]] || { echo "No source-built release artifacts exist" >&2; exit 1; }
(cd "$root/dist" && sha256sum -c SHA256SUMS)
