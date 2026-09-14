from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SentinelSceneProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: str = "Sentinel-2 Level-2A Surface Reflectance"
    dataset_provider: str = "ESA / Copernicus"
    access_service: str = "Microsoft Planetary Computer"
    collection: str
    scene_id: str
    platform: str
    acquisition_datetime: datetime
    b04_asset_key: str
    b08_asset_key: str
    scl_asset_key: str
    product_metadata_asset_key: str
    b04_scale: float
    b04_offset: float
    b08_scale: float
    b08_offset: float
    scaling_source: str
    source_crs: str
    b04_resolution: float
    b08_resolution: float
    scl_resolution: float
    analysis_crs: str
    analysis_resolution: float
    scl_resampling_method: Literal["nearest"] = "nearest"
    scene_quality_mask_policy: str
    vegetation_mask_policy: str
    water_scene_quality_policy: Literal["KEEP"] = "KEEP"
    water_ndvi_policy: Literal["EXCLUDE"] = "EXCLUDE"
    water_green_fraction_policy: Literal["NON_GREEN"] = "NON_GREEN"
    green_ndvi_threshold: float = 0.30
    retrieved_at: datetime
    raw_artifacts: dict[str, str]
    checksums: dict[str, str] = Field(min_length=4)
    data_mode: Literal["REAL"] = "REAL"

