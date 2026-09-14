from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional for minimal deployments
    load_dotenv = None


if load_dotenv is not None:
    # Local developer configuration is backend-only and remains gitignored.
    # Existing process environment values take precedence over the file.
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)


@dataclass(frozen=True)
class AgentSettings:
    provider: str = os.getenv("HEATSAFE_AGENT_PROVIDER", "")
    base_url: str = os.getenv("HEATSAFE_AGENT_BASE_URL", "").rstrip("/")
    api_key: str = os.getenv("HEATSAFE_AGENT_API_KEY", "")
    model: str = os.getenv("HEATSAFE_AGENT_MODEL", "")
    thinking_mode: str = os.getenv("HEATSAFE_AGENT_THINKING", "").strip().lower()
    timeout_seconds: float = float(os.getenv("HEATSAFE_AGENT_TIMEOUT_SECONDS", "60"))
    max_output_tokens: int = int(os.getenv("HEATSAFE_AGENT_MAX_OUTPUT_TOKENS", "4096"))
    max_tool_steps: int = int(os.getenv("HEATSAFE_AGENT_MAX_TOOL_STEPS", "4"))
    max_concurrent: int = int(os.getenv("HEATSAFE_AGENT_MAX_CONCURRENT", "4"))

    @property
    def configured(self) -> bool:
        return bool(self.provider and self.base_url and self.api_key and self.model)


agent_settings = AgentSettings()
