from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CoverageQuality(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT = "INSUFFICIENT"


def coverage_quality(valid_fraction: float) -> CoverageQuality:
    if valid_fraction >= 0.80:
        return CoverageQuality.HIGH
    if valid_fraction >= 0.50:
        return CoverageQuality.MEDIUM
    if valid_fraction >= 0.20:
        return CoverageQuality.LOW
    return CoverageQuality.INSUFFICIENT


class LandsatGridTemperature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grid_id: str
    scene_id: str
    product_id: str
    platform: str
    acquisition_datetime: datetime
    land_surface_temperature_c: float | None
    lst_mean_c: float | None
    lst_median_c: float | None
    lst_p90_c: float | None
    lst_min_c: float | None
    lst_max_c: float | None
    valid_pixel_count: int = Field(ge=0)
    total_pixel_count: int = Field(ge=0)
    valid_pixel_fraction: float = Field(ge=0, le=1)
    quality_flag: CoverageQuality
    source_mode: Literal["REAL"] = "REAL"
    source_id: str

    @model_validator(mode="after")
    def statistics_match_coverage(self) -> "LandsatGridTemperature":
        if self.valid_pixel_count > self.total_pixel_count:
            raise ValueError("valid_pixel_count cannot exceed total_pixel_count")
        values = (
            self.land_surface_temperature_c,
            self.lst_mean_c,
            self.lst_median_c,
            self.lst_p90_c,
            self.lst_min_c,
            self.lst_max_c,
        )
        if self.quality_flag == CoverageQuality.INSUFFICIENT:
            if any(value is not None for value in values):
                raise ValueError("INSUFFICIENT grids must not publish LST statistics")
        elif any(value is None for value in values):
            raise ValueError("usable grids require complete LST statistics")
        if (
            self.land_surface_temperature_c is not None
            and self.lst_median_c is not None
            and abs(self.land_surface_temperature_c - self.lst_median_c) > 1e-9
        ):
            raise ValueError("land_surface_temperature_c must equal the median LST")
        return self


class LandsatArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_mode: Literal["REAL"] = "REAL"
    pilot_name: str
    pilot_bbox_wgs84: tuple[float, float, float, float]
    collection: str
    scene_id: str
    product_id: str
    platform: str
    acquisition_datetime: datetime
    source_id: str
    grids: list[LandsatGridTemperature]


class SceneCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    product_id: str
    platform: str
    acquisition_datetime: datetime
    scene_cloud_cover: float
    pilot_total_pixels: int = 0
    pilot_valid_pixels: int = 0
    pilot_valid_fraction: float | None = None
    pilot_cloud_fraction: float | None = None
    st_asset_available: bool
    qa_asset_available: bool
    st_asset_key: str | None = None
    qa_asset_key: str | None = None
    st_qa_asset_key: str | None = None
