from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

from ..tools.contracts import finalizer_tool_schema, provider_tool_schemas
from ..finalizer import GroundedAnswer
from .base import LLMProvider
from .base import ToolChoiceMode


@dataclass(frozen=True)
class ProviderQualification:
    simple_completion: bool
    native_tool_calling: bool
    finalizer_support: bool
    simple_latency_ms: float = 0
    tool_latency_ms: float = 0
    finalizer_latency_ms: float = 0
    errors: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RequiredToolChoiceQualification:
    supported: bool
    selected_tool: str | None = None
    latency_ms: float = 0
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


async def qualify_required_tool_choice(provider: LLMProvider) -> RequiredToolChoiceQualification:
    """Verify generic required mode without naming or executing a business tool."""
    import time

    tools = provider_tool_schemas()
    public_names = {str(item["function"]["name"]) for item in tools}
    started = time.perf_counter()
    try:
        turn = await provider.complete(
            [
                {
                    "role": "system",
                    "content": "Protocol capability check only. Select exactly one available public function. Do not answer with text.",
                },
                {"role": "user", "content": "Select an available function now."},
            ],
            tools,
            {
                "qualification": "generic_required_tool_choice",
                "tool_choice_mode": ToolChoiceMode.REQUIRED,
            },
        )
        selected = next((str(call.get("name")) for call in turn.tool_calls if call.get("name") in public_names), None)
        return RequiredToolChoiceQualification(
            supported=selected is not None,
            selected_tool=selected,
            latency_ms=(time.perf_counter() - started) * 1000,
            error=None if selected is not None else "NO_PUBLIC_TOOL_CALL",
        )
    except Exception as error:
        return RequiredToolChoiceQualification(
            supported=False,
            latency_ms=(time.perf_counter() - started) * 1000,
            error=f"{type(error).__name__}:{str(error)[:240]}",
        )


async def qualify_provider_protocol(provider: LLMProvider) -> ProviderQualification:
    """Exercise the provider protocol directly, without the deterministic Agent router."""
    import time

    errors: list[str] = []
    simple = tool = finalizer = False
    timings: list[float] = []
    try:
        started = time.perf_counter()
        simple_turn = await provider.complete(
            [{"role": "user", "content": "Reply with the word READY."}], [], {"qualification": "simple_completion"}
        )
        timings.append((time.perf_counter() - started) * 1000)
        simple = bool(simple_turn.text or simple_turn.tool_calls)
    except Exception as error:
        errors.append(f"simple_completion:{type(error).__name__}")
    try:
        started = time.perf_counter()
        tool_turn = await provider.complete(
            [{"role": "user", "content": "Use get_demo_summary now."}],
            provider_tool_schemas(),
            {"qualification": "native_tool_calling"},
        )
        timings.append((time.perf_counter() - started) * 1000)
        tool = any(call.get("name") == "get_demo_summary" for call in tool_turn.tool_calls)
        if not tool:
            errors.append("native_tool_calling:no_get_demo_summary_call")
    except Exception as error:
        errors.append(f"native_tool_calling:{type(error).__name__}")
    try:
        started = time.perf_counter()
        finalizer_turn = await provider.complete(
            [
                {"role": "system", "content": "You must call submit_grounded_answer. Use only the supplied evidence and cite its exact evidence_id."},
                {"role": "user", "content": "Evidence: [{\"evidence_id\":\"E1\",\"metric\":\"risk_score\",\"value\":42.5,\"grid_id\":\"qualification-grid\"}]. Submit one grounded claim that cites E1."},
            ],
            [finalizer_tool_schema()],
            {
                "qualification": "finalizer_support",
                "tool_choice": {"type": "function", "function": {"name": "submit_grounded_answer"}},
            },
        )
        timings.append((time.perf_counter() - started) * 1000)
        finalizer = False
        for call in finalizer_turn.tool_calls:
            if call.get("name") != "submit_grounded_answer":
                continue
            arguments = call.get("arguments", {})
            if isinstance(arguments, str):
                arguments = json.loads(arguments or "{}")
            GroundedAnswer.model_validate(arguments)
            finalizer = True
            break
        if not finalizer:
            errors.append("finalizer_support:no_submit_grounded_answer_call")
    except Exception as error:
        errors.append(f"finalizer_support:{type(error).__name__}")
    return ProviderQualification(
        simple_completion=simple,
        native_tool_calling=tool,
        finalizer_support=finalizer,
        simple_latency_ms=timings[0] if len(timings) > 0 else 0,
        tool_latency_ms=timings[1] if len(timings) > 1 else 0,
        finalizer_latency_ms=timings[2] if len(timings) > 2 else 0,
        errors=tuple(errors),
    )
