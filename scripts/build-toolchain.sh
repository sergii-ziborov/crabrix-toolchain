#!/usr/bin/env bash
set -euo pipefail
mode="${1:-}"
if (( $# != 1 )) || [[ "$mode" != --locked && "$mode" != --candidate ]]; then
  echo "usage: $0 --locked|--candidate" >&2
  exit 2
fi
root="$(cd "$(dirname "$0")/.." && pwd)"
"$root/scripts/doctor.sh" "$mode"
work="${CRABRIX_TOOLCHAIN_WORK:-$root/work}"
[[ -d "$work/rust/.git" ]] || { echo "run fetch-sources.sh --locked first" >&2; exit 1; }
read -r expected_sha sdk_name build_jobs < <(python3 - "$root/toolchain.lock.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));print(x['rust']['revision'],x['wasiSDK']['url'].rsplit('/',1)[-1],x['bootstrap']['buildJobs'])
PY
)
[[ "$(git -C "$work/rust" rev-parse HEAD)" == "$expected_sha" ]] || {
  echo "Rust source checkout differs from toolchain.lock.json" >&2; exit 1;
}
[[ -d "$work/rust/vendor" && -f "$work/rust/.cargo/config.toml" ]] || {
  echo "run vendor-deps.sh --locked before the offline build" >&2; exit 1;
}
"$root/scripts/apply-patches.sh" "$mode"
candidate_marker="$work/.candidate-build"
if [[ "$mode" == --candidate ]]; then
  # Mark the work tree before x.py writes any output. A failed trial must not
  # later be packaged merely because its release environment lock was filled.
  printf 'Candidate build outputs; use a fresh work directory for --locked.\n' > "$candidate_marker"
elif [[ -e "$candidate_marker" ]]; then
  echo "This work directory contains candidate build outputs; use a fresh work directory for --locked." >&2
  exit 1
fi
sdk_dir="$work/rust/wasi-sdk-32.0-x86_64-linux"
if [[ ! -x "$sdk_dir/bin/clang" ]]; then
  tar -xzf "$work/downloads/$sdk_name" -C "$work/rust"
fi
export WASI_SDK_PATH="$sdk_dir"
export WASI_SYSROOT="$sdk_dir/share/wasi-sysroot"
export CARGO_HOME="$work/cargo-home"
export RUSTUP_DIST_SERVER="file://$work/mirror"
export CARGO_NET_OFFLINE=true
export CG_CLIF_FORCE_GNU_AS=1
export SOURCE_DATE_EPOCH="$(git -C "$work/rust" show -s --format=%ct HEAD)"
export TZ=UTC
export LC_ALL=C
codegen_backends="$(python3 - "$root/toolchain.lock.json" <<'PY'
import json,sys
print(json.dumps(json.load(open(sys.argv[1]))['bootstrap']['codegenBackends'],separators=(',',':')))
PY
)"
codegen_args=(--set "rust.codegen-backends=$codegen_backends")
llvm_targets="$(python3 - "$root/toolchain.lock.json" <<'PY'
import json,sys
print(';'.join(json.load(open(sys.argv[1]))['bootstrap']['llvm']['targets']))
PY
)"
llvm_args=(--set "llvm.targets=$llvm_targets" --set "llvm.experimental-targets=")
mkdir -p "$work/logs"
(
  cd "$work/rust"
  env -u GITHUB_ACTIONS -u CI python3 x.py install \
    --jobs "$build_jobs" \
    --set build.vendor=true --set llvm.download-ci-llvm=false \
    "${llvm_args[@]}" "${codegen_args[@]}" \
    2>&1 | tee "$work/logs/rustc-build.log"
  env -u GITHUB_ACTIONS -u CI python3 x.py build library \
    --target wasm32-wasip1 --stage 1 --jobs "$build_jobs" \
    --set build.vendor=true --set llvm.download-ci-llvm=false \
    "${llvm_args[@]}" "${codegen_args[@]}" \
    2>&1 | tee "$work/logs/wasip1-sysroot-build.log"
)
if [[ "$mode" == --candidate ]]; then
  echo "Candidate build finished. Packaging and publication still require the complete release environment lock."
else
  echo "Build finished; package-toolchain.sh validates the produced files before publication."
fi
