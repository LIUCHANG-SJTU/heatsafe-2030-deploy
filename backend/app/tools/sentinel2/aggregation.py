from __future__ import annotations

import numpy as np

from app.models.landsat import coverage_quality


GREEN_NDVI_THRESHOLD = 0.30


def aggregate_vegetation(
    ndvi: np.ndarray,
    *,
    inside_grid: np.ndarray,
    observation_valid: np.ndarray,
    valid_land: np.ndarray,
    threshold: float = GREEN_NDVI_THRESHOLD,
) -> dict[str, float | int | str | None]:
    values = np.asarray(ndvi, dtype=float)
    inside = np.asarray(inside_grid, dtype=bool)
    observed = inside & np.asarray(observation_valid, dtype=bool)
    land = observed & np.asarray(valid_land, dtype=bool) & np.isfinite(values)
    green = land & (values > threshold)
    total_count = int(inside.sum())
    observed_count = int(observed.sum())
    land_count = int(land.sum())
    green_count = int(green.sum())
    observation_fraction = observed_count / total_count if total_count else 0.0
    quality = coverage_quality(observation_fraction)
    land_values = values[land]
    result: dict[str, float | int | str | None] = {
        "ndvi_mean": None,
        "ndvi_median": None,
        "ndvi_p25": None,
        "ndvi_p75": None,
        "green_fraction_grid": (
            green_count / observed_count if observed_count else None
        ),
        "green_fraction_land": green_count / land_count if land_count else None,
        "green_pixel_count": green_count,
        "valid_land_pixel_count": land_count,
        "valid_observation_pixel_count": observed_count,
        "total_analysis_pixel_count": total_count,
        "valid_observation_fraction": observation_fraction,
        "valid_land_fraction": land_count / total_count if total_count else 0.0,
        "quality_flag": quality.value,
    }
    if land_count:
        result.update(
            ndvi_mean=float(np.mean(land_values)),
            ndvi_median=float(np.median(land_values)),
            ndvi_p25=float(np.percentile(land_values, 25)),
            ndvi_p75=float(np.percentile(land_values, 75)),
        )
    return result

