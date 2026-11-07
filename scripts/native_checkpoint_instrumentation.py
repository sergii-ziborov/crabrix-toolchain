"""Instrument pinned wasm2c control flow without polling on forward branches.

Every cycle in a finite function contains a backward edge; recursive cycles
enter a function. Keep a checkpoint on both, and reject unfamiliar source
shapes instead of silently emitting an uninterruptible kernel.
"""
import re


FUNCTION = re.compile(r"(?ms)^(?:static )?[\w* ]+ w2c_\w+\([^;{}]*\) \{\n.*?^\}")
JUMP = re.compile(r"\bgoto (\w+);")
LABEL = re.compile(r"(?m)^\s*(\w+):")


def instrument(source, policy="all-branches"):
    if policy not in ("all-branches", "function-and-backedge", "function-and-backedge-entry-stack"):
        raise ValueError("unknown native checkpoint policy")
    counts = {"functionEntries": 0, "backedges": 0, "forwardEdges": 0}
    total_jumps = len(JUMP.findall(source))
    total_entries = source.count("FUNC_PROLOGUE;")
    if len(re.findall(r"\bgoto\b", source)) != total_jumps:
        raise ValueError("unrecognized native goto syntax")

    def function(match):
        body = match.group()
        entries = body.count("FUNC_PROLOGUE;")
        jumps = list(JUMP.finditer(body))
        if not entries and not jumps:
            return body  # wasm2c's small typed call wrappers.
        if entries != 1:
            raise ValueError("generated function lacks exactly one entry checkpoint")
        if re.search(r"\b(?:while|for|do)\s*[({]", body):
            raise ValueError("native loop syntax changed; expected wasm2c goto loops")
        if policy == "function-and-backedge-entry-stack":
            # wasm2c guest frames have fixed-size locals. A backward jump
            # cannot grow that frame; each called guest function checks its
            # own entry. Reject dynamic native stack allocation rather than
            # applying that reasoning to a changed generator shape.
            if re.search(r"\b(?:__builtin_)?alloca\w*\s*\(", body):
                raise ValueError("dynamic native stack allocation is incompatible with entry stack checks")
            arrays = re.findall(r"(?m)^\s*(?!(?:return|goto)\b)(?:[\w*]+\s+)+\w+\s*((?:\[[^]]*\]\s*)+)", body)
            bounds = [bound for dimensions in arrays for bound in re.findall(r"\[([^]]*)\]", dimensions)]
            if any(not re.fullmatch(r"\s*[1-9][0-9]*\s*", bound) for bound in bounds):
                raise ValueError("unrecognized native array bound is incompatible with entry stack checks")
        counts["functionEntries"] += 1
        labels = {}
        for label in LABEL.finditer(body):
            name = label.group(1)
            if name == "default":
                continue  # switch default is not a goto target.
            if name in labels:
                raise ValueError("duplicate generated function label: " + name)
            labels[name] = label.start()

        def jump(item):
            name = item.group(1)
            if name not in labels:
                raise ValueError("unresolved generated function label: " + name)
            backward = labels[name] <= item.start()
            counts["backedges" if backward else "forwardEdges"] += 1
            if backward or policy == "all-branches":
                checkpoint = "crabrix_native_loop_checkpoint" if policy == "function-and-backedge-entry-stack" else "crabrix_native_checkpoint"
                return "do { " + checkpoint + "(); goto " + name + "; } while (0);"
            return item.group()

        body = JUMP.sub(jump, body)
        return body.replace("FUNC_PROLOGUE;", "FUNC_PROLOGUE; crabrix_native_checkpoint();")

    result = FUNCTION.sub(function, source)
    if counts["functionEntries"] != total_entries or counts["backedges"] + counts["forwardEdges"] != total_jumps:
        raise ValueError("unrecognized generated function boundary")
    counts["checkpoints"] = counts["functionEntries"] + counts["backedges"]
    if policy == "all-branches":
        counts["checkpoints"] += counts["forwardEdges"]
    return result, counts
