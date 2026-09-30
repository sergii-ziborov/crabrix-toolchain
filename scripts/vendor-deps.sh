#!/usr/bin/env bash
set -euo pipefail
[[ "${1:-}" == --locked ]] || { echo "usage: $0 --locked" >&2; exit 2; }
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$root/scripts/validate-lock.py" --source-only
work="${CRABRIX_TOOLCHAIN_WORK:-$root/work}"
rust="$work/rust"
[[ -d "$rust/.git" && -d "$work/mirror" ]] || {
  echo "run fetch-sources.sh --locked first" >&2
  exit 1
}
expected="$(python3 - "$root/toolchain.lock.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['rust']['revision'])
PY
)"
[[ "$(git -C "$rust" rev-parse HEAD)" == "$expected" ]] || {
  echo "Rust source checkout differs from toolchain.lock.json" >&2
  exit 1
}
sdk_name="$(python3 - "$root/toolchain.lock.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['wasiSDK']['url'].rsplit('/',1)[-1])
PY
)"
sdk_dir="$rust/wasi-sdk-32.0-x86_64-linux"
if [[ ! -x "$sdk_dir/bin/clang++" ]]; then
  tar -xzf "$work/downloads/$sdk_name" -C "$rust"
fi
export WASI_SDK_PATH="$sdk_dir"
export WASI_SYSROOT="$sdk_dir/share/wasi-sysroot"
export CARGO_HOME="$work/cargo-home"
mkdir -p "$CARGO_HOME"
# Rust bootstrap's Rust downloader accepts HTTP(S), while its Python stage0
# downloader also accepts file://. The compiler archives are already in the
# checked mirror; rustfmt and its matching nightly rustc are fetched here.
export RUSTUP_DIST_SERVER="https://static.rust-lang.org"
export TZ=UTC
export LC_ALL=C
mkdir -p "$work/logs"
(
  cd "$rust"
  python3 x.py vendor 2>&1 | tee "$work/logs/vendor-deps.log"
)
python3 - "$root/toolchain.lock.json" "$rust" <<'PY'
import hashlib,json,pathlib,sys
lock=json.load(open(sys.argv[1]))
rust=pathlib.Path(sys.argv[2])
fmt=lock['bootstrap']['rustfmt']
stage0=(rust/'src/stage0').read_text()
for name,item in fmt['components'].items():
    archive=rust/'build/cache'/fmt['date']/item['url'].rsplit('/',1)[-1]
    if not archive.is_file(): raise SystemExit(f'missing pinned rustfmt bootstrap archive: {name}')
    digest=hashlib.sha256()
    with archive.open('rb') as source:
        for chunk in iter(lambda: source.read(1024*1024),b''): digest.update(chunk)
    if digest.hexdigest()!=item['sha256']:
        raise SystemExit(f'rustfmt bootstrap SHA-256 mismatch: {name}')
    stage0_entry=f"dist/{fmt['date']}/{archive.name}={item['sha256']}"
    if stage0_entry not in stage0.splitlines():
        raise SystemExit(f'rustfmt bootstrap lock differs from pinned src/stage0: {name}')
print('Pinned rustfmt and matching nightly rustc archives verified')
PY
mkdir -p "$rust/.cargo"
cat > "$rust/.cargo/config.toml" <<'TOML'
[source.crates-io]
replace-with = "vendored-sources"

[source."git+https://github.com/rust-lang/team"]
git = "https://github.com/rust-lang/team"
replace-with = "vendored-sources"

[source.vendored-sources]
directory = "vendor"
TOML
stage0_bin="$rust/build/x86_64-unknown-linux-gnu/stage0/bin"
for manifest in Cargo.toml library/Cargo.toml compiler/rustc_codegen_cranelift/Cargo.toml src/tools/cargo/Cargo.toml; do
  (cd "$rust" && env CARGO_NET_OFFLINE=true RUSTC_BOOTSTRAP=1 \
    PATH="$stage0_bin:$PATH" "$stage0_bin/cargo" metadata \
    --manifest-path "$manifest" --locked --offline --format-version 1 >/dev/null)
  echo "Resolved offline: $manifest"
done
git -C "$rust" diff --ignore-submodules=all --exit-code || {
  echo "vendoring changed tracked Rust source; inspect the diff before building" >&2
  exit 1
}
[[ -d "$rust/vendor" && -f "$rust/.cargo/config.toml" ]] || {
  echo "vendoring did not produce the expected vendor tree/config" >&2
  exit 1
}
echo "Rust workspace dependencies materialized; inspect vendor-deps.log and package checksums before an offline build."
