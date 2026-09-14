from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .landsat import CoverageQuality


class AdaptiveCapacityProxy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float | None = Field(default=None, ge=0, le=1)
    source_mode: Literal["REAL"] = "REAL"
    method: Literal["VEGETATION_PROXY_HEURISTIC"] = "VEGETATION_PROXY_HEURISTIC"


class SentinelGridVegetation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grid_id: str
    scene_id: str
    platform: str
    acquisition_datetime: datetime
    ndvi_mean: float | None = Field(default=None, ge=-1, le=1)
    ndvi_median: float | None = Field(default=None, ge=-1, le=1)
    ndvi_p25: float | None = Field(default=None, ge=-1, le=1)
    ndvi_p75: float | None = Field(default=None, ge=-1, le=1)
    green_fraction_grid: float | None = Field(default=None, ge=0, le=1)
    green_fraction_land: float | None = Field(default=None, ge=0, le=1)
    green_pixel_count: int = Field(ge=0)
    valid_land_pixel_count: int = Field(ge=0)
    valid_observation_pixel_count: int = Field(ge=0)
    total_analysis_pixel_count: int = Field(ge=0)
    valid_observation_fraction: float = Field(ge=0, le=1)
    valid_land_fraction: float = Field(ge=0, le=1)
    quality_flag: CoverageQuality
    source_mode: Literal["REAL"] = "REAL"
    source_id: str
    adaptive_capacity: AdaptiveCapacityProxy

    @model_validator(mode="after")
    def counts_and_quality_are_consistent(self) -> "SentinelGridVegetation":
        if not (
            self.green_pixel_count
            <= self.valid_land_pixel_count
            <= self.valid_observation_pixel_count
            <= self.total_analysis_pixel_count
        ):
            raise ValueError("vegetation pixel counts must be monotonically bounded")
        if self.valid_land_pixel_count == 0 and self.green_fraction_land is not None:
            raise ValueError("green_fraction_land must be None without valid land")
        if self.quality_flag == CoverageQuality.INSUFFICIENT:
            if self.adaptive_capacity.score is not None:
                raise ValueError("INSUFFICIENT grids cannot publish adaptive capacity")
        elif self.adaptive_capacity.score is None:
            raise ValueError("usable grids require adaptive capacity score")
        return self


class SentinelVegetationArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_mode: Literal["REAL"] = "REAL"
    model_status: Literal["PRELIMINARY_HEURISTIC"] = "PRELIMINARY_HEURISTIC"
    pilot_name: str
    pilot_bbox_wgs84: tuple[float, float, float, float]
    analysis_crs: str
    analysis_resolution_meters: int = 10
    collection: str
    scene_ids: list[str] = Field(min_length=1)
    is_composite: bool = False
    source_id: str
    grids: list[SentinelGridVegetation]

