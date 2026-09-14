from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ERA5ArtifactProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: str = "ERA5-Land hourly time-series data on single levels"
    provider: str = "Copernicus Climate Change Service / ECMWF"
    access_service: str = "Copernicus Climate Data Store"
    dataset_id: str
    requested_latitude: float
    requested_longitude: float
    returned_latitude: float
    returned_longitude: float
    spatial_selection_method: str
    variables: list[str]
    units: dict[str, str]
    date_range: str
    time_resolution: str = "hourly"
    response_container: str = "ZIP containing one NetCDF artifact"
    retrieved_at: datetime
    raw_artifact_path: str
    checksum: str
    license: str = "CC-BY"
    request_payload_redacted: dict
    request_hash: str = Field(min_length=64, max_length=64)
    data_mode: str = "REAL"
