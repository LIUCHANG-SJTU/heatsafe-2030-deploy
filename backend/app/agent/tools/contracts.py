from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..schemas import CompareGridsInput, GridFilter, MethodologyTopic, QueryGridsInput


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GridInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grid_id: str = Field(min_length=1, max_length=128)


class HotspotsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=10, ge=1, le=10)


class MethodologyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: MethodologyTopic


class RecommendActionsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["selected_grid", "grid", "hotspots"]
    grid_id: str | None = Field(default=None, min_length=1, max_length=128)
    limit: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def validate_scope(self) -> "RecommendActionsInput":
        if self.scope in {"selected_grid", "grid"} and not self.grid_id:
            raise ValueError(f"{self.scope} action scope requires grid_id")
        if self.scope == "hotspots" and self.grid_id is not None:
            raise ValueError("hotspots action scope does not accept grid_id")
        if self.scope != "hotspots" and self.limit > 4:
            raise ValueError("grid action plans support at most four action cards")
        return self


class ToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    input_model: type[BaseModel]


PUBLIC_TOOL_DEFINITIONS = [
    ToolDefinition(name="get_demo_summary", description="Read the current HeatSafe analysis summary and metadata.", input_model=EmptyInput),
    ToolDefinition(name="inspect_grid", description="Read complete evidence for one real analysis grid, including population and LST. Use this for requests to check or inspect a grid (检查/查看网格); do not use explain_risk unless the user asks why its risk is high, and do not call both for one request.", input_model=GridInput),
    ToolDefinition(name="list_hotspots", description="List the backend-ranked top hotspots.", input_model=HotspotsInput),
    ToolDefinition(name="compare_grids", description="Compare two to five real grid records, including a selected grid and a named or ranked peer. Use this for compare/difference questions after any needed read-only lookup.", input_model=CompareGridsInput),
    ToolDefinition(name="query_grids", description="Filter and sort grids using the allowlisted query fields.", input_model=QueryGridsInput),
    ToolDefinition(name="explain_risk", description="Return deterministic contribution evidence and the complete grid evidence for one grid. Prefer this single call for why-risk questions; do not call inspect_grid separately.", input_model=GridInput),
    ToolDefinition(name="get_methodology", description="Read frozen HeatSafe methodology and limitations.", input_model=MethodologyInput),
    ToolDefinition(
        name="recommend_actions",
        description=(
            "Return deterministic, guidance-backed urban heat action priorities for a selected/explicit grid "
            "or a compact hotspot overview. Use this when the user asks what action should be prioritized. "
            "This tool does not estimate intervention effects, costs, budgets, or future risk."
        ),
        input_model=RecommendActionsInput,
    ),
]


def tool_names() -> list[str]:
    return [definition.name for definition in PUBLIC_TOOL_DEFINITIONS]


def provider_tool_schemas() -> list[dict[str, object]]:
    """Return provider-neutral function schemas without weakening Pydantic validation."""
    return [
        {
            "type": "function",
            "function": {
                "name": definition.name,
                "description": definition.description,
                "parameters": definition.input_model.model_json_schema(),
            },
        }
        for definition in PUBLIC_TOOL_DEFINITIONS
    ]


def finalizer_tool_schema() -> dict[str, object]:
    from ..finalizer import GroundedAnswer

    return {
        "type": "function",
        "function": {
            "name": "submit_grounded_answer",
            "description": "Finalize concise non-empty claims with exact evidence IDs; do not add unsupported numbers.",
            "parameters": GroundedAnswer.model_json_schema(),
            "strict": True,
        },
    }
