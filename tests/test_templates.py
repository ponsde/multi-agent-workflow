from __future__ import annotations

import unittest

from nanoworker.templates import build_init_config


class TemplateTests(unittest.TestCase):
    def test_both_provider_defaults_to_gpt_and_claude_sonnet(self) -> None:
        config = build_init_config("both")

        self.assertEqual(config["models"]["gpt-5.4"]["model"], "openai/gpt-5.4")
        self.assertEqual(config["models"]["claude-sonnet"]["model"], "anthropic/claude-sonnet-4-6")
        self.assertEqual(config["workers"]["write"]["model"], "gpt-5.4")
        self.assertEqual(config["workers"]["fix"]["role"], "fixer")
        self.assertEqual(config["workers"]["fix"]["skills"], ["fixer"])
        self.assertEqual(config["workers"]["review"]["model"], "claude-sonnet")
        self.assertEqual(config["workers"]["review"]["role"], "reviewer")
        self.assertEqual(config["workers"]["review"]["skills"], ["reviewer"])


if __name__ == "__main__":
    unittest.main()
