from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from nanoworker.config import Config, ProviderConfig
from nanoworker.llm import setup_provider_env


class LlmEnvTests(unittest.TestCase):
    def test_openai_compatible_provider_can_read_custom_env_names(self) -> None:
        config = Config(
            providers={
                "openai": ProviderConfig(
                    api_key_env="LLM_API_KEY",
                    api_base_env="LLM_API_BASE",
                )
            }
        )

        with patch.dict(
            os.environ,
            {
                "LLM_API_KEY": "secret",
                "LLM_API_BASE": "https://xianyutoken.com/v1",
            },
            clear=True,
        ):
            setup_provider_env(config, "openai/gpt-5.4")

            self.assertEqual(os.environ["OPENAI_API_KEY"], "secret")
            self.assertEqual(os.environ["OPENAI_API_BASE"], "https://xianyutoken.com/v1")
            self.assertEqual(os.environ["OPENAI_BASE_URL"], "https://xianyutoken.com/v1")

    def test_anthropic_native_provider_uses_anthropic_env_names(self) -> None:
        config = Config(
            providers={
                "anthropic": ProviderConfig(
                    api_key_env="CLAUDE_API_KEY",
                    api_base_env="CLAUDE_API_BASE",
                )
            }
        )

        with patch.dict(
            os.environ,
            {
                "CLAUDE_API_KEY": "secret",
                "CLAUDE_API_BASE": "https://api.anthropic.com",
            },
            clear=True,
        ):
            setup_provider_env(config, "anthropic/claude-sonnet-4-6")

            self.assertEqual(os.environ["ANTHROPIC_API_KEY"], "secret")
            self.assertEqual(os.environ["ANTHROPIC_API_BASE"], "https://api.anthropic.com")
            self.assertEqual(os.environ["ANTHROPIC_BASE_URL"], "https://api.anthropic.com")

    def test_generic_llm_env_works_without_provider_config(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LLM_API_KEY": "secret",
                "LLM_API_BASE": "https://xianyutoken.com/v1",
            },
            clear=True,
        ):
            setup_provider_env(Config(), "openai/gpt-5.4")

            self.assertEqual(os.environ["OPENAI_API_KEY"], "secret")
            self.assertEqual(os.environ["OPENAI_API_BASE"], "https://xianyutoken.com/v1")

    def test_generic_env_takes_precedence_over_literal_config(self) -> None:
        config = Config(providers={"openai": ProviderConfig(api_key="literal", api_base="https://literal")})

        with patch.dict(
            os.environ,
            {
                "LLM_API_KEY": "secret",
                "LLM_API_BASE": "https://xianyutoken.com/v1",
            },
            clear=True,
        ):
            setup_provider_env(config, "openai/gpt-5.4")

            self.assertEqual(os.environ["OPENAI_API_KEY"], "secret")
            self.assertEqual(os.environ["OPENAI_API_BASE"], "https://xianyutoken.com/v1")


if __name__ == "__main__":
    unittest.main()
