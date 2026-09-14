from __future__ import annotations

import numpy as np

from app.models.landsat import CoverageQuality, coverage_quality


def aggregate_temperature(
    temperatures_c: np.ndarray,
    inside_grid: np.ndarray,
    valid_mask: np.ndarray,
) -> dict[str, float | int | str | None]:
    inside = np.asarray(inside_grid, dtype=bool)
    valid = inside & np.asarray(valid_mask, dtype=bool)
    total_count = int(inside.sum())
    valid_count = int(valid.sum())
    fraction = valid_count / total_count if total_count else 0.0
    quality = coverage_quality(fraction)
    result: dict[str, float | int | str | None] = {
        "valid_pixel_count": valid_count,
        "total_pixel_count": total_count,
        "valid_pixel_fraction": fraction,
        "quality_flag": quality.value,
        "land_surface_temperature_c": None,
        "lst_mean_c": None,
        "lst_median_c": None,
        "lst_p90_c": None,
        "lst_min_c": None,
        "lst_max_c": None,
    }
    if quality == CoverageQuality.INSUFFICIENT:
        return result
    values = np.asarray(temperatures_c, dtype=float)[valid]
    result.update(
        land_surface_temperature_c=float(np.median(values)),
        lst_mean_c=float(np.mean(values)),
        lst_median_c=float(np.median(values)),
        lst_p90_c=float(np.percentile(values, 90)),
        lst_min_c=float(np.min(values)),
        lst_max_c=float(np.max(values)),
    )
    return result
