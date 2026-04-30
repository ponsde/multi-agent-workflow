from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nanoworker.config import load_config_file, load_local_env_file, resolve_model


class ConfigTests(unittest.TestCase):
    def test_loads_model_profiles_and_resolves_profile_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "models": {
                            "gpt-backend": {
                                "model": "openai/gpt-5.3-codex",
                                "strengths": ["backend", "tests"],
                                "preferred_roles": ["coder", "debug"],
                                "cost_tier": "medium",
                                "latency_tier": "medium",
                                "fallbacks": ["openai/gpt-5.4"],
                            }
                        },
                        "workers": {
                            "write": {
                                "role": "coder",
                                "tool_policy": "product-write",
                                "model": "gpt-backend",
                                "skills": ["coder"],
                            }
                        },
                        "journal": {"enabled": True, "path": "~/nw.jsonl"},
                    }
                ),
                encoding="utf-8",
            )

            config = load_config_file(path)
            worker = config.workers["write"]
            resolved = resolve_model(config, worker.model)

        self.assertEqual(resolved.model, "openai/gpt-5.3-codex")
        self.assertEqual(resolved.profile, "gpt-backend")
        self.assertEqual(resolved.strengths, ("backend", "tests"))
        self.assertEqual(resolved.preferred_roles, ("coder", "debug"))
        self.assertEqual(resolved.fallbacks, ("openai/gpt-5.4",))
        self.assertEqual(worker.tool_policy, "product-write")
        self.assertTrue(config.journal.enabled)
        self.assertEqual(config.journal.path, "~/nw.jsonl")

    def test_resolve_model_accepts_raw_model_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{}", encoding="utf-8")
            config = load_config_file(path)

        resolved = resolve_model(config, "openai/gpt-5.4")

        self.assertEqual(resolved.model, "openai/gpt-5.4")
        self.assertIsNone(resolved.profile)

    def test_load_local_env_file_does_not_override_process_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "env"
            path.write_text(
                "export LLM_API_KEY='from-file'\n"
                "export LLM_API_BASE='https://example.test/v1'\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"LLM_API_KEY": "from-process"}, clear=True):
                load_local_env_file(path)

                self.assertEqual(os.environ["LLM_API_KEY"], "from-process")
                self.assertEqual(os.environ["LLM_API_BASE"], "https://example.test/v1")


if __name__ == "__main__":
    unittest.main()
