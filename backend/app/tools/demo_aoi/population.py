from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from pyproj import CRS, Transformer
from shapely.geometry import box, mapping, shape
from shapely.ops import transform, unary_union

from app.grid.pilot import PilotGridCell
from app.tools.era5.percentile import average_rank_01

from .geometry import CANDIDATE_SIZE_M, GRID_SIZE_M, POPULATION_CELL_SIZE_M


POPULATED_CELL_MIN_ESTIMATED_PEOPLE = 1.0
POPULATED_FRACTION_GATE = 0.80
POPULATION_QUARTILE_GATE = 0.25


class CoarsePopulationCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    grid_id: str
    row: int
    column: int
    bounds_projected: tuple[float, float, float, float]
    geometry_projected: dict[str, Any]
    geometry_wgs84: dict[str, Any]
    centroid_lon: float
    centroid_lat: float
    projected_crs: str
    area_m2: float

    def as_pilot_cell(self, *, grid_id: str | None = None) -> PilotGridCell:
        return PilotGridCell(
            grid_id=grid_id or self.grid_id,
            geometry_projected=self.geometry_projected,
            geometry_wgs84=self.geometry_wgs84,
            centroid_lon=self.centroid_lon,
            centroid_lat=self.centroid_lat,
            projected_crs=self.projected_crs,
            area_m2=self.area_m2,
        )


class PopulationCellObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    grid_id: str
    row: int
    column: int
    geometry_wgs84: dict[str, Any]
    population_total: float = Field(ge=0)
    population_age_0_14: float = Field(ge=0)
    population_age_65_plus: float = Field(ge=0)
    populated: bool
    elderly_share: float = Field(ge=0, le=1)
    child_share: float = Field(ge=0, le=1)
    vulnerability_share_raw: float = Field(ge=0, le=1)
    population_composition_status: str
    task_id: str
    request_hash: str
    raw_response_path: str
    data_source: str


class PopulationCandidateMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    population_total_cells: float
    population_whole_area: float
    population_density_per_km2: float
    population_p10: float
    population_p50: float
    population_p90: float
    population_log_spread: float
    populated_cell_count: int
    populated_cell_fraction: float
    vulnerability_share_p10: float | None
    vulnerability_share_p50: float | None
    vulnerability_share_p90: float | None
    vulnerability_share_spread: float | None
    spearman_exposure_vulnerability_all: float | None
    spearman_exposure_vulnerability_populated: float | None
    correlation_status: str
    population_conservation_relative_error: float
    population_density_gate_rank: float | None = None
    final_population_eligible: bool
    rejection_reasons: list[str]
    cells: list[PopulationCellObservation]


