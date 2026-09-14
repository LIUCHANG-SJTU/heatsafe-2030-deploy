from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorldPopEndpoint(StrEnum):
    AGESEX = "agesex"
    POPULATION = "population"


class WorldPopQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: WorldPopEndpoint
    geojson: dict[str, Any]
    year: int = Field(default=2026, ge=2015, le=2030)
    resolution: Literal["100m", "1km"] = "100m"
    sex: Literal["male", "female", "both"] | None = None
    age_range: tuple[int, int] | None = None

    def api_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "geojson": self.geojson,
            "year": self.year,
            "resolution": self.resolution,
        }
        if self.endpoint == WorldPopEndpoint.AGESEX:
            payload["sex"] = self.sex or "both"
            if self.age_range is not None:
                payload["age_range"] = list(self.age_range)
        return payload


class TaskSubmission(BaseModel):
    task_id: str
    status: str
    message: str = ""
    check_url: str = ""


class TaskStatus(BaseModel):
    task_id: str
    status: str
    progress: float | None = None
    stage: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class CachedTaskResult(BaseModel):
    request_hash: str
    task_id: str
    result: dict[str, Any]
    response_path: Path
    cache_hit: bool
    submitted_at: datetime | None = None
    retrieved_at: datetime


class WorldPopGridPopulation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grid_id: str
    geometry_wgs84: dict[str, Any]
    centroid_lat: float
    centroid_lon: float
    projected_crs: str
    area_m2: float
    population_total: float = Field(ge=0)
    population_age_0_14: float = Field(ge=0)
    population_age_65_plus: float = Field(ge=0)
    data_source: str
    source_id: str
    task_id: str
    request_hash: str
    raw_response_path: str
    data_mode: Literal["REAL"] = "REAL"

    @model_validator(mode="after")
    def validate_age_subsets(self) -> "WorldPopGridPopulation":
        tolerance = max(1e-6, self.population_total * 1e-6)
        if self.population_age_0_14 > self.population_total + tolerance:
            raise ValueError("estimated age 0-14 population exceeds total")
        if self.population_age_65_plus > self.population_total + tolerance:
            raise ValueError("estimated age 65+ population exceeds total")
        if (
            self.population_age_0_14 + self.population_age_65_plus
            > self.population_total + tolerance
        ):
            raise ValueError("estimated child and elderly populations exceed total")
        return self


class WorldPopArtifact(BaseModel):
    data_mode: Literal["REAL"] = "REAL"
    population_description: str = "estimated population"
    provider: str = "WorldPop"
    api_url: str
    year: int = 2026
    resolution: str = "100m"
    projected_crs: str
    pilot_bbox_wgs84: tuple[float, float, float, float]
    grids: list[WorldPopGridPopulation]


class PopulationConservationAudit(BaseModel):
    pilot_bbox: tuple[float, float, float, float]
    projected_crs: str
    grid_count: int
    total_population_sum: float
    population_age_0_14_sum: float
    population_age_65_plus_sum: float
    whole_area_population: float | None
    population_conservation_absolute_difference: float | None
    population_conservation_relative_difference: float | None
    population_conservation_status: str
    population_conservation_note: str
    successful_tasks: int
    failed_tasks: int
    cached_tasks: int
    http_request_count: int
    http_request_count_this_run: int
    data_source: str
    year: int
    resolution: str
    license: str
    data_mode_population: Literal["REAL"] = "REAL"
    data_mode_analysis: Literal["MIXED"] = "MIXED"
