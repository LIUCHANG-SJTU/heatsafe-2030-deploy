from __future__ import annotations

import numpy as np


OFFICIAL_SCALE = 0.00341802
OFFICIAL_OFFSET_K = 149.0
KELVIN_TO_CELSIUS = 273.15


def scale_surface_temperature(
    dn: np.ndarray,
    scale: float = OFFICIAL_SCALE,
    offset: float = OFFICIAL_OFFSET_K,
) -> np.ndarray:
    """Scale Landsat C2 L2 ST digital numbers to Celsius."""
    values = np.asarray(dn, dtype=float)
    return values * scale + offset - KELVIN_TO_CELSIUS


def valid_temperature_mask(
    dn: np.ndarray,
    qa_valid: np.ndarray,
    nodata: float | int | None,
) -> np.ndarray:
    values = np.asarray(dn)
    valid = np.asarray(qa_valid, dtype=bool) & np.isfinite(values)
    if nodata is not None:
        valid &= values != nodata
    return valid

