from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class ToolChoiceMode(StrEnum):
    AUTO = "auto"
    REQUIRED = "required"


@dataclass
class ProviderTurn:
    text: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    model: str = ""
    latency_ms: float = 0
    finish_reason: str | None = None


class LLMProvider(Protocol):
    name: str
    model: str

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], metadata: dict[str, Any]) -> ProviderTurn:
        ...
