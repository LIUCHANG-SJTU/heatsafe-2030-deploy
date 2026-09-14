from __future__ import annotations

import numpy as np


def robust_normalize(
    values: list[float] | np.ndarray,
    lower_percentile: float = 5.0,
    upper_percentile: float = 95.0,
) -> np.ndarray:
    """Scale finite values to [0, 1] using percentile bounds.

    Missing values remain NaN. A constant finite vector maps to 0.5 because it
    contains no regional ranking information.
    """

    array = np.asarray(values, dtype=float)
    result = np.full(array.shape, np.nan, dtype=float)
    finite = np.isfinite(array)
    if not finite.any():
        return result

    lower, upper = np.nanpercentile(
        array[finite], [lower_percentile, upper_percentile]
    )
    if np.isclose(lower, upper):
        result[finite] = 0.5
        return result

    result[finite] = np.clip((array[finite] - lower) / (upper - lower), 0.0, 1.0)
    return result


def require_complete(*arrays: np.ndarray) -> np.ndarray:
    """Return a mask identifying rows where every required input is finite."""

    if not arrays:
        raise ValueError("at least one array is required")
    mask = np.ones(arrays[0].shape, dtype=bool)
    for array in arrays:
        if array.shape != arrays[0].shape:
            raise ValueError("all arrays must have the same shape")
        mask &= np.isfinite(array)
    return mask

