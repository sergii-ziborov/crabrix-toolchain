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
memory_kib="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
if [[ -r /sys/fs/cgroup/memory.max ]]; then
  cgroup_bytes="$(cat /sys/fs/cgroup/memory.max)"
  if [[ "$cgroup_bytes" =~ ^[0-9]+$ ]]; then
    cgroup_kib="$((cgroup_bytes / 1024))"
    if (( cgroup_kib < memory_kib )); then memory_kib="$cgroup_kib"; fi
  fi
fi
if (( memory_kib < 8 * 1024 * 1024 )); then
  echo "Production Rust/LLVM build requires at least 8 GiB available to this Linux environment; detected $((memory_kib / 1024)) MiB." >&2
  exit 1
fi
python3 "$root/scripts/validate-lock.py"
