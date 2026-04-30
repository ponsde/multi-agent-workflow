from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nanoworker.prompt import load_skill, skill_exists
from nanoworker.roles import upsert_role_path


class PromptTests(unittest.TestCase):
    def test_runtime_skill_resolution_uses_registry_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "roles"
            index = store / "index.json"
            skill = store / "reviewer" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("---\nname: reviewer\n---\n\n# Reviewer\n", encoding="utf-8")

            self.assertFalse(skill_exists(store, "reviewer"))
            self.assertIsNone(load_skill(store, "reviewer"))

            upsert_role_path(store, index, skill, role_id="reviewer")

            self.assertTrue(skill_exists(store, "reviewer"))
            self.assertEqual(load_skill(store, "reviewer"), "# Reviewer\n")


if __name__ == "__main__":
    unittest.main()
