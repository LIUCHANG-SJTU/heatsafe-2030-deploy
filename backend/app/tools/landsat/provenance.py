from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LandsatSceneProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: str = "Landsat Collection 2 Level-2"
    dataset_provider: str = "U.S. Geological Survey"
    access_service: str = "Microsoft Planetary Computer"
    collection: str
    scene_id: str
    product_id: str
    platform: str
    acquisition_datetime: datetime
    stac_item_url: str
    st_asset_key: str
    qa_asset_key: str
    st_qa_asset_key: str | None
    source_geometry: dict[str, Any]
    pilot_bbox: tuple[float, float, float, float]
    source_crs: str
    source_resolution: tuple[float, float]
    asset_gsd: float | None = None
    scale: float
    offset: float
    nodata: float | int | None
    qa_mask_policy: str
    water_mask_policy: Literal["KEEP"] = "KEEP"
    aggregation_method: str
    retrieved_at: datetime
    raw_artifacts: dict[str, str]
    checksums: dict[str, str]
    data_mode: Literal["REAL"] = "REAL"
