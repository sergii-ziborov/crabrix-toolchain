#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
"$root/scripts/verify-artifacts.sh"
[[ -f "$root/dist/toolchain.descriptor.json" ]] || {
  echo "No signed Crabrix toolchain release in dist/" >&2
  exit 1
}
python3 "$root/scripts/verify-signed-release.py" \
  --dist "$root/dist" --keys "$root/keys/production-keyring.json"
echo "Signed source-built toolchain release smoke passed"
