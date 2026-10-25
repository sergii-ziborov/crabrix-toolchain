import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location(
    'compile_native_compiler', Path(__file__).resolve().parents[1] / 'scripts/compile-native-compiler.py')
compiler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compiler)


class NativeCompileFlagsTests(unittest.TestCase):
    def test_default_recipe_and_safety_flags_survive_explicit_experiment(self):
        source = ['-O1', '-DWASM_RT_MEMCHECK_BOUNDS_CHECK=1', '-fno-optimize-sibling-calls',
                  '-DWASM_RT_STACK_DEPTH_COUNT=1', '-Werror=frame-larger-than']
        baseline = compiler.compilation_flags(source)
        candidate = compiler.compilation_flags(source, '2')
        self.assertEqual(baseline, source)
        self.assertIsNot(baseline, source)
        self.assertEqual(candidate[0], '-O2')
        self.assertEqual(candidate[1:], baseline[1:])
        self.assertEqual(source[0], '-O1')

    def test_ambiguous_or_unexpected_recipe_is_rejected(self):
        for flags in ([], ['-O2'], ['-O1', '-O0'], ['-Ofast']):
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                compiler.compilation_flags(flags, '2')

    def test_other_overrides_are_rejected(self):
        for level in ('0', '3', 'fast', ''):
            with self.subTest(level=level), self.assertRaises(ValueError):
                compiler.compilation_flags(['-O1'], level)


if __name__ == '__main__':
    unittest.main()
