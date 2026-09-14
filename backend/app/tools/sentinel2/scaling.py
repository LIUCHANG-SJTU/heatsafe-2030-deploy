from __future__ import annotations

import numpy as np


def dn_to_reflectance(
    values: np.ndarray,
    scale: float,
    offset: float,
    nodata: float | int | None,
) -> np.ndarray:
    raw = np.asarray(values, dtype=float)
    valid = np.isfinite(raw)
    if nodata is not None:
        valid &= raw != nodata
    reflectance = np.full(raw.shape, np.nan, dtype=float)
    reflectance[valid] = raw[valid] * scale + offset
    return reflectance

