from __future__ import annotations

import time
from typing import Any

import httpx

from .base import ProviderTurn, ToolChoiceMode


class OpenAICompatibleProvider:
    """Small provider-neutral adapter for OpenAI-compatible chat endpoints."""

    name = "openai_compatible"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 60,
        max_output_tokens: int = 4096,
        thinking_mode: str = "",
    ) -> None:
        thinking_mode = thinking_mode.strip().lower()
        if thinking_mode not in {"", "enabled", "disabled"}:
            raise ValueError("thinking_mode must be enabled, disabled, or unset")
        self.base_url, self.api_key, self.model, self.timeout_seconds, self.max_output_tokens = base_url.rstrip("/"), api_key, model, timeout_seconds, max_output_tokens
        self.thinking_mode = thinking_mode

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], metadata: dict[str, Any]) -> ProviderTurn:
        started = time.perf_counter()
        if "tool_choice" in metadata and "tool_choice_mode" in metadata:
            raise ValueError("tool_choice and tool_choice_mode are mutually exclusive")
        tool_choice_mode = metadata.get("tool_choice_mode")
        if tool_choice_mode is not None:
            try:
                tool_choice = ToolChoiceMode(tool_choice_mode).value
            except ValueError as error:
                raise ValueError(f"unsupported tool_choice_mode: {tool_choice_mode}") from error
        else:
            tool_choice = metadata.get("tool_choice", "auto")
        valid_string_choice = isinstance(tool_choice, str) and tool_choice in {"auto", "none", "required"}
        valid_function_choice = (
            isinstance(tool_choice, dict)
            and tool_choice.get("type") == "function"
            and isinstance(tool_choice.get("function", {}).get("name"), str)
        )
        if not (valid_string_choice or valid_function_choice):
            tool_choice = "auto"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": _wire_messages(messages),
            "temperature": 0.1,
            "tools": tools,
            "tool_choice": tool_choice,
            # A single sequential tool call keeps the tool-result/finalizer
            # protocol deterministic across OpenAI-compatible providers.
            "parallel_tool_calls": False,
        }
        if self.max_output_tokens > 0:
            payload["max_tokens"] = self.max_output_tokens
        if self.thinking_mode:
            payload["thinking"] = {"type": self.thinking_mode}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
        body = response.json()
        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        calls = []
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            calls.append({"id": call.get("id"), "name": function.get("name"), "arguments": function.get("arguments", "{}")})
        return ProviderTurn(
            text=message.get("content"),
            tool_calls=calls,
            usage=body.get("usage") or {},
            model=body.get("model", self.model),
            latency_ms=(time.perf_counter() - started) * 1000,
            finish_reason=choice.get("finish_reason"),
        )


def _wire_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize internal tool calls to the OpenAI-compatible assistant wire shape."""
    normalized: list[dict[str, Any]] = []
    for message in messages:
        item = dict(message)
        if item.get("role") == "assistant" and item.get("tool_calls"):
            calls = []
            for index, call in enumerate(item["tool_calls"], start=1):
                if call.get("function"):
                    normalized_call = dict(call)
                    normalized_call["id"] = call.get("id") or f"tool-call-{index}"
                    calls.append(normalized_call)
                else:
                    arguments = call.get("arguments", {})
                    if not isinstance(arguments, str):
                        import json
                        arguments = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
                    calls.append({"id": call.get("id") or f"tool-call-{index}", "type": "function", "function": {"name": call.get("name", ""), "arguments": arguments}})
            item["tool_calls"] = calls
        normalized.append(item)
    return normalized
