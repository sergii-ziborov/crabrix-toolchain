#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
"$root/scripts/verify-artifacts.sh"
echo "App runtime Check/Run/Cargo compatibility must be exercised by the Crabrix integration pipeline." >&2
exit 1
