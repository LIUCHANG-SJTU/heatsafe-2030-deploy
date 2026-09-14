from __future__ import annotations

import numpy as np


# Sentinel-2 L2A Scene Classification Layer classes from the ESA/Copernicus
# product definition. Class 2/7 remain observable; downstream quality audits
# retain their prevalence instead of silently relabeling them.
SCL_CLASSES = {
    0: "NO_DATA",
    1: "SATURATED_OR_DEFECTIVE",
    2: "DARK_AREA_PIXELS",
    3: "CLOUD_SHADOWS",
    4: "VEGETATION",
    5: "NOT_VEGETATED",
    6: "WATER",
    7: "UNCLASSIFIED",
    8: "CLOUD_MEDIUM_PROBABILITY",
    9: "CLOUD_HIGH_PROBABILITY",
    10: "THIN_CIRRUS",
    11: "SNOW_OR_ICE",
}
OBSERVATION_INVALID_CLASSES = frozenset({0, 1, 3, 8, 9, 10, 11})
WATER_CLASS = 6


def observation_valid_mask(scl: np.ndarray) -> np.ndarray:
    values = np.asarray(scl)
    return ~np.isin(values, list(OBSERVATION_INVALID_CLASSES))


def vegetation_land_mask(scl: np.ndarray) -> np.ndarray:
    values = np.asarray(scl)
    return observation_valid_mask(values) & (values != WATER_CLASS)


def water_mask(scl: np.ndarray) -> np.ndarray:
    return np.asarray(scl) == WATER_CLASS

