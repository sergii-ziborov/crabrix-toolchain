import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from native_checkpoint_instrumentation import instrument


class NativeCheckpointTests(unittest.TestCase):
    def test_forward_and_backward_edges_keep_function_local_labels(self):
        source = """void w2c_first(int n) {
  FUNC_PROLOGUE;
  goto exit;
  loop:;
  if (--n) goto loop;
  exit:;
  FUNC_EPILOGUE;
}
void w2c_second(
    int n) {
  FUNC_PROLOGUE;
  exit:;
  goto exit;
  FUNC_EPILOGUE;
}
"""
        result, counts = instrument(source, "function-and-backedge")
        self.assertEqual(counts, {"functionEntries": 2, "backedges": 2, "forwardEdges": 1, "checkpoints": 4})
        self.assertIn("\n  goto exit;", result)
        self.assertEqual(result.count("crabrix_native_checkpoint();"), 4)
        legacy, counts = instrument(source)
        self.assertEqual(counts["checkpoints"], 5)
        self.assertEqual(legacy.count("crabrix_native_checkpoint();"), 5)

    def test_rejects_unfamiliar_or_unresolved_control_flow(self):
        bodies = ["goto missing;", "goto *target;", "for (;;) {}", "while (1) {}", "do {} while (1);",
                  "again:;\n  again:; goto again;"]
        for body in bodies:
            with self.subTest(body=body), self.assertRaises(ValueError):
                instrument("void w2c_test(void) {\n  FUNC_PROLOGUE;\n  " + body + "\n}", "function-and-backedge")
        for source in ["void unfamiliar(void) {\n FUNC_PROLOGUE;\n}",
                       "void w2c_test(void) {\n again:; goto again;\n}"]:
            with self.assertRaises(ValueError): instrument(source, "function-and-backedge")

    def test_real_c_loops_recursion_and_forward_branches(self):
        clang = shutil.which("clang")
        self.assertIsNotNone(clang)
        prefix = """#include <stdlib.h>
#define FUNC_PROLOGUE
#define FUNC_EPILOGUE
static int budget = 4, checks;
static void crabrix_native_checkpoint(void) { if (!budget--) exit(23); ++checks; }
"""
        functions = [
            ("void w2c_loop(void) {\n FUNC_PROLOGUE;\n loop:; goto loop;\n}\n", "w2c_loop();", 23),
            ("void w2c_recurse(void) {\n FUNC_PROLOGUE;\n w2c_recurse();\n}\n", "w2c_recurse();", 23),
            ("void w2c_forward(void) {\n FUNC_PROLOGUE;\n goto exit;\n abort();\n exit:;\n}\n", "w2c_forward(); if (checks != 1) return 1;", 0),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            for n, (source, call, status) in enumerate(functions):
                code, _ = instrument(source, "function-and-backedge")
                path = root / f"case{n}.c"
                path.write_text(prefix + code + "int main(void) { " + call + " return 0; }\n")
                subprocess.run([clang, "-O1", "-fno-optimize-sibling-calls", str(path), "-o", str(root / f"case{n}")], check=True)
                run = subprocess.run([str(root / f"case{n}")], timeout=3)
                self.assertEqual(run.returncode, status)


if __name__ == "__main__": unittest.main()
