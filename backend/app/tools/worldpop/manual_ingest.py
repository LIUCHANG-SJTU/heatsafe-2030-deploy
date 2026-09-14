from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.errors import RasterioIOError
from rasterio.windows import Window, from_bounds

from .raster_backend import (
    WORLDPOP_AGESEX_BASE_URL,
    WORLDPOP_AGESEX_DOI,
    WORLDPOP_POPULATION_DOI,
    WORLDPOP_POPULATION_URL,
)


WORLDPOP_TOTAL_SUMMARY_URL = "https://hub.worldpop.org/geodata/summary?id=72928"
WORLDPOP_AGESEX_SUMMARY_URL = "https://hub.worldpop.org/geodata/summary?id=80688"
WORLDPOP_MANUAL_DIRECTORY = Path("data/manual/worldpop/m4c")
WORLDPOP_EXPECTED_RESOLUTION_DEGREES = 1 / 1200
MAX_AOI_TEST_WINDOW_PIXELS = 20_000


class ManualRasterSpec(NamedTuple):
    purpose: str
    age_code: str | None
    age_semantics: str
    filename: str
    official_page: str
    official_url: str
    approximate_size_mb: float
    doi: str


def _age_spec(code: str, semantics: str, size_mb: float) -> ManualRasterSpec:
    filename = f"chn_t_{code}_2026_CN_100m_R2025A_v1.tif"
    return ManualRasterSpec(
        purpose="AGE_0_14" if code in {"00", "01", "05", "10"} else "AGE_65_PLUS",
        age_code=code,
        age_semantics=semantics,
        filename=filename,
        official_page=WORLDPOP_AGESEX_SUMMARY_URL,
        official_url=f"{WORLDPOP_AGESEX_BASE_URL}/{filename}",
        approximate_size_mb=size_mb,
        doi=WORLDPOP_AGESEX_DOI,
    )


WORLDPOP_MANUAL_RASTER_SPECS = (
    ManualRasterSpec(
        purpose="TOTAL_POPULATION",
        age_code=None,
        age_semantics="all ages, both sexes",
        filename="chn_pop_2026_CN_100m_R2025A_v1.tif",
        official_page=WORLDPOP_TOTAL_SUMMARY_URL,
        official_url=WORLDPOP_POPULATION_URL,
        approximate_size_mb=878.14,
        doi=WORLDPOP_POPULATION_DOI,
    ),
    _age_spec("00", "0 to 12 months, both sexes", 871.17),
    _age_spec("01", "1 to 4 years, both sexes", 875.76),
    _age_spec("05", "5 to 9 years, both sexes", 876.59),
    _age_spec("10", "10 to 14 years, both sexes", 876.80),
    _age_spec("65", "65 to 69 years, both sexes", 876.65),
    _age_spec("70", "70 to 74 years, both sexes", 876.65),
    _age_spec("75", "75 to 79 years, both sexes", 876.26),
    _age_spec("80", "80 to 84 years, both sexes", 875.42),
    _age_spec("85", "85 to 89 years, both sexes", 872.91),
    _age_spec("90", "90 years and over, both sexes", 867.94),
)


