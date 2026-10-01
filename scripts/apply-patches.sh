#!/usr/bin/env bash
set -euo pipefail
[[ "${1:-}" == --locked && $# == 1 ]] || { echo "usage: $0 --locked" >&2; exit 2; }
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$root/scripts/validate-lock.py" --source-only
work="${CRABRIX_TOOLCHAIN_WORK:-$root/work}"
rust="$work/rust"
[[ -d "$rust/.git" ]] || { echo "run fetch-sources.sh --locked first" >&2; exit 1; }
expected="$(python3 - "$root/toolchain.lock.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['rust']['revision'])
PY
)"
[[ "$(git -C "$rust" rev-parse HEAD)" == "$expected" ]] || {
  echo "Rust source checkout differs from toolchain.lock.json" >&2
  exit 1
}
patch_relative="$(python3 - "$root/toolchain.lock.json" <<'PY'
import json,sys
paths=json.load(open(sys.argv[1]))['backend']['patches']
if len(paths)!=1: raise SystemExit('this recipe expects one pinned backend patch')
print(paths[0])
PY
)"
patch="$root/$patch_relative"
if git -C "$rust" apply --reverse --check "$patch" 2>/dev/null; then
  echo "Pinned backend patch already applied"
else
  git -C "$rust" apply --check "$patch"
  git -C "$rust" apply "$patch"
  echo "Applied pinned backend patch"
fi
git -C "$rust" diff --check
if ! git -C "$rust" diff --binary --ignore-submodules=all | cmp -s - "$patch"; then
  echo "Rust source has tracked changes beyond the exact pinned backend patch" >&2
  exit 1
fi
