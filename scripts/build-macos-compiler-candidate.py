#!/usr/bin/env python3
"""Build a test-only WASI rustc on an ephemeral Xcode Cloud Mac.

This is a compiler-only experiment, not the locked Linux release recipe. The
app's signed compiler, sysroot, inventories and production lock stay untouched.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import time


SDK_DIGESTS = {
    "arm64": "383be7fe00ae04691e1859164fd99970a528c55d624b886ed59f7933898b933d",
    "x86_64": "a36c9ab106a40abe8a051279c233c6bab719a5788ecc0788e8d141796eb55b1b",
}
PERFORMANCE = {
    "rust.optimize": "true",
    "rust.debug-assertions": "false",
    "rust.debug-assertions-std": "false",
    "rust.debug-assertions-tools": "false",
    "rust.debug-logging": "false",
    "rust.incremental": "false",
    "rust.frame-pointers": "false",
    "rust.lto": "thin",
}


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def run(command, *, cwd=None, env=None, timeout=1200):
    subprocess.run(command, cwd=cwd, env=env, check=True, timeout=timeout)


def compile_with_heartbeat(command, source, environment, log):
    started = time.monotonic()
    with log.open("w") as output:
        process = subprocess.Popen(command, cwd=source, env=environment, start_new_session=True,
                                   stdout=output, stderr=subprocess.STDOUT)
        try:
            while True:
                try:
                    status = process.wait(timeout=30)
                    break
                except subprocess.TimeoutExpired:
                    elapsed = int(time.monotonic() - started)
                    print(f"Candidate rustc build: {elapsed}s; log {log.stat().st_size} bytes", flush=True)
                    # Cargo progress and errors must remain visible in Cloud's
                    # downloadable clone log without flooding it with commands.
                    with log.open("rb") as reader:
                        reader.seek(max(0, log.stat().st_size - 1800))
                        print(reader.read().decode(errors="replace"), flush=True)
                    if elapsed > 5400:
                        raise TimeoutError("compiler-only candidate exceeded 90 minutes")
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
    if status:
        with log.open("rb") as reader:
            reader.seek(max(0, log.stat().st_size - 16000))
            print(reader.read().decode(errors="replace"), flush=True)
        raise subprocess.CalledProcessError(status, command)


def command_for(source, sdk, arch, jobs, llvm_config, lto="thin", proc_macro_bridge=False):
    triple = {"arm64": "aarch64-apple-darwin", "x86_64": "x86_64-apple-darwin"}[arch]
    settings = {
        "build.build": json.dumps(triple),
        "build.host": '["wasm32-wasip1"]',
        "build.target": '["wasm32-wasip1"]',
        "build.submodules": "false",
        "build.vendor": "false",
        "build.extended": "false",
        "rust.download-rustc": "false",
        "rust.codegen-backends": '["llvm","cranelift"]',
        f"target.{triple}.codegen-backends": '["llvm"]',
        f"target.{triple}.llvm-config": json.dumps(str(llvm_config)),
        "llvm.link-shared": "true",
        "target.wasm32-wasip1.codegen-backends": '["cranelift"]',
        "target.wasm32-wasip1.wasi-root": json.dumps(str(sdk / "share/wasi-sysroot")),
        "target.wasm32-wasip1.linker": json.dumps(str(sdk / "bin/clang")),
        "llvm.download-ci-llvm": "false",
        **PERFORMANCE,
        "rust.lto": lto,
    }
    if proc_macro_bridge:
        settings["target.wasm32-wasip1.rustflags"] = json.dumps([
            "-Clink-arg=-Wl,--export-if-defined=__crabrix_pm_alloc",
            "-Clink-arg=-Wl,--export-if-defined=__crabrix_pm_free",
            "-Clink-arg=-Wl,--export-if-defined=__crabrix_pm_dispatch",
        ])
    command = [sys.executable, "x.py", "build", "compiler/rustc", "--stage", "2", "--jobs", str(jobs)]
    for key, value in settings.items():
        command.extend(["--set", f"{key}={value}"])
    return command, settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--llvm-config", type=Path, required=True,
                        help="native LLVM 22.1.8, used only by the intermediate Darwin compiler")
    parser.add_argument("--lto", choices=("thin", "fat"), default="thin",
                        help="candidate-only whole-compiler optimization; thin retains the measured baseline")
    parser.add_argument("--proc-macro-bridge", action="store_true",
                        help="apply the experimental WASI RPC macro loader patch; never a release input")
    parser.add_argument("--plan", action="store_true", help="print exact inputs without fetching/building")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    lock = json.loads((root / "toolchain.lock.json").read_text())
    arch = platform.machine()
    if platform.system() != "Darwin" or arch not in SDK_DIGESTS:
        parser.error("this candidate recipe requires an arm64 or x86_64 Mac")
    work, output = args.work.resolve(), args.output.resolve()
    source = work / "rust"
    sdk_name = f"wasi-sdk-32.0-{arch}-macos"
    sdk = work / sdk_name
    command, settings = command_for(source, sdk, arch, lock["bootstrap"]["buildJobs"], args.llvm_config.resolve(), args.lto, args.proc_macro_bridge)
    plan = {
        "candidate": True,
        "productionReplacement": False,
        "rustRevision": lock["rust"]["revision"],
        "configSourceSHA256": lock["bootstrap"]["configSourceSHA256"],
        "patchDigests": lock["patchDigests"],
        "sdk": {"url": f"https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-32/{sdk_name}.tar.gz",
                "sha256": SDK_DIGESTS[arch]},
        "settings": settings,
        "command": command,
    }
    bridge_patch = root / "patches/0005-wasi-proc-macro-bridge.candidate.patch"
    if args.proc_macro_bridge:
        plan["experimentalProcMacroBridge"] = {
            "schemaVersion": 1, "patch": bridge_patch.name, "sha256": digest(bridge_patch),
            "compilerOptInEnvironment": "CRABRIX_WASM_PROC_MACROS=1",
        }
    if args.plan:
        print(json.dumps(plan, indent=2))
        return
    if os.environ.get("CI_XCODE_CLOUD") != "TRUE" \
            or os.environ.get("CI_WORKFLOW") != "Compiler performance candidate (manual)":
        parser.error("build is restricted to the explicitly started compiler-candidate Cloud workflow")
    if work.exists() or output.exists():
        parser.error("work and output must be fresh paths; existing artifacts are never removed")
    work.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(work.parent).free < 30 * 1024**3:
        parser.error("candidate build needs at least 30 GiB free on the ephemeral Mac")
    llvm_version = subprocess.check_output([str(args.llvm_config), "--version"], text=True).strip()
    if llvm_version != "22.1.8":
        parser.error(f"candidate native LLVM must be exactly 22.1.8, received {llvm_version}")
    plan["nativeLLVM"] = {"version": llvm_version, "llvmConfigSHA256": digest(args.llvm_config),
                          "role": "intermediate Darwin compiler only; not bundled into WASI candidate"}
    work.mkdir()
    (work / "CANDIDATE-NOT-FOR-RELEASE.txt").write_text("Compiler-only native macOS experiment. Not a locked release.\n")
    # The regular Linux packager recognizes this marker as well.
    (work / ".candidate-build").write_text("Native macOS compiler-only performance candidate.\n")
    run([sys.executable, str(root / "scripts/validate-lock.py"), "--source-only"])
    run(["git", "init", str(source)])
    run(["git", "remote", "add", "origin", lock["rust"]["url"]], cwd=source)
    run(["git", "fetch", "--depth", "1", "origin", lock["rust"]["revision"]], cwd=source)
    run(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=source)
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if actual != lock["rust"]["revision"] or digest(source / "bootstrap.toml") != plan["configSourceSHA256"]:
        raise ValueError("Rust revision or bootstrap config differs from pinned input")
    run(["git", "submodule", "update", "--init", "--depth", "1", "library/backtrace"], cwd=source)
    actual = subprocess.check_output(["git", "-C", "library/backtrace", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if actual != lock["submodules"]["library/backtrace"]:
        raise ValueError("backtrace submodule differs from pinned input")
    environment = dict(os.environ, CRABRIX_TOOLCHAIN_WORK=str(work),
                       CG_CLIF_FORCE_GNU_AS="1", CARGO_NET_OFFLINE="false", TZ="UTC")
    run([str(root / "scripts/apply-patches.sh"), "--candidate"], env=environment)
    if args.proc_macro_bridge:
        if digest(bridge_patch) != plan["experimentalProcMacroBridge"]["sha256"]:
            raise ValueError("experimental bridge patch changed after input recording")
        run(["git", "apply", "--check", str(bridge_patch)], cwd=source)
        run(["git", "apply", str(bridge_patch)], cwd=source)
    archive = work / f"{sdk_name}.tar.gz"
    run(["/usr/bin/curl", "--fail", "--location", "--retry", "3", "--output", str(archive), plan["sdk"]["url"]])
    if digest(archive) != plan["sdk"]["sha256"]:
        raise ValueError("native WASI SDK SHA-256 differs")
    run(["tar", "-xzf", str(archive), "-C", str(work)])
    if not (sdk / "bin/clang").is_file():
        raise ValueError("verified native WASI SDK has no clang")
    environment.update(WASI_SDK_PATH=str(sdk), WASI_SYSROOT=str(sdk / "share/wasi-sysroot"),
                       CARGO_HOME=str(work / "cargo-home"),
                       SOURCE_DATE_EPOCH=subprocess.check_output(
                           ["git", "show", "-s", "--format=%ct", "HEAD"], cwd=source, text=True).strip())
    # Stage0 Darwin archives are selected and digest-checked by the pinned
    # src/stage0 manifest. Stage1 is built from the exact fork before building
    # target std and stage2 WASI rustc. Stage0 cannot build in-tree cross std.
    for key in ("GITHUB_ACTIONS", "CI"):
        environment.pop(key, None)
    (work / "build-plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    run([sys.executable, str(root / "scripts/audit-build-profile.py"), str(source), "--performance-profile"])
    started = time.monotonic()
    compile_with_heartbeat(command, source, environment, work / "compiler-build.log")
    binary = source / "build/wasm32-wasip1/stage2/bin/rustc.wasm"
    if not binary.is_file():
        binary = binary.with_name("rustc")
    with binary.open("rb") as stream:
        if stream.read(8) != b"\0asm\1\0\0\0":
            raise ValueError("candidate compiler is not a Wasm v1 module")
    output.mkdir(parents=True)
    shutil.copyfile(binary, output / "rustc.wasm")
    provenance = dict(plan, rustVersion=lock["rust"]["actualVersion"],
                      compilerSHA256=digest(binary), compilerBytes=binary.stat().st_size,
                      compilerBuildSeconds=time.monotonic() - started,
                      toolchainRepositoryCommit=subprocess.check_output(
                          ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
                      stage0ManifestSHA256=digest(source / "src/stage0"),
                      cloudBuildID=os.environ.get("CI_BUILD_ID"),
                      host=platform.platform())
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    (output / "CANDIDATE-NOT-FOR-RELEASE.txt").write_text("Compiler-only performance experiment. Not signed production data.\n")
    print("Candidate built:", provenance["compilerSHA256"], provenance["compilerBytes"], flush=True)


if __name__ == "__main__":
    main()
