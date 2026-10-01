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
patch_relatives=()
while IFS= read -r patch_relative; do
  patch_relatives+=("$patch_relative")
done < <(python3 - "$root/toolchain.lock.json" <<'PY'
import json,sys
paths=json.load(open(sys.argv[1]))['backend']['patches']
if not paths: raise SystemExit('at least one pinned source patch is required')
print('\n'.join(paths))
PY
)
targets=()
validation_dir="$(mktemp -d)"
trap 'rm -rf "$validation_dir"' EXIT
GIT_INDEX_FILE="$validation_dir/index" git -C "$rust" read-tree HEAD
for patch_relative in "${patch_relatives[@]}"; do
  patch="$root/$patch_relative"
  target="$(python3 - "$patch" <<'PY'
import pathlib,sys
paths=[line[6:] for line in pathlib.Path(sys.argv[1]).read_text().splitlines() if line.startswith('+++ b/')]
if len(paths)!=1 or paths[0].startswith('/') or '..' in pathlib.PurePosixPath(paths[0]).parts:
    raise SystemExit('expected one relative source patch target')
print(paths[0])
PY
  )"
  # Build the expected cumulative source in a separate Git index. More than
  # one pinned patch may touch the same source file.
  GIT_INDEX_FILE="$validation_dir/index" git -C "$rust" apply --cached "$patch"
  if git -C "$rust" apply --reverse --check "$patch" 2>/dev/null; then
    echo "Pinned source patch already applied: $patch_relative"
  else
    git -C "$rust" apply --check "$patch"
    git -C "$rust" apply "$patch"
    echo "Applied pinned source patch: $patch_relative"
  fi
  git -C "$rust" diff --check -- "$target"
  targets+=("$target")
done
for target in "${targets[@]}"; do
  expected_blob="$(GIT_INDEX_FILE="$validation_dir/index" git -C "$rust" rev-parse ":$target")"
  actual_blob="$(git -C "$rust" hash-object "$target")"
  [[ "$actual_blob" == "$expected_blob" ]] || {
    echo "Rust source differs from the cumulative pinned patches: $target" >&2
    exit 1
  }
done
if [[ "$mode" == --locked ]]; then
  changed="$(git -C "$rust" diff --name-only --ignore-submodules=all | LC_ALL=C sort)"
  expected_changes="$(printf '%s\n' "${targets[@]}" | LC_ALL=C sort -u)"
  [[ "$changed" == "$expected_changes" ]] || {
    echo "Rust source has tracked changes beyond pinned source patches" >&2
    exit 1
  }
fi
