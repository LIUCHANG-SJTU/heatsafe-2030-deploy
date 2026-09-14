from __future__ import annotations

import numpy as np


def spatiotemporal_hazard(
    spatial_heat: np.ndarray,
    temporal_severity: float,
    spatial_weight: float = 0.7,
) -> np.ndarray:
    spatial = np.asarray(spatial_heat, dtype=float)
    if not 0 <= temporal_severity <= 1 or not 0 < spatial_weight <= 1:
        raise ValueError("hazard inputs and weight must be within [0,1]")
    return spatial_weight * spatial + (1 - spatial_weight) * temporal_severity
