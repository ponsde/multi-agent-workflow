"""Config templates used by the CLI."""

from __future__ import annotations

from typing import Any

DEFAULT_OPENAI_MODEL = "gpt-5.4"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"


def build_init_config(provider: str, model_id: str | None = None) -> dict[str, Any]:
    """Build an env-first sample config for nanoworker init."""
    if provider == "openai-compatible":
        model_id = model_id or DEFAULT_OPENAI_MODEL
        providers = {
            "openai": {
                "api_key_env": "LLM_API_KEY",
                "api_base_env": "LLM_API_BASE",
            }
        }
        models = {
            "gpt-5.4": {
                "model": f"openai/{model_id}",
                "strengths": ["backend", "reasoning", "refactor", "tests"],
                "preferred_roles": ["coder", "debug", "fixer", "tester"],
                "fallbacks": [],
            }
        }
        default_model = "gpt-5.4"
    elif provider == "anthropic-native":
        model_id = model_id or DEFAULT_ANTHROPIC_MODEL
        providers = {
            "anthropic": {
                "api_key_env": "LLM_API_KEY",
                "api_base_env": "LLM_API_BASE",
            }
        }
        models = {
            "claude-sonnet": {
                "model": f"anthropic/{model_id}",
                "strengths": ["frontend", "ui", "review", "code"],
                "preferred_roles": ["coder", "debug", "fixer", "reviewer"],
                "fallbacks": [],
            }
        }
        default_model = "claude-sonnet"
    elif provider == "both":
        openai_model_id = model_id or DEFAULT_OPENAI_MODEL
        anthropic_model_id = DEFAULT_ANTHROPIC_MODEL if model_id is None else model_id
        providers = {
            "openai": {
                "api_key_env": "LLM_API_KEY",
                "api_base_env": "LLM_OPENAI_API_BASE",
            },
            "anthropic": {
                "api_key_env": "LLM_API_KEY",
                "api_base_env": "LLM_ANTHROPIC_API_BASE",
            },
        }
        models = {
            "gpt-5.4": {
                "model": f"openai/{openai_model_id}",
                "strengths": ["backend", "reasoning", "refactor", "tests"],
                "preferred_roles": ["coder", "debug", "fixer", "tester"],
                "fallbacks": ["claude-sonnet"],
            },
            "claude-sonnet": {
                "model": f"anthropic/{anthropic_model_id}",
                "strengths": ["frontend", "ui", "review", "code"],
                "preferred_roles": ["coder", "debug", "fixer", "reviewer"],
                "fallbacks": ["gpt-5.4"],
            },
        }
        default_model = "gpt-5.4"
    else:
        raise ValueError("provider must be one of: openai-compatible, anthropic-native, both")

    return {
        "providers": providers,
        "models": models,
        "workers": {
            "write": {
                "role": "coder",
                "tool_policy": "product-write",
                "model": default_model,
                "skills": ["coder"],
                "max_iterations": 30,
            },
            "debug": {
                "role": "debug",
                "tool_policy": "product-write",
                "model": default_model,
                "skills": ["debug"],
                "max_iterations": 30,
            },
            "fix": {
                "role": "fixer",
                "tool_policy": "product-write",
                "model": default_model,
                "skills": ["fixer"],
                "max_iterations": 30,
            },
            "verify": {
                "role": "tester",
                "tool_policy": "test-write-only",
                "model": default_model,
                "skills": ["tester"],
                "max_iterations": 20,
            },
            "review": {
                "role": "reviewer",
                "tool_policy": "read-only-review",
                "model": "claude-sonnet" if provider == "both" else default_model,
                "skills": ["reviewer"],
                "max_iterations": 20,
            },
        },
        "journal": {
            "enabled": False,
            "path": "~/.nanoworker/journal.jsonl",
        },
    }
