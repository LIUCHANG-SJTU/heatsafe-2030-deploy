from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np


def nearest_hour(value: datetime) -> datetime:
    """Round to the nearest hour; exact half-hours round to the later hour."""
    floor = value.replace(minute=0, second=0, microsecond=0)
    elapsed = value - floor
    return floor + (timedelta(hours=1) if elapsed >= timedelta(minutes=30) else timedelta())


def kelvin_to_celsius(values: np.ndarray | float) -> np.ndarray:
    return np.asarray(values, dtype=float) - 273.15
