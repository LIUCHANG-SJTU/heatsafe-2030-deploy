from __future__ import annotations

from app.models.grid import GridCell, RawGridCell

from .score import RiskEngine


def apply_temperature_scenario(
    cells: list[RawGridCell], temperature_delta: float, engine: RiskEngine | None = None
) -> list[GridCell]:
    """Run a bounded sensitivity scenario, not a causal prediction."""

    return (engine or RiskEngine()).score(cells, temperature_delta=temperature_delta)

