#!/usr/bin/env bash
set -euo pipefail
[[ "${1:-}" == --locked ]] || { echo "usage: $0 --locked" >&2; exit 2; }
root="$(cd "$(dirname "$0")/.." && pwd)"
"$root/scripts/doctor.sh"
work="${CRABRIX_TOOLCHAIN_WORK:-$root/work}"
[[ -d "$work/rust/.git" ]] || { echo "run fetch-sources.sh --locked first" >&2; exit 1; }
read -r expected_sha sdk_name < <(python3 - "$root/toolchain.lock.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));print(x['rust']['revision'],x['wasiSDK']['url'].rsplit('/',1)[-1])
PY
)
[[ "$(git -C "$work/rust" rev-parse HEAD)" == "$expected_sha" ]] || {
  echo "Rust source checkout differs from toolchain.lock.json" >&2; exit 1;
}
[[ -d "$work/rust/vendor" && -f "$work/rust/.cargo/config.toml" ]] || {
  echo "run vendor-deps.sh --locked before the offline build" >&2; exit 1;
}
sdk_dir="$work/rust/wasi-sdk-32.0-x86_64-linux"
if [[ ! -x "$sdk_dir/bin/clang" ]]; then
  tar -xzf "$work/downloads/$sdk_name" -C "$work/rust"
fi
export WASI_SDK_PATH="$sdk_dir"
export WASI_SYSROOT="$sdk_dir/share/wasi-sysroot"
export CARGO_HOME="$work/cargo-home"
export RUSTUP_DIST_SERVER="file://$work/mirror"
export CARGO_NET_OFFLINE=true
export SOURCE_DATE_EPOCH="$(git -C "$work/rust" show -s --format=%ct HEAD)"
export TZ=UTC
export LC_ALL=C
mkdir -p "$work/logs"
(
  cd "$work/rust"
  env -u GITHUB_ACTIONS -u CI python3 x.py install \
    --set build.vendor=true --set llvm.download-ci-llvm=false \
    2>&1 | tee "$work/logs/rustc-build.log"
  env -u GITHUB_ACTIONS -u CI python3 x.py build library \
    --target wasm32-wasip1 --stage 1 \
    --set build.vendor=true --set llvm.download-ci-llvm=false \
    2>&1 | tee "$work/logs/wasip1-sysroot-build.log"
)
echo "Build finished; package-toolchain.sh validates the produced files before publication."
