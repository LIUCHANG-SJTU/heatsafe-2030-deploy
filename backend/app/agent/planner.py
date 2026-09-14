from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.models.api import AnalysisRequest


class ToolName(StrEnum):
    CLIMATE = "climate"
    THERMAL = "thermal"
    POPULATION = "population"
    VULNERABILITY = "vulnerability"
    GREEN_CAPACITY = "green_capacity"
    RISK_ENGINE = "risk_engine"


class AnalysisPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area: tuple[float, float, float, float] | None
    requested_scenario: dict[str, float]
    required_tools: list[ToolName]
    output_requirements: list[str]
    population_mode: str
    temperature_mode: str
    vegetation_mode: str
    temporal_mode: str


class DeterministicPlanner:
    """M0 stand-in for a future provider-agnostic structured LLM planner."""

    def plan(self, request: AnalysisRequest) -> AnalysisPlan:
        return AnalysisPlan(
            area=request.bbox,
            requested_scenario={
                "temperature_delta": request.scenario_temperature_delta
            },
            required_tools=list(ToolName),
            output_requirements=[
                "summary",
                "top_risk_grids",
                "statistics",
                "provenance",
            ],
            population_mode=request.population_mode,
            temperature_mode=request.temperature_mode,
            vegetation_mode=request.vegetation_mode,
            temporal_mode=request.temporal_mode,
        )
