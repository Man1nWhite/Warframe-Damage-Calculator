"""Saved-build JSON nesting checks must not depend on the Python version."""
from __future__ import annotations

import json
import unittest

from modules.json_safety import require_json_depth


class JsonDepthTests(unittest.TestCase):
    def test_exact_depth_limit_and_next_level(self) -> None:
        for depth in (0, 1, 64):
            text = "[" * depth + "0" + "]" * depth
            require_json_depth(text, 64, "Build JSON")
            self.assertIsNotNone(json.loads(text))
        with self.assertRaisesRegex(ValueError, "nesting depth"):
            require_json_depth("[" * 65 + "0" + "]" * 65, 64, "Build JSON")

    def test_brackets_quotes_and_backslashes_inside_strings_are_not_nesting(self) -> None:
        value = {"text": '[[{]}}] "escaped" \\\\ \\" [still text]',
                 "nested": [{"name": "fixture"}]}
        text = json.dumps(value)
        require_json_depth(text, 3, "Build JSON")
        self.assertEqual(json.loads(text), value)
        with self.assertRaisesRegex(ValueError, "nesting depth"):
            require_json_depth(text, 2, "Build JSON")


if __name__ == "__main__":
    unittest.main()
