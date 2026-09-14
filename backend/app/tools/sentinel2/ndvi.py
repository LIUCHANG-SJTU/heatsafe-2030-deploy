from __future__ import annotations

import numpy as np


NDVI_DENOMINATOR_EPSILON = 1e-12


def calculate_ndvi(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    red_values = np.asarray(red, dtype=float)
    nir_values = np.asarray(nir, dtype=float)
    if red_values.shape != nir_values.shape:
        raise ValueError("red and NIR arrays must have identical shapes")
    denominator = nir_values + red_values
    valid = (
        np.isfinite(red_values)
        & np.isfinite(nir_values)
        & (np.abs(denominator) > NDVI_DENOMINATOR_EPSILON)
    )
    result = np.full(red_values.shape, np.nan, dtype=float)
    result[valid] = (nir_values[valid] - red_values[valid]) / denominator[valid]
    return result

