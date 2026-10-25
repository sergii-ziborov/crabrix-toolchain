#!/usr/bin/env python3
"""Generate checked, interruptible C for the bundled compiler only.

User programs and procedural-macro crates remain WasmKit guests. This command
does not execute, sign or qualify a candidate, and never rewrites its origin.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

import qualified_macos
from native_checkpoint_instrumentation import instrument

WABT_SHA = "3f654779b436c628db3ca4323c51538815f5fbc887a6d5f3bb1c18d36281e240"
FLAGS = ["-O1", "-g0", "-DNDEBUG=1", "-fno-optimize-sibling-calls", "-fno-omit-frame-pointer", "-frounding-math",
         "-DWASM_RT_USE_MMAP=1", "-DWASM_RT_MEMCHECK_GUARD_PAGES=0", "-DWASM_RT_MEMCHECK_BOUNDS_CHECK=1",
         "-DWASM_RT_INSTALL_SIGNAL_HANDLER=0", "-DWASM_RT_STACK_DEPTH_COUNT=1", "-DWASM_RT_MAX_CALL_STACK_DEPTH=4096",
         "-DWASM_RT_TRAP_HANDLER=crabrix_native_trap", "-DWASM_RT_USE_LOCAL_MEMORY_BASE_SIZE=0",
         "-Wframe-larger-than=131072", "-Werror=frame-larger-than"]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(artifact, archive, work, output, checkpoint_policy="all-branches"):
    root = Path(__file__).resolve().parents[1]
    provenance = json.loads((artifact / "provenance.json").read_text())
    qualified_macos.validate_source(provenance, qualified_macos.profile())
    compiler = artifact / "rustc.wasm"
    if sha(compiler) != provenance["compilerSHA256"] or sha(archive) != WABT_SHA:
        raise ValueError("compiler or official WABT archive differs from pinned input")
    if work.exists() or output.exists(): raise ValueError("native generation paths must be fresh")
    work.mkdir(parents=True); output.mkdir(parents=True)
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
                raise ValueError("unsafe WABT archive entry")
        bundle.extractall(work, filter="data")
    wabt = work / "wabt-1.0.42"
    subprocess.run([str(wabt / "bin/wasm2c"), str(compiler), "-o", str(output / "rustc.c"),
                    "--module-name=crabrix_rustc", "--num-outputs=64", "--no-debug-names", "--disable-tail-call"], check=True)
    header = (output / "rustc.h").read_text()
    declarations = re.findall(r"(?:void|u32|u64)\s+(w2c_\w+)\((struct w2c_\w+\*)[^;]*\);", header)
    imports = []
    for function, context_type in declarations:
        declaration = re.search(r"(?:void|u32|u64)\s+" + re.escape(function) + r"\([^;]+;", header).group(0)
        prefix = context_type.removeprefix("struct ").removesuffix("*") + "_"
        if not function.startswith(prefix): continue
        module = {"w2c_wasi__snapshot__preview1": "wasi_snapshot_preview1",
                  "w2c_crabrix__proc__macro__v1": "crabrix_proc_macro_v1"}.get(prefix[:-1])
        if module is None: raise ValueError("unexpected compiler import namespace")
        field = function[len(prefix):].replace("__", "_")
        result, tail = declaration.split(" ", 1)
        args = declaration[declaration.index("(")+1:declaration.rindex(")")].split(",")
        scalar_types = [arg.strip() for arg in args[1:]]
        if any(arg not in ("u32", "u64") for arg in scalar_types): raise ValueError("unsupported native import ABI")
        imports.append((module, field, result, function, context_type, scalar_types))
    if {item[0] for item in imports} != {"wasi_snapshot_preview1", "crabrix_proc_macro_v1"}:
        raise ValueError("macro-enabled compiler import ABI is missing")
    instantiate = re.search(r"void wasm2c_crabrix__rustc_instantiate\(([^;]+)\);", header).group(1)
    contexts = [value.strip().removesuffix("*").removeprefix("struct ") for value in instantiate.split(",")[1:]]
    def exported(name):
        match = re.search(r"/\* export: '" + re.escape(name) + r"' \*/\s*(?:void|u32|u64) (\w+)\(", header)
        if not match: raise ValueError("required native compiler export missing: " + name)
        return match.group(1)
    replacements = {
        "SOURCE_SHA256": provenance["compilerSHA256"],
        "IMPORT_CONTEXTS": "\n".join("struct " + item + " { CrabrixNativeCompiler* owner; };" for item in contexts),
        "IMPORT_MEMBERS": " ".join("struct " + item + " import_" + str(index) + ";" for index, item in enumerate(contexts)),
        "INITIALIZE_IMPORTS": " ".join("compiler->import_" + str(index) + ".owner = compiler;" for index in range(len(contexts))),
        "INSTANTIATE_IMPORTS": ", ".join("&compiler->import_" + str(index) for index in range(len(contexts))),
        "START_EXPORT": exported("_start"), "ALLOC_EXPORT": exported("__crabrix_pm_alloc"),
        "FREE_EXPORT": exported("__crabrix_pm_free"), "DISPATCH_EXPORT": exported("__crabrix_pm_dispatch"),
    }
    functions = []
    for module, field, result, function, context_type, types in imports:
        arguments = ["p" + str(index) for index in range(len(types))]
        signature = context_type + " context" + "".join(", " + kind + " " + arg for kind, arg in zip(types, arguments))
        functions.append(result + " " + function + "(" + signature + ") {\n"
            "  uint64_t args[] = {" + ", ".join(arguments or ["0"]) + "}; uint64_t result = 0;\n"
            "  CrabrixNativeCompiler* compiler = context->owner;\n"
            "  if (compiler->host(compiler->context, \"" + module + "\", \"" + field + "\", args, " + str(len(types))
            + ", &result)) wasm_rt_trap(WASM_RT_TRAP_UNREACHABLE);\n"
            + ("  return (" + result + ")result;\n" if result != "void" else "") + "}\n")
    replacements["IMPORT_FUNCTIONS"] = "\n".join(functions)
    template = (root / "native-compiler/NativeCompiler.c.in").read_text()
    for key, value in replacements.items(): template = template.replace("@" + key + "@", value)
    if re.search(r"@[A-Z_0-9]+@", template): raise ValueError("unresolved native compiler template marker")
    (output / "NativeCompiler.c").write_text(template)
    for name in ("NativeCompilerAPI.h", "native-checkpoint.h"):
        shutil.copyfile(root / "native-compiler" / name, output / name)
    for path in (wabt / "include").glob("wasm-rt*.h"): shutil.copyfile(path, output / path.name)
    for path in (wabt / "share/wabt/wasm2c").glob("wasm-rt*"):
        if path.is_file(): shutil.copyfile(path, output / path.name)
    checkpoint_counts = {"functionEntries": 0, "backedges": 0, "forwardEdges": 0, "checkpoints": 0}
    for path in output.glob("rustc*.c"):
        source, counts = instrument(path.read_text(), checkpoint_policy)
        for key, value in counts.items(): checkpoint_counts[key] += value
        path.write_text('#include "native-checkpoint.h"\n' + source)
    # Ordinary simulator builds keep their VM backend. A separate, explicit
    # simulator candidate may compile this same source for its actual SDK.
    for path in output.glob("*.c"):
        path.write_text('#include <TargetConditionals.h>\n#if !TARGET_OS_SIMULATOR || defined(CRABRIX_NATIVE_COMPILER_SIMULATOR)\n' + path.read_text() + '\n#endif\n')
    files = [{"path": path.name, "bytes": path.stat().st_size, "sha256": sha(path)} for path in sorted(output.iterdir()) if path.is_file()]
    report = {"schemaVersion": 1, "candidate": True, "productionReplacement": False,
        "compilerWASMSHA256": provenance["compilerSHA256"], "wabtArchiveSHA256": WABT_SHA,
        "generatorSHA256": sha(Path(__file__)), "checkpointInstrumenterSHA256": sha(root / "scripts/native_checkpoint_instrumentation.py"),
        "flags": FLAGS, "checkpointCount": checkpoint_counts["checkpoints"],
        "checkpointPolicy": checkpoint_policy, "checkpointCounts": checkpoint_counts,
        "limits": {"linearMemoryBytes": 2 * 1024**3, "nativeFrameMaximumBytes": 131072,
                   "stackGuardMarginBytes": 512 * 1024, "pollIntervalCheckpoints": 128,
                   "stackCheckPlacement": "function-entry" if checkpoint_policy == "function-and-backedge-entry-stack" else "every-checkpoint"},
        "files": files, "sourceBuildProvenance": provenance}
    (output / "native-source-provenance.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("artifact", "wabt-archive", "work", "output"): parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--checkpoint-policy", choices=("all-branches", "function-and-backedge", "function-and-backedge-entry-stack"), default="all-branches",
                        help="backedge-only polling is an opt-in performance experiment until benchmarked")
    args = parser.parse_args()
    result = generate(args.artifact.resolve(), args.wabt_archive.resolve(), args.work.resolve(), args.output.resolve(), args.checkpoint_policy)
    print(json.dumps({key: result[key] for key in ("compilerWASMSHA256", "checkpointCount", "flags")}, indent=2))


if __name__ == "__main__": main()
