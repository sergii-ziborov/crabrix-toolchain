#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$root/scripts/validate-lock.py" --source-only
for command in git python3 curl tar sha256sum cmake ninja gcc; do
  command -v "$command" >/dev/null || { echo "missing build tool: $command" >&2; exit 1; }
done
if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
  echo "Production build requires controlled Linux x86_64; this host can inspect the source lock only." >&2
  exit 1
fi
python3 "$root/scripts/validate-lock.py"
