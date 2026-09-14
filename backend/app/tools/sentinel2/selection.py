from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.landsat import CoverageQuality, coverage_quality


class SentinelCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    platform: str
    acquisition_datetime: datetime
    scene_cloud_cover: float
    pilot_observation_total_pixels: int = 0
    pilot_observation_valid_pixels: int = 0
    pilot_observation_valid_fraction: float = Field(ge=0, le=1)
    b04_available: bool
    b08_available: bool
    scl_available: bool
    b04_asset_key: str | None = None
    b08_asset_key: str | None = None
    scl_asset_key: str | None = None
    days_from_landsat_scene: float = Field(ge=0)

    @property
    def quality(self) -> CoverageQuality:
        return coverage_quality(self.pilot_observation_valid_fraction)


class SearchDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window: Literal["INITIAL", "EXPANDED", "COMPOSITE"]
    selected_scene: SentinelCandidate | None
    composite_required: bool
    candidates: list[SentinelCandidate]


def select_best_scene(candidates: list[SentinelCandidate]) -> SentinelCandidate:
    eligible = [
        candidate
        for candidate in candidates
        if candidate.b04_available
        and candidate.b08_available
        and candidate.scl_available
    ]
    if not eligible:
        raise ValueError("no candidate has B04, B08, and SCL")
    return max(
        eligible,
        key=lambda candidate: (
            candidate.quality == CoverageQuality.HIGH,
            candidate.pilot_observation_valid_fraction,
            -candidate.days_from_landsat_scene,
            -candidate.scene_cloud_cover,
        ),
    )


def choose_search_result(
    initial: list[SentinelCandidate],
    expanded: list[SentinelCandidate],
) -> SearchDecision:
    initial_high = [item for item in initial if item.quality == CoverageQuality.HIGH]
    if initial_high:
        return SearchDecision(
            window="INITIAL",
            selected_scene=select_best_scene(initial_high),
            composite_required=False,
            candidates=initial,
        )
    expanded_high = [item for item in expanded if item.quality == CoverageQuality.HIGH]
    if expanded_high:
        return SearchDecision(
            window="EXPANDED",
            selected_scene=select_best_scene(expanded_high),
            composite_required=False,
            candidates=expanded,
        )
    return SearchDecision(
        window="COMPOSITE",
        selected_scene=None,
        composite_required=True,
        candidates=expanded,
    )

