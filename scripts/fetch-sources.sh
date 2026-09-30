#!/usr/bin/env bash
set -euo pipefail
[[ "${1:-}" == --locked ]] || { echo "usage: $0 --locked" >&2; exit 2; }
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$root/scripts/validate-lock.py" --source-only
work="${CRABRIX_TOOLCHAIN_WORK:-$root/work}"
mkdir -p "$work/downloads"
read -r source_url source_revision sdk_url sdk_digest sdk_name < <(python3 - "$root/toolchain.lock.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));s=x['wasiSDK']
print(x['rust']['url'],x['rust']['revision'],s['url'],s['sha256'],s['url'].rsplit('/',1)[-1])
PY
)
if [[ ! -d "$work/rust/.git" ]]; then
  git clone --filter=blob:none "$source_url" "$work/rust"
fi
git -C "$work/rust" fetch origin "$source_revision"
git -C "$work/rust" checkout --detach "$source_revision"
[[ "$(git -C "$work/rust" rev-parse HEAD)" == "$source_revision" ]]
python3 - "$root/toolchain.lock.json" "$work/rust" <<'PY'
import json,subprocess,sys
lock=json.load(open(sys.argv[1])); root=sys.argv[2]
for path,sha in lock['submodules'].items():
    line=subprocess.check_output(['git','ls-tree','HEAD',path],cwd=root,text=True).strip()
    if not line.startswith(f'160000 commit {sha}\t'):
        raise SystemExit(f'submodule pin mismatch: {path}')
print('Rust revision and all Git submodule pins match')
PY
git -C "$work/rust" submodule update --init --recursive
archive="$work/downloads/$sdk_name"
if [[ ! -f "$archive" ]]; then curl -fL --retry 3 -o "$archive.part" "$sdk_url" && mv "$archive.part" "$archive"; fi
echo "$sdk_digest  $archive" | sha256sum -c -
python3 - "$root/toolchain.lock.json" "$work" <<'PY'
import hashlib,json,pathlib,sys,urllib.request
lock=json.load(open(sys.argv[1]));work=pathlib.Path(sys.argv[2])
date=lock['bootstrap']['compilerDate']
for name,item in lock['bootstrap']['compiler'].items():
    url=item['url']; digest=item['sha256']; target=work/'downloads'/url.rsplit('/',1)[-1]
    if not target.exists():
        part=target.with_suffix(target.suffix+'.part')
        urllib.request.urlretrieve(url,part)
        part.replace(target)
    actual=hashlib.sha256(target.read_bytes()).hexdigest()
    if actual!=digest: raise SystemExit(f'bootstrap {name}: SHA-256 mismatch')
    mirror=work/'mirror'/'dist'/date/target.name
    mirror.parent.mkdir(parents=True,exist_ok=True)
    if not mirror.exists(): mirror.symlink_to(target)
print('Pinned bootstrap rustc/std/cargo archives fetched and verified')
PY
python3 - "$root/toolchain.lock.json" "$work/rust" <<'PY'
import hashlib,json,pathlib,sys
lock=json.load(open(sys.argv[1]));rust=pathlib.Path(sys.argv[2])
actual=hashlib.sha256((rust/'bootstrap.toml').read_bytes()).hexdigest()
if actual!=lock['bootstrap']['configSourceSHA256']:
    raise SystemExit('bootstrap.toml does not match locked source config')
PY
echo "Pinned source, submodules, SDK and bootstrap compiler assets fetched; build host identity is checked separately."
