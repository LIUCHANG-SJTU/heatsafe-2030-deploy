from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorldPopApiProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: str
    provider: str = "WorldPop"
    source_type: str = "api"
    api_url: str
    endpoint: str
    year: int
    resolution: str
    data_source: str
    license: str = "CC BY 4.0"
    grid_id: str
    geometry_wgs84: dict[str, Any]
    task_id: str
    request_hash: str
    submitted_at: datetime | None
    retrieved_at: datetime
    raw_response_path: str
    checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    data_mode: str = "REAL"
    provenance_note: str = (
        "API provenance only; no asserted mapping to Hub id 80688, R2025A v1, "
        "or DOI 10.5258/SOTON/WP00841."
    )


def file_checksum(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"

