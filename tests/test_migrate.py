from __future__ import annotations

import unittest

from nanoworker.migrate import migrate_config


class MigrateTests(unittest.TestCase):
    def test_migrates_numbered_workers_and_generic_env_names(self) -> None:
        result = migrate_config(
            {
                "providers": {
                    "openai": {
                        "api_key": "secret",
                        "api_base": "https://xianyutoken.com/v1",
                        "api_key_env": "XIANYU_API_KEY",
                        "api_base_env": "XIANYU_API_BASE",
                    }
                },
                "workers": {
                    "coder-1": {"role": "coder", "model": "fast", "skills": ["coder"]},
                    "coder-2": {"role": "coder", "model": "fast", "skills": ["coder"]},
                    "debug-1": {"role": "debug", "model": "fast", "skills": ["debug-engineer"]},
                    "tester": {"role": "tester", "model": "fast", "skills": ["testing-engineer"]},
                },
            }
        )

        provider = result.config["providers"]["openai"]
        self.assertNotIn("api_key", provider)
        self.assertNotIn("api_base", provider)
        self.assertEqual(provider["api_key_env"], "LLM_API_KEY")
        self.assertEqual(provider["api_base_env"], "LLM_API_BASE")

        self.assertEqual(set(result.config["workers"]), {"write", "debug", "verify"})
        self.assertEqual(result.config["workers"]["write"]["tool_policy"], "product-write")
        self.assertEqual(result.config["workers"]["verify"]["tool_policy"], "test-write-only")
        self.assertEqual(result.config["workers"]["debug"]["skills"], ["debug"])
        self.assertEqual(result.config["workers"]["verify"]["skills"], ["tester"])
        self.assertTrue(any("coder-2" in warning for warning in result.warnings))

    def test_migrates_legacy_duel_worker_to_reviewer(self) -> None:
        result = migrate_config(
            {
                "workers": {
                    "debug-duel-1": {"role": "debug-duel", "model": "fast", "skills": ["debug-duel"]},
                }
            }
        )

        self.assertEqual(result.config["workers"]["review"]["role"], "reviewer")
        self.assertEqual(result.config["workers"]["review"]["skills"], ["reviewer"])

    def test_explicit_template_wins_over_legacy_numbered_worker(self) -> None:
        result = migrate_config(
            {
                "workers": {
                    "coder-1": {"role": "coder", "model": "old"},
                    "write": {"role": "coder", "model": "new"},
                }
            }
        )

        self.assertEqual(result.config["workers"]["write"]["model"], "new")
        self.assertTrue(any("explicit template write" in warning for warning in result.warnings))


if __name__ == "__main__":
    unittest.main()