def sha256_stream(path: Path, *, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_aoi_window(source: rasterio.DatasetReader, bbox: tuple[float, ...]) -> Window:
    raw = from_bounds(*bbox, transform=source.transform)
    window = raw.round_offsets().round_lengths()
    window = window.intersection(Window(0, 0, source.width, source.height))
    if window.width <= 0 or window.height <= 0:
        raise ValueError("AOI does not intersect raster")
    if window.width * window.height > MAX_AOI_TEST_WINDOW_PIXELS:
        raise ValueError("AOI test window exceeds safety pixel limit")
    return window


def _validate_geotiff(path: Path, bbox_wgs84: tuple[float, ...]) -> dict[str, Any]:
    with rasterio.open(path) as source:
        crs_is_wgs84 = bool(source.crs == CRS.from_epsg(4326))
        resolution_valid = bool(
            abs(abs(source.transform.a) - WORLDPOP_EXPECTED_RESOLUTION_DEGREES)
            <= 1e-10
            and abs(abs(source.transform.e) - WORLDPOP_EXPECTED_RESOLUTION_DEGREES)
            <= 1e-10
        )
        north_up = bool(
            source.transform.a > 0
            and source.transform.e < 0
            and abs(source.transform.b) <= 1e-12
            and abs(source.transform.d) <= 1e-12
        )
        west, south, east, north = source.bounds
        aoi_covered = bool(
            crs_is_wgs84
            and west <= bbox_wgs84[0]
            and south <= bbox_wgs84[1]
            and east >= bbox_wgs84[2]
            and north >= bbox_wgs84[3]
        )
        dtype = np.dtype(source.dtypes[0]) if source.count else None
        dtype_valid = bool(dtype is not None and np.issubdtype(dtype, np.number))
        nodata_valid = bool(source.nodata is not None and np.isfinite(source.nodata))

        sample_shape = None
        sample_valid_pixels = None
        sample_read = False
        if crs_is_wgs84 and resolution_valid and aoi_covered:
            window = _safe_aoi_window(source, bbox_wgs84)
            sample = source.read(1, window=window, masked=True)
            sample_shape = list(sample.shape)
            sample_valid_pixels = int(np.ma.count(sample))
            sample_read = True

        checks = {
            "driver_geotiff": source.driver == "GTiff",
            "single_band": source.count == 1,
            "crs_wgs84": crs_is_wgs84,
            "resolution_3_arc_second": resolution_valid,
            "north_up": north_up,
            "dimensions_positive": source.width > 0 and source.height > 0,
            "numeric_dtype": dtype_valid,
            "nodata_defined": nodata_valid,
            "aoi_covered": aoi_covered,
            "aoi_test_window_readable": sample_read,
        }
        return {
            "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks,
            "driver": source.driver,
            "crs": source.crs.to_string() if source.crs else None,
            "resolution": [abs(source.transform.a), abs(source.transform.e)],
            "width": source.width,
            "height": source.height,
            "bounds": list(source.bounds),
            "band_count": source.count,
            "dtype": source.dtypes[0] if source.count else None,
            "nodata": source.nodata,
            "compression": source.profile.get("compress"),
            "aoi_test_window_shape": sample_shape,
            "aoi_test_window_valid_pixels": sample_valid_pixels,
        }


def validate_manual_worldpop_files(
    manual_directory: Path,
    bbox_wgs84: tuple[float, float, float, float],
) -> dict[str, Any]:
    results = []
    for spec in WORLDPOP_MANUAL_RASTER_SPECS:
        path = manual_directory / spec.filename
        result: dict[str, Any] = {
            "purpose": spec.purpose,
            "age_code": spec.age_code,
            "age_semantics": spec.age_semantics,
            "filename": spec.filename,
            "manual_source_path": str(path),
            "official_page": spec.official_page,
            "doi": spec.doi,
            "exists": path.exists(),
            "regular_file": path.is_file() and not path.is_symlink(),
            "file_size": path.stat().st_size if path.is_file() else None,
            "sha256": None,
            "geotiff": None,
            "status": "MISSING",
        }
        if result["regular_file"] and result["file_size"] > 0:
            try:
                result["geotiff"] = _validate_geotiff(path, bbox_wgs84)
                result["sha256"] = sha256_stream(path)
                result["status"] = result["geotiff"]["status"]
            except (RasterioIOError, OSError, ValueError) as error:
                result["status"] = "INVALID"
                result["error"] = str(error)
        elif result["exists"]:
            result["status"] = "INVALID"
        results.append(result)

    present = [item for item in results if item["exists"]]
    valid = [item for item in results if item["status"] == "PASS"]
    missing = [item["filename"] for item in results if item["status"] == "MISSING"]
    invalid = [item["filename"] for item in results if item["status"] == "INVALID"]
    ready = len(valid) == len(WORLDPOP_MANUAL_RASTER_SPECS)
    return {
        "m4c_status": (
            "READY_FOR_LOCAL_RASTER_PROCESSING"
            if ready
            else "WAITING_FOR_MANUAL_WORLDPOP_FILES"
        ),
        "manual_worldpop_ingest": "PASS" if ready else "WAITING",
        "manual_download_strategy": "PASS",
        "worldpop_backend": "LOCAL_MANUAL_RASTER" if ready else "NOT_READY",
        "manual_directory": str(manual_directory),
        "required_file_count": len(WORLDPOP_MANUAL_RASTER_SPECS),
        "present_file_count": len(present),
        "valid_file_count": len(valid),
        "missing_files": missing,
        "invalid_files": invalid,
        "network_downloads": 0,
        "ready_for_local_raster_processing": ready,
        "files": results,
    }
