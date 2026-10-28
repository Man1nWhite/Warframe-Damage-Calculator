"""Ensure CI diagnostics report failures without turning them into passes."""
from __future__ import annotations

import contextlib
import io
import unittest
from unittest.mock import patch

from tools.run_tests_ci import _escape_command_text, run_suite


class CiRunnerTests(unittest.TestCase):
    def test_workflow_command_data_is_escaped(self):
        self.assertEqual(_escape_command_text("50%\r\nnext"), "50%25%0D%0Anext")

    def test_failures_and_errors_generate_annotations_and_stay_failed(self):
        class FailingCase(unittest.TestCase):
            def test_failure(self):
                self.fail("bad 50% result")

            def test_error(self):
                raise ValueError("bad input")

        suite = unittest.defaultTestLoader.loadTestsFromTestCase(FailingCase)
        output = io.StringIO()
        log = io.StringIO()
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}), contextlib.redirect_stdout(output):
            result = run_suite(suite, stream=log)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual((len(result.failures), len(result.errors)), (1, 1))
        self.assertEqual(output.getvalue().count("::error title=Unittest failure::"), 2)
        self.assertIn("bad 50%25 result", output.getvalue())
        self.assertIn("ValueError: bad input", output.getvalue())
        self.assertIn("FAILED (failures=1, errors=1)", log.getvalue())


if __name__ == "__main__":
    unittest.main()
