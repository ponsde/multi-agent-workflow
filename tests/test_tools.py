from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from nanoworker.tools import get_tools_for_policy


class ToolPolicyTests(unittest.TestCase):
    def test_test_write_only_allows_test_paths_and_blocks_product_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tools = get_tools_for_policy("test-write-only", tmp)

            allowed = asyncio.run(
                tools.execute("write", {"path": "tests/test_app.py", "content": "def test_ok():\n    pass\n"})
            )
            blocked = asyncio.run(tools.execute("write", {"path": "src/app.py", "content": "print('x')\n"}))

            self.assertIn("Successfully wrote", allowed)
            self.assertTrue((Path(tmp) / "tests/test_app.py").exists())
            self.assertIn("test-write-only policy", blocked)
            self.assertFalse((Path(tmp) / "src/app.py").exists())


if __name__ == "__main__":
    unittest.main()
