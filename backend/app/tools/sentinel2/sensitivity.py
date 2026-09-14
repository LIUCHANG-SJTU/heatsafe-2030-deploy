from __future__ import annotations

from typing import Iterable

import numpy as np

from .adaptive import percentile_rank
from .aggregation import GREEN_NDVI_THRESHOLD


def _spearman(left: np.ndarray, right: np.ndarray) -> float:
    left_rank = percentile_rank(left)
    right_rank = percentile_rank(right)
    valid = np.isfinite(left_rank) & np.isfinite(right_rank)
    if valid.sum() < 2:
        return 1.0 if np.allclose(left[valid], right[valid]) else 0.0
    left_valid = left_rank[valid]
    right_valid = right_rank[valid]
    if np.isclose(np.std(left_valid), 0) or np.isclose(np.std(right_valid), 0):
        return 1.0 if np.allclose(left_valid, right_valid) else 0.0
    return float(np.corrcoef(left_valid, right_valid)[0, 1])


def threshold_sensitivity(
    grid_ndvi_values: list[np.ndarray],
    *,
    thresholds: Iterable[float],
    top_n: int = 10,
    observation_counts: list[int] | None = None,
) -> dict:
    thresholds_list = list(thresholds)
    if GREEN_NDVI_THRESHOLD not in thresholds_list:
        raise ValueError("thresholds must include the formal 0.30 threshold")
    denominators = observation_counts or [len(values) for values in grid_ndvi_values]
    fractions: dict[float, np.ndarray] = {}
    for threshold in thresholds_list:
        fractions[threshold] = np.array(
            [
                float(np.sum(np.asarray(values) > threshold)) / denominator
                if denominator
                else np.nan
                for values, denominator in zip(
                    grid_ndvi_values, denominators, strict=True
                )
            ],
            dtype=float,
        )
    formal = fractions[GREEN_NDVI_THRESHOLD]
    count = min(top_n, len(grid_ndvi_values))
    formal_top = set(np.argsort(np.nan_to_num(formal, nan=-1))[-count:])
    comparisons = {}
    for threshold in thresholds_list:
        values = fractions[threshold]
        threshold_top = set(np.argsort(np.nan_to_num(values, nan=-1))[-count:])
        comparisons[f"{threshold:.2f}"] = {
            "spearman_correlation": round(_spearman(formal, values), 6),
            "top_n_overlap": (
                round(len(formal_top & threshold_top) / count, 6) if count else 1.0
            ),
            "green_fraction_grid": values.tolist(),
        }
    return {
        "formal_threshold": GREEN_NDVI_THRESHOLD,
        "top_n": count,
        "comparisons": comparisons,
    }

