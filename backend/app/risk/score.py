from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.models.grid import GridCell, RawGridCell

from .normalize import require_complete, robust_normalize
from .vulnerability import age_composition_scores


@dataclass(frozen=True)
class RiskWeights:
    hazard: float = 0.40
    exposure: float = 0.25
    vulnerability: float = 0.20
    adaptive_capacity_gap: float = 0.15

    def __post_init__(self) -> None:
        values = (
            self.hazard,
            self.exposure,
            self.vulnerability,
            self.adaptive_capacity_gap,
        )
        if any(value < 0 for value in values):
            raise ValueError("risk weights cannot be negative")
        if not np.isclose(sum(values), 1.0):
            raise ValueError("risk weights must sum to 1.0")


DEFAULT_WEIGHTS = RiskWeights()


class RiskEngine:
    """Deterministic implementation of the preliminary HeatSafe heuristic."""

    def __init__(self, weights: RiskWeights = DEFAULT_WEIGHTS) -> None:
        self.weights = weights

    def score(
        self, raw_cells: list[RawGridCell], temperature_delta: float = 0.0
    ) -> list[GridCell]:
        if not raw_cells:
            return []
        if temperature_delta < 0 or temperature_delta > 5:
            raise ValueError("temperature_delta must be between 0 and 5 Celsius")

        lst = np.array(
            [cell.land_surface_temperature for cell in raw_cells], dtype=float
        )
        baseline_percentile = np.array(
            [cell.temperature_percentile for cell in raw_cells], dtype=float
        )
        exceedance = np.array(
            [cell.heat_exceedance_hours for cell in raw_cells], dtype=float
        )
        population = np.array(
            [cell.population_total for cell in raw_cells], dtype=float
        )
        age_0_14 = np.array(
            [cell.population_age_0_14 for cell in raw_cells], dtype=float
        )
        age_65_plus = np.array(
            [cell.population_age_65_plus for cell in raw_cells], dtype=float
        )
        ndvi = np.array([cell.ndvi for cell in raw_cells], dtype=float)

        lst_spatial = robust_normalize(lst)
        scenario_percentile = np.clip(
            baseline_percentile + temperature_delta * 0.08, 0.0, 1.0
        )
        scenario_exceedance = exceedance + temperature_delta * 2.0
        exceedance_score = robust_normalize(scenario_exceedance)
        if all(cell.spatiotemporal_hazard is not None for cell in raw_cells):
            if temperature_delta:
                raise ValueError(
                    "scenario_temperature_delta is unavailable with a fixed REAL ERA5 context"
                )
            hazard = np.array(
                [cell.spatiotemporal_hazard.hazard_score for cell in raw_cells],
                dtype=float,
            )
        else:
            hazard = (
                0.45 * lst_spatial
                + 0.35 * scenario_percentile
                + 0.20 * exceedance_score
            )

        exposure = robust_normalize(np.log1p(population))
        vulnerability, _, _, _, composition_status = age_composition_scores(
            population, age_0_14, age_65_plus
        )
        if all(
            cell.adaptive_capacity is not None
            and cell.adaptive_capacity.score is not None
            for cell in raw_cells
        ):
            adaptive_capacity = np.array(
                [cell.adaptive_capacity.score for cell in raw_cells], dtype=float
            )
        else:
            adaptive_capacity = robust_normalize(ndvi)

        complete = require_complete(
            hazard, exposure, vulnerability, adaptive_capacity
        )
        if not complete.all():
            missing_ids = [
                raw_cells[index].grid_id
                for index, is_complete in enumerate(complete)
                if not is_complete
            ]
            raise ValueError(
                "required risk inputs are missing for grids: " + ", ".join(missing_ids)
            )

        risk = 100.0 * (
            self.weights.hazard * hazard
            + self.weights.exposure * exposure
            + self.weights.vulnerability * vulnerability
            + self.weights.adaptive_capacity_gap * (1.0 - adaptive_capacity)
        )
        risk = np.clip(risk, 0.0, 100.0)

        scored_cells: list[GridCell] = []
        for index, cell in enumerate(raw_cells):
            payload = cell.model_dump()
            payload.update(
                land_surface_temperature=round(
                    cell.land_surface_temperature + temperature_delta, 3
                ),
                temperature_percentile=round(scenario_percentile[index], 6),
                heat_exceedance_hours=round(scenario_exceedance[index], 3),
                hazard_score=round(hazard[index], 6),
                exposure_score=round(exposure[index], 6),
                vulnerability_score=round(vulnerability[index], 6),
                adaptive_capacity_score=round(adaptive_capacity[index], 6),
                population_composition_status=str(composition_status[index]),
                risk_score=round(risk[index], 3),
            )
            scored_cells.append(GridCell.model_validate(payload))
        return scored_cells
