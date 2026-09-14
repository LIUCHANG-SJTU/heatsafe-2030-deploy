from __future__ import annotations

import numpy as np


def percentile_rank(values: np.ndarray) -> np.ndarray:
    data = np.asarray(values, dtype=float)
    result = np.full(data.shape, np.nan, dtype=float)
    valid_indices = np.flatnonzero(np.isfinite(data))
    if not valid_indices.size:
        return result
    valid = data[valid_indices]
    if valid.size == 1:
        result[valid_indices] = 0.5
        return result
    # Upper empirical rank gives all tied maxima 1.0 and preserves equal scores
    # for ties. This is more interpretable for bounded coverage fractions than
    # average-position ranking, which can leave a large tied maximum below 1.
    ranks = np.array(
        [(np.sum(valid <= value) - 1) / (valid.size - 1) for value in valid],
        dtype=float,
    )
    result[valid_indices] = ranks
    return result
