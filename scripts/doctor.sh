#!/usr/bin/env bash
set -euo pipefail
mode="${1:---locked}"
if (( $# > 1 )) || [[ "$mode" != --locked && "$mode" != --candidate ]]; then
  echo "usage: $0 [--locked|--candidate]" >&2
  exit 2
fi
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$root/scripts/validate-lock.py" --source-only
for command in git python3 curl tar sha256sum cmake ninja gcc; do
  command -v "$command" >/dev/null || { echo "missing build tool: $command" >&2; exit 1; }
done
if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
  echo "Production build requires controlled Linux x86_64; this host can inspect the source lock only." >&2
  exit 1
fi
memory_kib="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
if [[ -r /sys/fs/cgroup/memory.max ]]; then
  cgroup_bytes="$(cat /sys/fs/cgroup/memory.max)"
  if [[ "$cgroup_bytes" =~ ^[0-9]+$ ]]; then
    cgroup_kib="$((cgroup_bytes / 1024))"
    if (( cgroup_kib < memory_kib )); then memory_kib="$cgroup_kib"; fi
  fi
fi
resource_error=0
if (( memory_kib < 8 * 1024 * 1024 )); then
  echo "Production Rust compiler build requires at least 8 GiB available to this Linux environment; detected $((memory_kib / 1024)) MiB." >&2
  resource_error=1
fi
work="${CRABRIX_TOOLCHAIN_WORK:-$root/work}"
disk_path="$work"
[[ -e "$disk_path" ]] || disk_path="$root"
free_disk_kib="$(df -Pk "$disk_path" | awk 'NR == 2 { print $4 }')"
if [[ ! "$free_disk_kib" =~ ^[0-9]+$ ]]; then
  echo "Could not determine free build disk space at $disk_path." >&2
  resource_error=1
elif (( free_disk_kib < 30 * 1024 * 1024 )); then
  echo "Production Rust compiler build requires at least 30 GiB free at $disk_path; detected $((free_disk_kib / 1024)) MiB." >&2
  resource_error=1
fi
(( resource_error == 0 )) || exit 1
if [[ "$mode" == --locked ]]; then
  [[ -z "$(git -C "$root" status --porcelain --untracked-files=normal)" ]] || {
    echo "Release builder checkout must be clean and committed" >&2
    exit 1
  }
  python3 "$root/scripts/validate-lock.py"
else
  echo "Candidate mode marks output as test-only; use --locked for a release build." >&2
fi
