from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any


@dataclass
class AgentTrace:
    request_id: str
    started: float = field(default_factory=perf_counter)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    routing_source: str = ""
    rendering_source: str = ""
    provider_attempt_count: int = 0
    provider_turn_count: int = 0
    provider_tool_calls: list[str] = field(default_factory=list)
    provider_finish_reasons: list[str] = field(default_factory=list)
    provider_completion_tokens: int = 0
    tool_execution_count: int = 0
    first_attempt_tool_calls: list[str] = field(default_factory=list)
    first_attempt_validation_status: str = "NOT_RUN"
    first_attempt_validation_errors: list[str] = field(default_factory=list)
    last_provider_validation_errors: list[str] = field(default_factory=list)
    validation_repair_used: bool = False
    validation_repair_count: int = 0
    validation_repair_success: bool = False
    early_finalizer_deferred: bool = False
    argument_normalization_used: bool = False
    tool_argument_canonicalization_used: bool = False
    canonicalized_fields: list[str] = field(default_factory=list)
    semantic_intent: str = "UNCONSTRAINED"
    semantic_contract_status: str = "NOT_RUN"
    semantic_missing_evidence_slots: list[str] = field(default_factory=list)
    evidence_completion_used: bool = False
    evidence_completion_count: int = 0
    semantic_completion_used: bool = False
    semantic_completion_provider_attempts: int = 0
    terminal_action_gated: bool = False
    terminal_action_gate_reason: str | None = None
    agent_state: str = "PLANNING"
    semantic_completion_tool_required: bool = False
    semantic_completion_tool_choice_mode: str = "AUTO"
    semantic_completion_public_tool_called: bool = False
    semantic_completion_selected_tool: str | None = None
    semantic_completion_missing_slots: list[str] = field(default_factory=list)
    semantic_completion_candidate_tools: list[str] = field(default_factory=list)
    semantic_completion_candidate_count: int = 0
    semantic_completion_capability_filter_used: bool = False
    semantic_completion_selected_tool_capabilities: dict[str, list[str]] = field(default_factory=dict)
    terminal_render_arbitration_used: bool = False
    terminal_render_candidate_tools: list[str] = field(default_factory=list)
    terminal_render_candidate_coverage: list[dict[str, Any]] = field(default_factory=list)
    terminal_render_full_contract_candidates: list[str] = field(default_factory=list)
    terminal_render_selected_tool: str | None = None
    terminal_render_selection_reason: str | None = None
    compare_mode: str = ""
    query_intent_completeness_status: str = "NOT_RUN"
    query_intent_completeness_errors: list[str] = field(default_factory=list)
    validation_status: str = ""
    fallback_used: bool = False
    fallback_reason: str | None = None
    provider_latency_ms: float = 0
    tool_latency_ms: float = 0
    validation_latency_ms: float = 0
    error_code: str | None = None

    def finish(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "total_latency_ms": (perf_counter() - self.started) * 1000,
            "tool_calls": self.tool_calls,
            "routing_source": self.routing_source,
            "rendering_source": self.rendering_source,
            "provider_attempt_count": self.provider_attempt_count,
            "provider_turn_count": self.provider_turn_count,
            "provider_tool_calls": self.provider_tool_calls,
            "provider_finish_reasons": self.provider_finish_reasons,
            "provider_completion_tokens": self.provider_completion_tokens,
            "tool_execution_count": self.tool_execution_count,
            "first_attempt_tool_calls": self.first_attempt_tool_calls,
            "first_attempt_validation_status": self.first_attempt_validation_status,
            "first_attempt_validation_errors": self.first_attempt_validation_errors,
            "last_provider_validation_errors": self.last_provider_validation_errors,
            "validation_repair_used": self.validation_repair_used,
            "validation_repair_count": self.validation_repair_count,
            "validation_repair_success": self.validation_repair_success,
            "early_finalizer_deferred": self.early_finalizer_deferred,
            "argument_normalization_used": self.argument_normalization_used,
            "tool_argument_canonicalization_used": self.tool_argument_canonicalization_used,
            "canonicalized_fields": self.canonicalized_fields,
            "semantic_intent": self.semantic_intent,
            "semantic_contract_status": self.semantic_contract_status,
            "semantic_missing_evidence_slots": self.semantic_missing_evidence_slots,
            "evidence_completion_used": self.evidence_completion_used,
            "evidence_completion_count": self.evidence_completion_count,
            "semantic_completion_used": self.semantic_completion_used,
            "semantic_completion_provider_attempts": self.semantic_completion_provider_attempts,
            "terminal_action_gated": self.terminal_action_gated,
            "terminal_action_gate_reason": self.terminal_action_gate_reason,
            "agent_state": self.agent_state,
            "semantic_completion_tool_required": self.semantic_completion_tool_required,
            "semantic_completion_tool_choice_mode": self.semantic_completion_tool_choice_mode,
            "semantic_completion_public_tool_called": self.semantic_completion_public_tool_called,
            "semantic_completion_selected_tool": self.semantic_completion_selected_tool,
            "semantic_completion_missing_slots": self.semantic_completion_missing_slots,
            "semantic_completion_candidate_tools": self.semantic_completion_candidate_tools,
            "semantic_completion_candidate_count": self.semantic_completion_candidate_count,
            "semantic_completion_capability_filter_used": self.semantic_completion_capability_filter_used,
            "semantic_completion_selected_tool_capabilities": self.semantic_completion_selected_tool_capabilities,
            "terminal_render_arbitration_used": self.terminal_render_arbitration_used,
            "terminal_render_candidate_tools": self.terminal_render_candidate_tools,
            "terminal_render_candidate_coverage": self.terminal_render_candidate_coverage,
            "terminal_render_full_contract_candidates": self.terminal_render_full_contract_candidates,
            "terminal_render_selected_tool": self.terminal_render_selected_tool,
            "terminal_render_selection_reason": self.terminal_render_selection_reason,
            "compare_mode": self.compare_mode,
            "query_intent_completeness_status": self.query_intent_completeness_status,
            "query_intent_completeness_errors": self.query_intent_completeness_errors,
            "validation_status": self.validation_status,
            "final_validation_status": self.validation_status,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "provider_latency_ms": self.provider_latency_ms,
            "tool_latency_ms": self.tool_latency_ms,
            "validation_latency_ms": self.validation_latency_ms,
            "error_code": self.error_code,
        }