class DemoSelectionInput(BaseModel):
    """Final selection contract intentionally has no risk or hazard field."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    population_density_per_km2: float
    lst_p90_p10_spread_c: float
    green_p90_p10_spread: float
    vulnerability_share_spread: float
    populated_cell_fraction: float
    water_fraction: float
    landsat_valid_fraction: float
    sentinel_valid_fraction: float
    satellite_balance_score: float


class RankedDemoCandidate(DemoSelectionInput):
    population_rank: float = Field(ge=0, le=1)
    thermal_rank: float = Field(ge=0, le=1)
    vegetation_rank: float = Field(ge=0, le=1)
    vulnerability_rank: float = Field(ge=0, le=1)
    pareto_front: int = Field(ge=1)
    demo_balance_score: float = Field(ge=0, le=1)
    explanation_labels: list[str]


def build_population_screening_cells(
    candidate: dict[str, Any], projected_crs: str
) -> list[CoarsePopulationCell]:
    west, south, east, north = (float(value) for value in candidate["bounds_projected"])
    if not (
        abs(east - west - CANDIDATE_SIZE_M) < 1e-6
        and abs(north - south - CANDIDATE_SIZE_M) < 1e-6
    ):
        raise ValueError("population screening requires an exact 5 km candidate")
    to_wgs84 = Transformer.from_crs(projected_crs, "EPSG:4326", always_xy=True)
    cells: list[CoarsePopulationCell] = []
    count = CANDIDATE_SIZE_M // POPULATION_CELL_SIZE_M
    for row in range(count):
        for column in range(count):
            cell_west = west + column * POPULATION_CELL_SIZE_M
            cell_south = south + row * POPULATION_CELL_SIZE_M
            polygon = box(
                cell_west,
                cell_south,
                cell_west + POPULATION_CELL_SIZE_M,
                cell_south + POPULATION_CELL_SIZE_M,
            )
            wgs84 = transform(to_wgs84.transform, polygon)
            centroid = wgs84.centroid
            cells.append(
                CoarsePopulationCell(
                    candidate_id=candidate["candidate_id"],
                    grid_id=f"{candidate['candidate_id']}-P-R{row:02d}-C{column:02d}",
                    row=row,
                    column=column,
                    bounds_projected=tuple(float(value) for value in polygon.bounds),
                    geometry_projected=mapping(polygon),
                    geometry_wgs84=mapping(wgs84),
                    centroid_lon=float(centroid.x),
                    centroid_lat=float(centroid.y),
                    projected_crs=projected_crs,
                    area_m2=float(polygon.area),
                )
            )
    return cells


def validate_population_grid(cells: list[CoarsePopulationCell]) -> None:
    if len(cells) != 25:
        raise ValueError("coarse population grid must contain 25 cells")
    polygons = [shape(cell.geometry_projected) for cell in cells]
    if any(
        polygon.area != POPULATION_CELL_SIZE_M**2
        or polygon.bounds[2] - polygon.bounds[0] != POPULATION_CELL_SIZE_M
        or polygon.bounds[3] - polygon.bounds[1] != POPULATION_CELL_SIZE_M
        for polygon in polygons
    ):
        raise ValueError("coarse population cells must be exact 1 km squares")
    union = unary_union(polygons)
    if union.area != CANDIDATE_SIZE_M**2 or sum(p.area for p in polygons) != union.area:
        raise ValueError("coarse population grid has a gap or overlap")


def population_geometry_key(cell: CoarsePopulationCell) -> str:
    canonical = ",".join(f"{value:.3f}" for value in cell.bounds_projected)
    return hashlib.sha256(
        f"{CRS.from_user_input(cell.projected_crs).to_wkt()}|{canonical}".encode("utf-8")
    ).hexdigest()


def deduplicate_population_cells(
    cells: list[CoarsePopulationCell],
) -> dict[str, list[CoarsePopulationCell]]:
    grouped: dict[str, list[CoarsePopulationCell]] = {}
    for cell in cells:
        grouped.setdefault(population_geometry_key(cell), []).append(cell)
    return {key: grouped[key] for key in sorted(grouped)}


def vulnerability_composition(
    total: float, child: float, elderly: float
) -> tuple[float, float, float, str]:
    if min(total, child, elderly) < 0:
        raise ValueError("population estimates cannot be negative")
    tolerance = max(1e-6, total * 1e-6)
    if child > total + tolerance or elderly > total + tolerance or child + elderly > total + tolerance:
        raise ValueError("age subsets exceed total population")
    if total <= 0:
        return 0.0, 0.0, 0.0, "NO_POPULATION"
    elderly_share = elderly / total
    child_share = child / total
    return elderly_share, child_share, 0.7 * elderly_share + 0.3 * child_share, "POPULATED"


def spearman_or_none(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    x = np.asarray(left, dtype=float)
    y = np.asarray(right, dtype=float)
    finite = np.isfinite(x) & np.isfinite(y)
    if finite.sum() < 3 or np.all(x[finite] == x[finite][0]) or np.all(y[finite] == y[finite][0]):
        return None
    return float(np.corrcoef(average_rank_01(x[finite]), average_rank_01(y[finite]))[0, 1])


def summarize_population_candidate(
    candidate_id: str,
    cells: list[PopulationCellObservation],
    whole_area_population: float,
) -> PopulationCandidateMetrics:
    if len(cells) != 25:
        raise ValueError("candidate population summary requires 25 cells")
    populations = np.asarray([cell.population_total for cell in cells], dtype=float)
    populated = [cell for cell in cells if cell.populated]
    vulnerabilities = np.asarray(
        [cell.vulnerability_share_raw for cell in populated], dtype=float
    )
    vulnerability_quantiles = (
        np.percentile(vulnerabilities, [10, 50, 90])
        if vulnerabilities.size
        else np.asarray([np.nan, np.nan, np.nan])
    )
    all_correlation = spearman_or_none(
        np.log1p(populations).tolist(),
        [cell.vulnerability_share_raw for cell in cells],
    )
    populated_correlation = spearman_or_none(
        [float(np.log1p(cell.population_total)) for cell in populated],
        [cell.vulnerability_share_raw for cell in populated],
    )
    total = float(populations.sum())
    reasons: list[str] = []
    fraction = len(populated) / len(cells)
    if fraction < POPULATED_FRACTION_GATE:
        reasons.append("LOW_POPULATED_FRACTION")
    if vulnerabilities.size < 3 or not np.isfinite(vulnerability_quantiles).all():
        reasons.append("INSUFFICIENT_VULNERABILITY_VARIATION")
    spread = (
        float(vulnerability_quantiles[2] - vulnerability_quantiles[0])
        if np.isfinite(vulnerability_quantiles).all()
        else None
    )
    if spread == 0:
        reasons.append("NO_VULNERABILITY_VARIATION")
    return PopulationCandidateMetrics(
        candidate_id=candidate_id,
        population_total_cells=total,
        population_whole_area=whole_area_population,
        population_density_per_km2=total / 25,
        population_p10=float(np.percentile(populations, 10)),
        population_p50=float(np.percentile(populations, 50)),
        population_p90=float(np.percentile(populations, 90)),
        population_log_spread=float(
            np.percentile(np.log1p(populations), 90)
            - np.percentile(np.log1p(populations), 10)
        ),
        populated_cell_count=len(populated),
        populated_cell_fraction=fraction,
        vulnerability_share_p10=(float(vulnerability_quantiles[0]) if vulnerabilities.size else None),
        vulnerability_share_p50=(float(vulnerability_quantiles[1]) if vulnerabilities.size else None),
        vulnerability_share_p90=(float(vulnerability_quantiles[2]) if vulnerabilities.size else None),
        vulnerability_share_spread=spread,
        spearman_exposure_vulnerability_all=all_correlation,
        spearman_exposure_vulnerability_populated=populated_correlation,
        correlation_status=(
            "PASS" if all_correlation is not None and populated_correlation is not None else "INSUFFICIENT_VARIATION"
        ),
        population_conservation_relative_error=abs(total - whole_area_population)
        / max(whole_area_population, 1e-12),
        final_population_eligible=not reasons,
        rejection_reasons=reasons,
        cells=cells,
    )


def apply_relative_population_gate(
    candidates: list[PopulationCandidateMetrics],
) -> tuple[list[PopulationCandidateMetrics], bool]:
    eligible = [candidate for candidate in candidates if candidate.final_population_eligible]
    if len(eligible) < 4:
        return candidates, False
    ranks = average_rank_01(
        np.asarray([candidate.population_density_per_km2 for candidate in eligible])
    )
    updates: dict[str, PopulationCandidateMetrics] = {}
    for candidate, rank in zip(eligible, ranks, strict=True):
        reasons = list(candidate.rejection_reasons)
        if rank < POPULATION_QUARTILE_GATE:
            reasons.append("LOW_RELATIVE_POPULATION_DENSITY")
        updates[candidate.candidate_id] = candidate.model_copy(
            update={
                "population_density_gate_rank": float(rank),
                "final_population_eligible": not reasons,
                "rejection_reasons": reasons,
            }
        )
    return [updates.get(candidate.candidate_id, candidate) for candidate in candidates], True


def _dominates(left: np.ndarray, right: np.ndarray) -> bool:
    return bool(np.all(left >= right) and np.any(left > right))


def assign_pareto_fronts(rank_matrix: np.ndarray) -> list[int]:
    remaining = set(range(len(rank_matrix)))
    fronts = [0] * len(rank_matrix)
    front = 1
    while remaining:
        current = [
            index
            for index in sorted(remaining)
            if not any(
                _dominates(rank_matrix[other], rank_matrix[index])
                for other in remaining
                if other != index
            )
        ]
        for index in current:
            fronts[index] = front
            remaining.remove(index)
        front += 1
    return fronts


def _explanation_labels(candidate: RankedDemoCandidate) -> list[str]:
    labels = []
    for rank, label in (
        (candidate.population_rank, "HIGH_POPULATION_DENSITY"),
        (candidate.thermal_rank, "STRONG_THERMAL_CONTRAST"),
        (candidate.vegetation_rank, "STRONG_GREEN_CONTRAST"),
        (candidate.vulnerability_rank, "STRONG_VULNERABILITY_VARIATION"),
    ):
        if rank >= 0.75:
            labels.append(label)
    if candidate.water_fraction <= 0.05:
        labels.append("LOW_WATER_DOMINANCE")
    if candidate.landsat_valid_fraction >= 0.95 and candidate.sentinel_valid_fraction >= 0.95:
        labels.append("EXCELLENT_SATELLITE_COVERAGE")
    return labels


def rank_and_select_demo_aois(
    candidates: list[DemoSelectionInput], count: int = 3
) -> tuple[list[RankedDemoCandidate], list[RankedDemoCandidate]]:
    if not candidates:
        raise ValueError("at least one final-eligible candidate is required")
    raw = np.asarray(
        [
            [
                candidate.population_density_per_km2,
                candidate.lst_p90_p10_spread_c,
                candidate.green_p90_p10_spread,
                candidate.vulnerability_share_spread,
            ]
            for candidate in candidates
        ],
        dtype=float,
    )
    ranks = np.column_stack([average_rank_01(raw[:, index]) for index in range(4)])
    fronts = assign_pareto_fronts(ranks)
    ranked: list[RankedDemoCandidate] = []
    for candidate, values, front in zip(candidates, ranks, fronts, strict=True):
        provisional = RankedDemoCandidate(
            **candidate.model_dump(),
            population_rank=float(values[0]),
            thermal_rank=float(values[1]),
            vegetation_rank=float(values[2]),
            vulnerability_rank=float(values[3]),
            pareto_front=front,
            demo_balance_score=float(values.min()),
            explanation_labels=[],
        )
        ranked.append(
            provisional.model_copy(
                update={"explanation_labels": _explanation_labels(provisional)}
            )
        )
    ordered = sorted(
        ranked,
        key=lambda candidate: (
            candidate.pareto_front,
            -candidate.demo_balance_score,
            -candidate.populated_cell_fraction,
            candidate.water_fraction,
            -min(candidate.landsat_valid_fraction, candidate.sentinel_valid_fraction),
            -candidate.satellite_balance_score,
            candidate.candidate_id,
        ),
    )
    return ranked, ordered[:count]


def build_selected_future_grid(
    candidate: dict[str, Any], projected_crs: str
) -> dict[str, Any]:
    west, south, _, _ = (float(value) for value in candidate["bounds_projected"])
    to_wgs84 = Transformer.from_crs(projected_crs, "EPSG:4326", always_xy=True)
    features = []
    count = CANDIDATE_SIZE_M // GRID_SIZE_M
    for row in range(count):
        for column in range(count):
            polygon = box(
                west + column * GRID_SIZE_M,
                south + row * GRID_SIZE_M,
                west + (column + 1) * GRID_SIZE_M,
                south + (row + 1) * GRID_SIZE_M,
            )
            grid_id = f"{candidate['candidate_id']}-G-R{row:02d}-C{column:02d}"
            features.append(
                {
                    "type": "Feature",
                    "id": grid_id,
                    "geometry": mapping(transform(to_wgs84.transform, polygon)),
                    "properties": {"grid_id": grid_id, "row": row, "column": column},
                }
            )
    return {"type": "FeatureCollection", "features": features}
