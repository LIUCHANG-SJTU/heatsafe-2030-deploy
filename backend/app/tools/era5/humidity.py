from __future__ import annotations

import math


def relative_humidity_percent(temperature_c: float, dewpoint_c: float) -> float:
    if not math.isfinite(temperature_c) or not math.isfinite(dewpoint_c):
        raise ValueError("temperature and dewpoint must be finite")
    exponent = (
        17.625 * dewpoint_c / (243.04 + dewpoint_c)
        - 17.625 * temperature_c / (243.04 + temperature_c)
    )
    value = 100.0 * math.exp(exponent)
    if value < -1 or value > 101:
        raise ValueError("relative humidity indicates invalid units or values")
    return min(100.0, max(0.0, value))
