from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class DataAdapterError(RuntimeError):
    """Raised when acquisition fails without creating a valid raw artifact."""


class AdapterMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: str
    dataset_id: str
    provider: str
    source_url: HttpUrl
    purpose: str
    license_notes: str
    acquisition_notes: str


class AcquisitionRequest(BaseModel):
    bbox: tuple[float, float, float, float]
    start_date: date
    end_date: date
    raw_cache: Path

    @model_validator(mode="after")
    def validate_request(self) -> "AcquisitionRequest":
        west, south, east, north = self.bbox
        if west >= east or south >= north:
            raise ValueError("bbox must be ordered [west, south, east, north]")
        if self.start_date > self.end_date:
            raise ValueError("start_date cannot be after end_date")
        return self


class AcquisitionResult(BaseModel):
    files: list[Path] = Field(min_length=1)
    sidecars: list[Path] = Field(min_length=1)


class DataAdapter(ABC):
    metadata: AdapterMetadata

    @abstractmethod
    def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
        """Acquire a bounded subset and write raw files plus provenance sidecars."""

    def not_implemented(self) -> None:
        raise DataAdapterError(
            f"{self.metadata.dataset} acquisition is intentionally disabled in M0. "
            "Validate dataset terms and implement a bounded request before use."
        )

