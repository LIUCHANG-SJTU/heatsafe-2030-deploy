from __future__ import annotations

from typing import Any

import numpy as np
from rasterio.enums import Resampling
from rasterio.warp import reproject


def align_array(
    source: np.ndarray,
    *,
    source_transform: Any,
    source_crs: Any,
    target_shape: tuple[int, int],
    target_transform: Any,
    target_crs: Any,
    resampling: Resampling,
    source_nodata: float | int | None,
    target_nodata: float | int,
    destination_dtype: np.dtype | type | None = None,
) -> np.ndarray:
    if resampling not in {Resampling.nearest, Resampling.bilinear}:
        raise ValueError("M3A alignment permits nearest or bilinear only")
    destination = np.full(
        target_shape,
        target_nodata,
        dtype=destination_dtype or source.dtype,
    )
    reproject(
        source=source,
        destination=destination,
        src_transform=source_transform,
        src_crs=source_crs,
        src_nodata=source_nodata,
        dst_transform=target_transform,
        dst_crs=target_crs,
        dst_nodata=target_nodata,
        resampling=resampling,
    )
    return destination
