"""LLM integration via litellm."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import litellm
from litellm import acompletion

from nanoworker.config import Config

# Disable Responses API routing — custom proxies don't support /v1/responses.
# Monkey-patch the bridge check to never return mode="responses".
import litellm.main as _litellm_main

_orig_responses_check = _litellm_main.responses_api_bridge_check


def _patched_responses_check(model, custom_llm_provider, **kwargs):
    model_info, model = _orig_responses_check(model, custom_llm_provider, **kwargs)
    model_info.pop("mode", None)
    return model_info, model


_litellm_main.responses_api_bridge_check = _patched_responses_check


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
    """Set environment variables for litellm based on model prefix."""
    prefix = model.split("/")[0] if "/" in model else ""

    for name, provider in config.providers.items():
        if prefix and prefix != name:
            continue
        if provider.api_key:
            env_key = f"{name.upper()}_API_KEY"
            if name == "openai":
                env_key = "OPENAI_API_KEY"
            elif name == "anthropic":
                env_key = "ANTHROPIC_API_KEY"
            os.environ[env_key] = provider.api_key

        if provider.api_base:
            if name == "openai":
                os.environ["OPENAI_API_BASE"] = provider.api_base


async def chat(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> LLMResponse:
    """Call LLM via litellm and return parsed response."""
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
                id=tc.id,
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
