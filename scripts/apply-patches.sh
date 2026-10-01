#!/usr/bin/env bash
set -euo pipefail
mode="${1:-}"
[[ $# == 1 && ( "$mode" == --locked || "$mode" == --candidate ) ]] || {
  echo "usage: $0 --locked|--candidate" >&2
  exit 2
}
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
target="$(python3 - "$patch" <<'PY'
import pathlib,sys
paths=[line[6:] for line in pathlib.Path(sys.argv[1]).read_text().splitlines() if line.startswith('+++ b/')]
if len(paths)!=1 or paths[0].startswith('/') or '..' in pathlib.PurePosixPath(paths[0]).parts:
    raise SystemExit('expected one relative backend patch target')
print(paths[0])
PY
)"
if git -C "$rust" apply --reverse --check "$patch" 2>/dev/null; then
  echo "Pinned backend patch already applied"
else
  git -C "$rust" apply --check "$patch"
  git -C "$rust" apply "$patch"
  echo "Applied pinned backend patch"
fi
git -C "$rust" diff --check -- "$target"
if ! git -C "$rust" diff --binary -- "$target" | cmp -s - "$patch"; then
  echo "Rust backend source differs from the exact pinned patch" >&2
  exit 1
fi
if [[ "$mode" == --locked ]]; then
  changed="$(git -C "$rust" diff --name-only --ignore-submodules=all)"
  [[ "$changed" == "$target" ]] || {
    echo "Rust source has tracked changes beyond the pinned backend patch" >&2
    exit 1
  }
fi
