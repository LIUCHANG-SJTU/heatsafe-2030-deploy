from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SpatiotemporalHazardGrid(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grid_id: str
    spatial_heat_score: float = Field(ge=0, le=1)
    temporal_context_id: str
    temporal_severity_score: float = Field(ge=0, le=1)
    hazard_score: float = Field(ge=0, le=1)
    source_mode: Literal["REAL"] = "REAL"
    method: Literal["SPATIOTEMPORAL_HEAT_HAZARD_HEURISTIC"] = (
        "SPATIOTEMPORAL_HEAT_HAZARD_HEURISTIC"
    )


class SpatiotemporalHazardArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_mode: Literal["REAL"] = "REAL"
    temporal_context_id: str
    source_id: str
    grids: list[SpatiotemporalHazardGrid]
