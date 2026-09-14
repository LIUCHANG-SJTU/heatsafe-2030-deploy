from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from shapely.geometry import shape

from app.grid import PilotGrid
from app.tools.landsat.raster import crop_remote_cog, read_cached_window

from .alignment import align_array


@dataclass(frozen=True)
class AnalysisRasterGrid:
    crs: str
    transform: Affine
    shape: tuple[int, int]
    resolution_meters: int
    bounds: tuple[float, float, float, float]


def build_analysis_raster(pilot: PilotGrid, resolution_meters: int = 10) -> AnalysisRasterGrid:
    polygons = [shape(cell.geometry_projected) for cell in pilot.cells]
    west = min(polygon.bounds[0] for polygon in polygons)
    south = min(polygon.bounds[1] for polygon in polygons)
    east = max(polygon.bounds[2] for polygon in polygons)
    north = max(polygon.bounds[3] for polygon in polygons)
    width_m = east - west
    height_m = north - south
    width = round(width_m / resolution_meters)
    height = round(height_m / resolution_meters)
    if not np.isclose(width_m, width * resolution_meters) or not np.isclose(
        height_m, height * resolution_meters
    ):
        raise ValueError("pilot bounds do not align to requested analysis resolution")
    return AnalysisRasterGrid(
        crs=pilot.projected_crs,
        transform=from_origin(west, north, resolution_meters, resolution_meters),
        shape=(height, width),
        resolution_meters=resolution_meters,
        bounds=(west, south, east, north),
    )


def ensure_remote_window(
    href: str,
    geometry_wgs84: dict[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    return crop_remote_cog(href, geometry_wgs84, output_path)


def align_cached_window(
    path: Path,
    target: AnalysisRasterGrid,
    *,
    resampling: Resampling,
    target_nodata: float | int,
    destination_dtype: np.dtype | type | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    values, metadata = read_cached_window(path)
    aligned = align_array(
        values,
        source_transform=metadata["transform"],
        source_crs=metadata["crs"],
        target_shape=target.shape,
        target_transform=target.transform,
        target_crs=target.crs,
        resampling=resampling,
        source_nodata=metadata["nodata"],
        target_nodata=target_nodata,
        destination_dtype=destination_dtype,
    )
    return aligned, metadata

