"""
Tests for cli/__main__.py — entry point coverage.
"""

import unittest


class TestCLIMain(unittest.TestCase):
    def test_module_has_main_guard(self):
        import tokenade.cli.__main__ as mod

        self.assertTrue(hasattr(mod, "main"))

    def test_main_function_is_callable(self):
        from tokenade.cli import main

        self.assertTrue(callable(main))


if __name__ == "__main__":
    unittest.main()
