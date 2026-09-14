from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ProvenanceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    source_url: HttpUrl
    retrieved_at: datetime
    time_range: str = Field(min_length=1)
    bbox: tuple[float, float, float, float]
    license: str = Field(min_length=1)
    checksum: str
    data_mode: str
    notes: str = ""

    @field_validator("bbox")
    @classmethod
    def ordered_bbox(
        cls, value: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        west, south, east, north = value
        if west >= east or south >= north:
            raise ValueError("bbox must be ordered [west, south, east, north]")
        return value

    @field_validator("checksum")
    @classmethod
    def sha256_checksum(cls, value: str) -> str:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
            raise ValueError("checksum must use sha256:<64 lowercase hex characters>")
        return value

    @field_validator("data_mode")
    @classmethod
    def supported_data_mode(cls, value: str) -> str:
        if value not in {"FIXTURE", "MIXED", "REAL"}:
            raise ValueError("data_mode must be FIXTURE, MIXED, or REAL")
        return value
