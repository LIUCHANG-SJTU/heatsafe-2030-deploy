from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .grid import ComponentModes, DataMode, GridCell, ModelStatus
from .era5 import ERA5TemporalContext
from .provenance import ProvenanceRecord


class AnalysisRequest(BaseModel):
    bbox: tuple[float, float, float, float] | None = None
    scenario_temperature_delta: float = Field(default=0, ge=0, le=5)
    top_n: int = Field(default=10, ge=1, le=50)
    population_mode: Literal["fixture", "real"] = "fixture"
    temperature_mode: Literal["fixture", "real"] = "fixture"
    vegetation_mode: Literal["fixture", "real"] = "fixture"
    temporal_mode: Literal["fixture", "real"] = "fixture"

    @model_validator(mode="after")
    def ordered_bbox(self) -> "AnalysisRequest":
        if self.bbox is not None:
            west, south, east, north = self.bbox
            if west >= east or south >= north:
                raise ValueError("bbox must be ordered [west, south, east, north]")
        return self


class ScenarioRequest(BaseModel):
    temperature_delta: float = Field(ge=0, le=5)
    bbox: tuple[float, float, float, float] | None = None
    population_mode: Literal["fixture", "real"] = "fixture"
    temperature_mode: Literal["fixture", "real"] = "fixture"
    vegetation_mode: Literal["fixture", "real"] = "fixture"
    temporal_mode: Literal["fixture", "real"] = "fixture"


class AnalysisSummary(BaseModel):
    area_label: str
    data_mode: DataMode
    grid_count: int
    scenario_temperature_delta: float
    high_risk_grid_count: int
    exposed_population_in_high_risk_grids: int
    disclaimer: str


class AnalysisResponse(BaseModel):
    data_mode: DataMode
    model_status: ModelStatus = ModelStatus.PRELIMINARY_HEURISTIC
    component_modes: ComponentModes
    summary: AnalysisSummary
    top_risk_grids: list[GridCell]
    statistics: dict[str, Any]
    provenance: list[dict[str, Any]]
    temporal_context: ERA5TemporalContext | None = None
    methods: dict[str, str] = Field(default_factory=dict)
