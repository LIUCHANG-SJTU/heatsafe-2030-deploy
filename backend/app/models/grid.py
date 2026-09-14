from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .landsat import LandsatGridTemperature
from .hazard import SpatiotemporalHazardGrid
from .sentinel2 import AdaptiveCapacityProxy, SentinelGridVegetation


class DataMode(StrEnum):
    FIXTURE = "FIXTURE"
    MIXED = "MIXED"
    REAL = "REAL"


class ModelStatus(StrEnum):
    PRELIMINARY_HEURISTIC = "PRELIMINARY_HEURISTIC"


class ComponentModes(BaseModel):
    hazard: DataMode = DataMode.FIXTURE
    exposure: DataMode = DataMode.FIXTURE
    vulnerability: DataMode = DataMode.FIXTURE
    adaptive_capacity: DataMode = DataMode.FIXTURE
    risk: DataMode = DataMode.FIXTURE
    population: DataMode = DataMode.FIXTURE
    spatial_heat: DataMode = DataMode.FIXTURE
    vegetation: DataMode = DataMode.FIXTURE
    temporal_heat: DataMode = DataMode.FIXTURE


SOURCE_MODE_FIELDS = (
    "population",
    "vulnerability",
    "spatial_heat",
    "vegetation",
    "temporal_heat",
)


def derive_data_mode(
    modes: ComponentModes | Mapping[str, DataMode | str | None],
) -> DataMode:
    if isinstance(modes, ComponentModes):
        values = modes.model_dump()
    else:
        values = dict(modes)
    if any(field not in values or values[field] is None for field in SOURCE_MODE_FIELDS):
        return DataMode.MIXED
    required = tuple(DataMode(values[field]) for field in SOURCE_MODE_FIELDS)
    if all(mode == DataMode.REAL for mode in required):
        return DataMode.REAL
    if all(mode == DataMode.FIXTURE for mode in required):
        return DataMode.FIXTURE
    return DataMode.MIXED


class RawGridCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grid_id: str
    geometry: dict[str, Any]
    lat: float
    lon: float
    population_total: float = Field(ge=0)
    population_age_0_14: float = Field(ge=0)
    population_age_65_plus: float = Field(ge=0)
    land_surface_temperature: float
    temperature_percentile: float = Field(ge=0, le=1)
    heat_exceedance_hours: float = Field(ge=0)
    ndvi: float = Field(ge=-1, le=1)
    data_timestamp: datetime
    data_source_ids: list[str] = Field(min_length=1)
    data_mode: DataMode
    component_modes: ComponentModes = Field(default_factory=ComponentModes)
    component_source_ids: dict[str, list[str]] = Field(default_factory=dict)
    surface_temperature: LandsatGridTemperature | None = None
    vegetation: SentinelGridVegetation | None = None
    adaptive_capacity: AdaptiveCapacityProxy | None = None
    population_composition_status: str | None = None
    temporal_context_id: str | None = None
    spatiotemporal_hazard: SpatiotemporalHazardGrid | None = None

    @field_validator("geometry")
    @classmethod
    def polygon_geometry_required(cls, value: dict[str, Any]) -> dict[str, Any]:
        if value.get("type") != "Polygon" or not value.get("coordinates"):
            raise ValueError("geometry must be a non-empty GeoJSON Polygon")
        return value

    @field_validator("population_age_0_14", "population_age_65_plus")
    @classmethod
    def age_population_is_nonnegative(cls, value: float) -> float:
        return value

    @model_validator(mode="after")
    def age_subsets_do_not_exceed_total(self) -> "RawGridCell":
        if self.population_age_0_14 > self.population_total + 1e-6:
            raise ValueError("population_age_0_14 cannot exceed population_total")
        if self.population_age_65_plus > self.population_total + 1e-6:
            raise ValueError("population_age_65_plus cannot exceed population_total")
        if (
            self.population_age_0_14 + self.population_age_65_plus
            > self.population_total + 1e-6
        ):
            raise ValueError("child and elderly populations cannot exceed total")
        return self


class GridCell(RawGridCell):
    hazard_score: float = Field(ge=0, le=1)
    exposure_score: float = Field(ge=0, le=1)
    vulnerability_score: float = Field(ge=0, le=1)
    adaptive_capacity_score: float = Field(ge=0, le=1)
    risk_score: float = Field(ge=0, le=100)


class GridCollection(BaseModel):
    data_mode: DataMode
    model_status: ModelStatus = ModelStatus.PRELIMINARY_HEURISTIC
    grid_size_meters: int = 250
    cells: list[GridCell]
