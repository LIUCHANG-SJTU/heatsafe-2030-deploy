from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .base import ProviderTurn


class MockProvider:
    name = "mock"
    model = "mock-v1"

    def __init__(self, turns: list[ProviderTurn] | Callable[..., ProviderTurn] | None = None) -> None:
        self._turns = turns or []
        self.calls: list[dict[str, Any]] = []

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], metadata: dict[str, Any]) -> ProviderTurn:
        self.calls.append({"messages": messages, "tools": tools, "metadata": metadata})
        if callable(self._turns):
            return self._turns(messages, tools, metadata)
        if self._turns:
            return self._turns.pop(0)
        return ProviderTurn(text=None, model=self.model)
