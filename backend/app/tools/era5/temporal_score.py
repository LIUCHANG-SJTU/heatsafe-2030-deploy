from __future__ import annotations


def temporal_severity(
    intensity: float,
    consecutive_hot_hours: int,
    intensity_weight: float = 0.7,
) -> tuple[float, float]:
    if not 0 <= intensity <= 1 or not 0 <= intensity_weight <= 1:
        raise ValueError("scores and weights must be within [0,1]")
    persistence = min(consecutive_hot_hours / 24.0, 1.0)
    severity = intensity_weight * intensity + (1 - intensity_weight) * persistence
    return persistence, severity
