from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HourlyThreshold(BaseModel):
    model_config = ConfigDict(extra="forbid")

    utc_hour: int = Field(ge=0, le=23)
    temperature_p90_c: float
    sample_count: int = Field(gt=0)
    quantile_method: Literal["linear"] = "linear"


class ERA5BaselineStatistics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_start: str
    baseline_end: str
    reference_utc_hour: int = Field(ge=0, le=23)
    expected_july_same_hour_samples: int = Field(ge=0)
    actual_july_same_hour_samples: int = Field(ge=0)
    missing_samples: int = Field(ge=0)
    historical_temperature_mean_c: float
    historical_temperature_median_c: float
    historical_temperature_p90_c: float
    historical_temperature_p95_c: float
    historical_temperature_std_c: float = Field(ge=0)
    quantile_method: Literal["linear"] = "linear"


class ERA5TemporalContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_mode: Literal["REAL"] = "REAL"
    source_id: str
    temporal_context_id: str
    dataset_id: str
    requested_latitude: float
    requested_longitude: float
    returned_latitude: float
    returned_longitude: float
    spatial_selection_method: str
    satellite_reference_time: datetime
    era5_reference_time: datetime
    time_offset_minutes: float = Field(ge=0)
    time_selection_method: Literal["NEAREST_HOUR"] = "NEAREST_HOUR"
    air_temperature_c: float
    dewpoint_temperature_c: float
    relative_humidity_percent: float = Field(ge=0, le=100.000001)
    historical_median_c: float
    historical_mean_c: float
    historical_p90_c: float
    historical_p95_c: float
    historical_std_c: float = Field(ge=0)
    baseline_sample_count: int = Field(gt=0)
    temperature_anomaly_c: float
    temperature_percentile: float = Field(ge=0, le=1)
    hot_hours_last_24h: int = Field(ge=0, le=24)
    hot_hours_last_72h: int = Field(ge=0, le=72)
    consecutive_hot_hours_at_reference: int = Field(ge=0, le=72)
    max_consecutive_hot_hours_last_72h: int = Field(ge=0, le=72)
    event_window_complete: bool
    temporal_intensity_score: float = Field(ge=0, le=1)
    temporal_persistence_score: float = Field(ge=0, le=1)
    temporal_severity_score: float = Field(ge=0, le=1)
    method: Literal["TEMPORAL_HEAT_CONTEXT_HEURISTIC"] = (
        "TEMPORAL_HEAT_CONTEXT_HEURISTIC"
    )

    @model_validator(mode="after")
    def complete_event_is_required(self) -> "ERA5TemporalContext":
        if not self.event_window_complete:
            raise ValueError("REAL temporal context requires a complete 72-hour window")
        return self
