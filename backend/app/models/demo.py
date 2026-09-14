from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DemoGrid(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grid_id: str
    row: int = Field(ge=0)
    column: int = Field(ge=0)
    geometry: dict[str, Any]
    analysis_status: str
    analysis_reasons: list[str] = Field(default_factory=list)
    ranking_eligible: bool
    source_mode: str
    population_total: float = Field(ge=0)
    population_age_0_14: float = Field(ge=0)
    population_age_65_plus: float = Field(ge=0)
    elderly_share: float = Field(ge=0)
    child_share: float = Field(ge=0)
    vulnerability_share_raw: float = Field(ge=0)
    lst_median_c: float | None = None
    lst_valid_fraction: float = Field(ge=0, le=1)
    landsat_quality_flag: str
    ndvi_median_land: float | None = None
    green_fraction_land: float | None = Field(default=None, ge=0, le=1)
    green_fraction_grid_legacy: float | None = Field(default=None, ge=0, le=1)
    water_fraction_grid: float = Field(ge=0, le=1)
    sentinel_valid_fraction: float = Field(ge=0, le=1)
    sentinel_quality_flag: str
    spatial_heat_score: float | None = Field(default=None, ge=0, le=1)
    temporal_severity_score: float = Field(ge=0, le=1)
    hazard_score: float | None = Field(default=None, ge=0, le=1)
    exposure_score: float | None = Field(default=None, ge=0, le=1)
    vulnerability_score: float | None = Field(default=None, ge=0, le=1)
    adaptive_capacity_score: float | None = Field(default=None, ge=0, le=1)
    risk_score: float | None = Field(default=None, ge=0, le=100)
    risk_percentile_within_aoi: float | None = Field(default=None, ge=0, le=1)
    hazard_contribution_points: float | None = None
    exposure_contribution_points: float | None = None
    vulnerability_contribution_points: float | None = None
    adaptive_deficit_contribution_points: float | None = None
    primary_driver: str | None = None
    temporal_context_id: str
    source_ids: list[str] = Field(default_factory=list)


class DemoFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = "Feature"
    id: str
    geometry: dict[str, Any]
    properties: dict[str, Any]


class DemoFeatureCollection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = "FeatureCollection"
    name: str
    features: list[DemoFeature]


class DemoSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    demo_id: str
    api_version: str
    demo_revision: str = "m4c1"
    qa_contract_version: str = "M4C1_CANONICAL_QA_V1"
    data_mode: str
    model_status: str
    risk_scope: str
    event: dict[str, Any]
    aoi: dict[str, Any]
    temporal_context: dict[str, Any]
    methods: dict[str, str]
    weights: dict[str, float]
    quality_summary: dict[str, Any]
    summary: dict[str, Any]


class DemoGridDetail(DemoGrid):
    methods: dict[str, str]
    quality: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    temporal_context: dict[str, Any] | None = None
