from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.grid.pilot import PilotGrid

from .models import WorldPopArtifact


WORLDPOP_POPULATION_DOI = "10.5258/SOTON/WP00839"
WORLDPOP_AGESEX_DOI = "10.5258/SOTON/WP00841"
WORLDPOP_POPULATION_URL = (
    "https://data.worldpop.org/GIS/Population/Global_2015_2030/"
    "R2025A/2026/CHN/v1/100m/constrained/"
    "chn_pop_2026_CN_100m_R2025A_v1.tif"
)
WORLDPOP_AGESEX_BASE_URL = (
    "https://data.worldpop.org/GIS/AgeSex_structures/Global_2015_2030/"
    "R2025A/2026/CHN/v1/100m/constrained"
)
WORLDPOP_REQUIRED_AGE_CODES = (
    "00",
    "01",
    "05",
    "10",
    "65",
    "70",
    "75",
    "80",
    "85",
    "90",
)
WORLDPOP_AGESEX_URLS = {
    code: (
        f"{WORLDPOP_AGESEX_BASE_URL}/"
        f"chn_t_{code}_2026_CN_100m_R2025A_v1.tif"
    )
    for code in WORLDPOP_REQUIRED_AGE_CODES
}

_CONTENT_RANGE = re.compile(r"^bytes 0-(\d+)/(\d+|\*)$")


class RasterWindowProbeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    status: str
    reason: str
    head_status_code: int
    range_status_code: int
    content_length: int | None
    accept_ranges: str | None
    etag: str | None
    last_modified: str | None
    requested_range: str
    content_range: str | None
    range_content_length: int | None
    bytes_read: int = Field(ge=0)


def _integer_header(headers: Mapping[str, str], name: str) -> int | None:
    value = headers.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def assess_range_response(
    *, status_code: int, headers: Mapping[str, str], requested_bytes: int
) -> tuple[bool, str]:
    """Accept only a bounded byte-range response, never a full-file fallback."""

    if status_code != 206:
        return False, "RANGE_REQUEST_NOT_HONORED"

    content_range = headers.get("content-range", "")
    match = _CONTENT_RANGE.fullmatch(content_range)
    if match is None or int(match.group(1)) != requested_bytes - 1:
        return False, "INVALID_CONTENT_RANGE"

    content_length = _integer_header(headers, "content-length")
    if content_length is None or content_length > requested_bytes:
        return False, "UNBOUNDED_RANGE_RESPONSE"
    return True, "RANGE_WINDOW_SUPPORTED"


class WorldPopRasterBackend:
    """Guarded R2025A raster backend.

    M4C may proceed only after an upstream GeoTIFF proves that it honors bounded
    HTTP range requests. A server response that silently falls back to the full
    national raster is rejected before its body is consumed.
    """

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 45.0,
    ) -> None:
        self._client = client
        self.timeout_seconds = timeout_seconds

    def probe_remote_window(
        self, url: str, *, requested_bytes: int = 65_536
    ) -> RasterWindowProbeResult:
        if requested_bytes <= 0:
            raise ValueError("requested_bytes must be positive")

        owns_client = self._client is None
        client = self._client or httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
        )
        requested_range = f"bytes=0-{requested_bytes - 1}"
        try:
            head = client.head(url, headers={"Accept-Encoding": "identity"})
            head.raise_for_status()
            with client.stream(
                "GET",
                url,
                headers={
                    "Accept-Encoding": "identity",
                    "Range": requested_range,
                },
            ) as response:
                allowed, reason = assess_range_response(
                    status_code=response.status_code,
                    headers=response.headers,
                    requested_bytes=requested_bytes,
                )
                bytes_read = 0
                if allowed:
                    for chunk in response.iter_bytes():
                        bytes_read += len(chunk)
                        if bytes_read > requested_bytes:
                            allowed = False
                            reason = "RANGE_BODY_EXCEEDED_LIMIT"
                            break
                    if allowed and bytes_read == 0:
                        allowed = False
                        reason = "EMPTY_RANGE_RESPONSE"

                return RasterWindowProbeResult(
                    url=url,
                    status="PASS" if allowed else "FAIL",
                    reason=reason,
                    head_status_code=head.status_code,
                    range_status_code=response.status_code,
                    content_length=_integer_header(head.headers, "content-length"),
                    accept_ranges=head.headers.get("accept-ranges"),
                    etag=head.headers.get("etag"),
                    last_modified=head.headers.get("last-modified"),
                    requested_range=requested_range,
                    content_range=response.headers.get("content-range"),
                    range_content_length=_integer_header(
                        response.headers, "content-length"
                    ),
                    bytes_read=bytes_read,
                )
        finally:
            if owns_client:
                client.close()

    def acquire(self, grid: PilotGrid, raw_cache: Path) -> WorldPopArtifact:
        raise NotImplementedError(
            "WorldPop raster acquisition requires a passing M4C remote-window probe"
        )
