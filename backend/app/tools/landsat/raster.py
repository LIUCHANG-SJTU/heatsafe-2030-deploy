from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.features import geometry_mask
from rasterio.mask import mask
from shapely.geometry import mapping, shape
from shapely.ops import transform


def transform_geometry(geometry: dict[str, Any], source_crs: str, target_crs: Any) -> dict[str, Any]:
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    return mapping(transform(transformer.transform, shape(geometry)))


def crop_remote_cog(
    href: str,
    geometry_wgs84: dict[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF",
    ):
        with rasterio.open(href) as source:
            projected_geometry = transform_geometry(
                geometry_wgs84, "EPSG:4326", source.crs
            )
            data, cropped_transform = mask(
                source,
                [projected_geometry],
                crop=True,
                filled=True,
                nodata=source.nodata,
                all_touched=False,
            )
            profile = source.profile.copy()
            profile.update(
                driver="GTiff",
                height=data.shape[1],
                width=data.shape[2],
                transform=cropped_transform,
                tiled=False,
                compress="deflate",
            )
            with rasterio.open(output_path, "w", **profile) as target:
                target.write(data)
            return {
                "source_crs": source.crs.to_string(),
                "source_resolution": [abs(source.transform.a), abs(source.transform.e)],
                "nodata": source.nodata,
                "shape": [data.shape[1], data.shape[2]],
            }


def geometry_pixel_mask(
    geometry_wgs84: dict[str, Any],
    raster_crs: Any,
    raster_transform: Any,
    out_shape: tuple[int, int],
    source_crs: str = "EPSG:4326",
) -> np.ndarray:
    projected = transform_geometry(geometry_wgs84, source_crs, raster_crs)
    return geometry_mask(
        [projected],
        out_shape=out_shape,
        transform=raster_transform,
        invert=True,
        all_touched=False,
    )


def read_cached_window(path: Path) -> tuple[np.ndarray, dict[str, Any]]:
    with rasterio.open(path) as source:
        values = source.read(1)
        metadata = {
            "crs": source.crs,
            "transform": source.transform,
            "nodata": source.nodata,
            "resolution": [abs(source.transform.a), abs(source.transform.e)],
        }
    return values, metadata
