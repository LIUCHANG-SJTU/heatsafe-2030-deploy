from __future__ import annotations

import numpy as np


def empirical_percentile(value: float, reference: np.ndarray) -> float:
    data = np.asarray(reference, dtype=float)
    data = data[np.isfinite(data)]
    if not data.size or not np.isfinite(value):
        raise ValueError("finite percentile value and reference are required")
    less = np.sum(data < value)
    equal = np.sum(data == value)
    return float((less + 0.5 * equal) / data.size)


def average_rank_01(values: np.ndarray) -> np.ndarray:
    data = np.asarray(values, dtype=float)
    result = np.full(data.shape, np.nan, dtype=float)
    valid_indices = np.flatnonzero(np.isfinite(data))
    valid = data[valid_indices]
    if not valid.size:
        return result
    if np.all(valid == valid[0]):
        result[valid_indices] = 0.5
        return result
    for index, value in zip(valid_indices, valid, strict=True):
        less = np.sum(valid < value)
        equal = np.sum(valid == value)
        average_zero_based_rank = less + (equal - 1) / 2
        result[index] = average_zero_based_rank / (valid.size - 1)
    return result
