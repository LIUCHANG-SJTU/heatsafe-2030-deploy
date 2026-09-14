from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AgentRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class AgentMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: AgentRole
    content: str = Field(min_length=1, max_length=6000)


class ActiveLayer(StrEnum):
    RISK = "risk_score"
    HAZARD = "hazard_score"
    EXPOSURE = "exposure_score"
    VULNERABILITY = "vulnerability_score"
    ADAPTIVE_GAP = "adaptive_capacity_gap"
    POPULATION = "population_total"
    LST = "lst_median_c"
    GREEN = "green_fraction_land"
    WATER = "water_fraction_grid"


class AgentUIContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_grid_id: str | None = None
    active_layer: ActiveLayer | None = None
    focused_hotspot_id: str | None = None
    agent_highlighted_grid_ids: list[str] = Field(default_factory=list, max_length=20)
    locale: Literal["zh-CN", "en"] = "zh-CN"


class AgentQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[AgentMessage] = Field(min_length=1, max_length=12)
    context: AgentUIContext = Field(default_factory=AgentUIContext)
    session_id: str | None = Field(default=None, max_length=128)

    @field_validator("messages")
    @classmethod
    def validate_history(cls, messages: list[AgentMessage]) -> list[AgentMessage]:
        if any(len(message.content) > 4000 for message in messages if message.role == AgentRole.USER):
            raise ValueError("user message exceeds 4000 characters")
        return messages


class FilterOperator(StrEnum):
    EQ = "eq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"


QUERY_FIELDS = {
    "risk_score", "risk_percentile_within_aoi", "hazard_score", "exposure_score",
    "vulnerability_score", "adaptive_capacity_score", "population_total",
    "lst_median_c", "green_fraction_land", "water_fraction_grid", "analysis_status",
    "primary_driver", "ranking_eligible",
}


class GridFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    op: FilterOperator
    value: Any

    @field_validator("field")
    @classmethod
    def validate_field(cls, value: str) -> str:
        if value not in QUERY_FIELDS:
            raise ValueError(f"field is not queryable: {value}")
        return value

    @model_validator(mode="after")
    def validate_operator_value(self) -> "GridFilter":
        if self.op == FilterOperator.IN and not isinstance(self.value, list):
            raise ValueError("in operator requires a list value")
        if self.op != FilterOperator.IN and isinstance(self.value, list):
            raise ValueError("comparison operators require a scalar value")
        if self.op in {FilterOperator.GT, FilterOperator.GTE, FilterOperator.LT, FilterOperator.LTE} and self.field in {"analysis_status", "primary_driver", "ranking_eligible"}:
            raise ValueError(f"numeric comparison is invalid for {self.field}")
        return self


class QueryGridsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filters: list[GridFilter] = Field(default_factory=list, max_length=10)
    sort_by: str = "risk_score"
    sort_order: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=10, ge=1, le=20)

    @field_validator("sort_by")
    @classmethod
    def validate_sort(cls, value: str) -> str:
        value = {"population": "population_total"}.get(value, value)
        if value not in QUERY_FIELDS:
            raise ValueError(f"sort field is not queryable: {value}")
        return value


class CompareGridsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grid_ids: list[str] = Field(min_length=2, max_length=5)


class MethodologyTopic(StrEnum):
    OVERVIEW = "overview"
    RISK_FORMULA = "risk_formula"
    RISK_SCOPE = "risk_scope"
    HAZARD = "hazard"
    EXPOSURE = "exposure"
    VULNERABILITY = "vulnerability"
    ADAPTIVE_CAPACITY = "adaptive_capacity"
    WORLDPOP = "worldpop"
    LANDSAT = "landsat"
    SENTINEL2 = "sentinel2"
    ERA5 = "era5"
    WATER_RULE = "water_rule"
    QA = "qa"
    LIMITATIONS = "limitations"


class MapAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["select_grid", "highlight_grids", "focus_grids", "suggest_layer"]
    grid_ids: list[str] = Field(default_factory=list, max_length=20)
    layer: ActiveLayer | None = None


class AgentValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["PASS", "FAIL"]
    errors: list[str] = Field(default_factory=list)


class PublicToolTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    status: str
    duration_ms: float = 0
    result_count: int = 0


class AgentQualification(BaseModel):
    """Sanitized runtime facts for offline/live qualification; never includes prompts or secrets."""

    model_config = ConfigDict(extra="forbid")

    routing_source: str
    rendering_source: str
    provider_attempt_count: int = 0
    provider_turn_count: int = 0
    provider_tool_calls: list[str] = Field(default_factory=list)
    provider_finish_reasons: list[str] = Field(default_factory=list, max_length=12)
    provider_completion_tokens: int = 0
    tool_execution_count: int = 0
    first_attempt_tool_calls: list[str] = Field(default_factory=list)
    first_attempt_validation_status: str = "NOT_RUN"
    first_attempt_validation_errors: list[str] = Field(default_factory=list, max_length=20)
    last_provider_validation_errors: list[str] = Field(default_factory=list, max_length=20)
    validation_repair_used: bool = False
    validation_repair_count: int = 0
    validation_repair_success: bool = False
    early_finalizer_deferred: bool = False
    argument_normalization_used: bool = False
    tool_argument_canonicalization_used: bool = False
    canonicalized_fields: list[str] = Field(default_factory=list, max_length=20)
    semantic_intent: str = "UNCONSTRAINED"
    semantic_contract_status: str = "NOT_RUN"
    semantic_missing_evidence_slots: list[str] = Field(default_factory=list, max_length=20)
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
    semantic_completion_missing_slots: list[str] = Field(default_factory=list, max_length=20)
    semantic_completion_candidate_tools: list[str] = Field(default_factory=list, max_length=8)
    semantic_completion_candidate_count: int = 0
    semantic_completion_capability_filter_used: bool = False
    semantic_completion_selected_tool_capabilities: dict[str, list[str]] = Field(default_factory=dict)
    terminal_render_arbitration_used: bool = False
    terminal_render_candidate_tools: list[str] = Field(default_factory=list, max_length=20)
    terminal_render_candidate_coverage: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    terminal_render_full_contract_candidates: list[str] = Field(default_factory=list, max_length=20)
    terminal_render_selected_tool: str | None = None
    terminal_render_selection_reason: str | None = None
    compare_mode: str = ""
    query_intent_completeness_status: str = "NOT_RUN"
    query_intent_completeness_errors: list[str] = Field(default_factory=list, max_length=20)
    fallback_used: bool = False
    fallback_reason: str | None = None
    error_code: str | None = None
    final_validation_status: str
    provider_latency_ms: float = 0
    tool_latency_ms: float = 0
    validation_latency_ms: float = 0
    total_latency_ms: float = 0
    provider_result: Literal["PASS", "FAIL", "NOT_RUN"] = "NOT_RUN"
    user_visible_result: Literal["GROUNDED", "SAFE_FALLBACK", "SCOPE_LIMITATION"]


class AgentQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    answer: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    tool_trace: list[PublicToolTrace] = Field(default_factory=list)
    map_actions: list[MapAction] = Field(default_factory=list)
    validation: AgentValidation
    answer_mode: Literal["GROUNDED", "DETERMINISTIC_FALLBACK", "SCOPE_LIMITATION"]
    provider: str
    model: str
    latency_ms: float
    qualification: AgentQualification
