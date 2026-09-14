from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from app.models.landsat import CoverageQuality
from app.tools.era5.percentile import average_rank_01


ACCEPTABLE_QUALITY = {CoverageQuality.HIGH.value, CoverageQuality.MEDIUM.value}


class LandsatCandidateMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    acquisition_time: datetime
    scene_coverage_fraction: float = Field(ge=0, le=1)
    valid_fraction: float = Field(ge=0, le=1)
    high_quality_cell_count: int = Field(ge=0)
    medium_quality_cell_count: int = Field(ge=0)
    low_quality_cell_count: int = Field(ge=0)
    insufficient_cell_count: int = Field(ge=0)
    lst_candidate_median_c: float | None
    lst_p10_c: float | None
    lst_p25_c: float | None
    lst_p50_c: float | None
    lst_p75_c: float | None
    lst_p90_c: float | None
    lst_iqr_c: float | None
    lst_p90_p10_spread_c: float | None
    eligible: bool
    rejection_reasons: list[str]


class SentinelCandidateMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selection_method: Literal[
        "SINGLE_SCENE",
        "SAME_DATE_TILE_MOSAIC",
        "EXTENDED_WINDOW_SINGLE_SCENE",
        "EXTENDED_WINDOW_TILE_MOSAIC",
        "QA_MEDIAN_COMPOSITE",
    ]
    scene_ids: list[str] = Field(min_length=1)
    acquisition_times: list[datetime] = Field(min_length=1)
    minimum_time_difference_days: float = Field(ge=0)
    maximum_time_difference_days: float = Field(ge=0)
    valid_fraction: float = Field(ge=0, le=1)
    water_fraction: float = Field(ge=0, le=1)
    ndvi_p10: float | None
    ndvi_p50: float | None
    ndvi_p90: float | None
    ndvi_p90_p10_spread: float | None
    green_p10: float | None
    green_p50: float | None
    green_p90: float | None
    green_p90_p10_spread: float | None
    green_saturation_fraction: float | None = Field(default=None, ge=0, le=1)
    eligible: bool
    rejection_reasons: list[str]


class SatelliteScreeningResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    phase: Literal["BASE", "REFINED"]
    source_candidate_ids: list[str]
    centroid_lon: float
    centroid_lat: float
    bbox_wgs84: tuple[float, float, float, float]
    bounds_projected: tuple[float, float, float, float]
    landsat: LandsatCandidateMetrics
    sentinel: SentinelCandidateMetrics
    satellite_eligible: bool
    rejection_reasons: list[str]
    lst_spread_rank: float | None = Field(default=None, ge=0, le=1)
    green_spread_rank: float | None = Field(default=None, ge=0, le=1)
    ndvi_spread_rank: float | None = Field(default=None, ge=0, le=1)
    non_saturation_rank: float | None = Field(default=None, ge=0, le=1)
    satellite_balance_score: float | None = Field(default=None, ge=0, le=1)


def candidate_valid_fraction(quality_flags: list[str]) -> float:
    if not quality_flags:
        raise ValueError("quality flags are required")
    return sum(flag in ACCEPTABLE_QUALITY for flag in quality_flags) / len(
        quality_flags
    )


def finite_quantiles(values: list[float | None]) -> dict[str, float | None]:
    data = np.asarray([value for value in values if value is not None], dtype=float)
    data = data[np.isfinite(data)]
    if not data.size:
        return {key: None for key in ("p10", "p25", "p50", "p75", "p90")}
    return {
        f"p{quantile}": float(np.percentile(data, quantile))
        for quantile in (10, 25, 50, 75, 90)
    }


def green_saturation_fraction(values: list[float | None]) -> float | None:
    data = np.asarray([value for value in values if value is not None], dtype=float)
    data = data[np.isfinite(data)]
    if not data.size:
        return None
    return float(np.mean((data <= 0.05) | (data >= 0.95)))


def _metric_ranks(values: list[float]) -> np.ndarray:
    return average_rank_01(np.asarray(values, dtype=float))


def rank_satellite_candidates(
    candidates: list[SatelliteScreeningResult],
) -> list[SatelliteScreeningResult]:
    eligible = [candidate for candidate in candidates if candidate.satellite_eligible]
    if not eligible:
        return candidates
    metrics = (
        [candidate.landsat.lst_p90_p10_spread_c for candidate in eligible],
        [candidate.sentinel.green_p90_p10_spread for candidate in eligible],
        [candidate.sentinel.ndvi_p90_p10_spread for candidate in eligible],
        [
            None
            if candidate.sentinel.green_saturation_fraction is None
            else 1 - candidate.sentinel.green_saturation_fraction
            for candidate in eligible
        ],
    )
    if any(any(value is None for value in metric) for metric in metrics):
        raise ValueError("eligible candidates require finite satellite metrics")
    rank_arrays = [_metric_ranks([float(value) for value in metric]) for metric in metrics]
    updates: dict[str, SatelliteScreeningResult] = {}
    for index, candidate in enumerate(eligible):
        ranks = [float(values[index]) for values in rank_arrays]
        updates[candidate.candidate_id] = candidate.model_copy(
            update={
                "lst_spread_rank": ranks[0],
                "green_spread_rank": ranks[1],
                "ndvi_spread_rank": ranks[2],
                "non_saturation_rank": ranks[3],
                "satellite_balance_score": min(ranks),
            }
        )
    return [updates.get(candidate.candidate_id, candidate) for candidate in candidates]


def select_top_base_for_refinement(
    candidates: list[SatelliteScreeningResult], count: int = 5
) -> list[SatelliteScreeningResult]:
    eligible = [candidate for candidate in candidates if candidate.satellite_eligible]
    return sorted(
        eligible,
        key=lambda candidate: (
            -float(candidate.satellite_balance_score),
            -candidate.landsat.valid_fraction,
            -candidate.sentinel.valid_fraction,
            candidate.sentinel.water_fraction,
            candidate.candidate_id,
        ),
    )[:count]


def select_satellite_top8(
    candidates: list[SatelliteScreeningResult], count: int = 8
) -> list[SatelliteScreeningResult]:
    eligible = [candidate for candidate in candidates if candidate.satellite_eligible]
    return sorted(
        eligible,
        key=lambda candidate: (
            -float(candidate.satellite_balance_score),
            -min(candidate.landsat.valid_fraction, candidate.sentinel.valid_fraction),
            candidate.sentinel.water_fraction,
            -float(candidate.landsat.lst_p90_p10_spread_c),
            candidate.candidate_id,
        ),
    )[:count]
