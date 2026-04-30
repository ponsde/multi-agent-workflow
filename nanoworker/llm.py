"""LLM integration via litellm."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from nanoworker.config import Config


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON string


@dataclass(frozen=True)
class LLMResponse:
    content: str | None
    tool_calls: tuple[ToolCall, ...]
    finish_reason: str


def setup_provider_env(config: Config, model: str) -> None:
    """Set environment variables for litellm based on model prefix.

    Existing environment variables work without config. Config may point to
    custom env names so secrets can stay in shell/GitHub Actions secrets.
    """
    prefix = model.split("/")[0] if "/" in model else ""
    matched_provider = False

    for name, provider in config.providers.items():
        if prefix and prefix != name:
            continue
        matched_provider = True

        api_key = _value_from_env_or_literal(provider.api_key_env, provider.api_key, fallback_env="LLM_API_KEY")
        if api_key:
            _set_if_missing(_api_key_env_name(name), api_key)

        api_base = _value_from_env_or_literal(provider.api_base_env, provider.api_base, fallback_env="LLM_API_BASE")
        if api_base:
            for env_name in _api_base_env_names(name):
                _set_if_missing(env_name, api_base)

    if prefix and not matched_provider:
        api_key = os.environ.get("LLM_API_KEY")
        api_base = os.environ.get("LLM_API_BASE")
        if api_key:
            _set_if_missing(_api_key_env_name(prefix), api_key)
        if api_base:
            for env_name in _api_base_env_names(prefix):
                _set_if_missing(env_name, api_base)


def _value_from_env_or_literal(
    env_name: str | None,
    literal: str | None,
    fallback_env: str | None = None,
) -> str | None:
    if env_name:
        value = os.environ.get(env_name)
        if value:
            return value
    if fallback_env:
        value = os.environ.get(fallback_env)
        if value:
            return value
    return literal or None


def _set_if_missing(env_name: str, value: str) -> None:
    os.environ.setdefault(env_name, value)


def _api_key_env_name(provider_name: str) -> str:
    if provider_name == "openai":
        return "OPENAI_API_KEY"
    if provider_name == "anthropic":
        return "ANTHROPIC_API_KEY"
    return f"{provider_name.upper()}_API_KEY"


def _api_base_env_names(provider_name: str) -> tuple[str, ...]:
    if provider_name == "openai":
        return ("OPENAI_API_BASE", "OPENAI_BASE_URL")
    if provider_name == "anthropic":
        return ("ANTHROPIC_API_BASE", "ANTHROPIC_BASE_URL")
    return (f"{provider_name.upper()}_API_BASE",)


def _normalize_tool_call_id(tc_id: str) -> str:
    """Return tool call IDs unchanged for OpenAI-compatible providers."""
    return tc_id


async def chat(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> LLMResponse:
    """Call LLM via litellm and return parsed response."""
    from litellm import acompletion

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools

    response = await acompletion(**kwargs)
    choice = response.choices[0]
    message = choice.message

    tool_calls = ()
    if message.tool_calls:
        tool_calls = tuple(
            ToolCall(
                id=_normalize_tool_call_id(tc.id),
                name=tc.function.name,
                arguments=tc.function.arguments,
            )
            for tc in message.tool_calls
        )

    return LLMResponse(
        content=message.content,
        tool_calls=tool_calls,
        finish_reason=choice.finish_reason,
    )
