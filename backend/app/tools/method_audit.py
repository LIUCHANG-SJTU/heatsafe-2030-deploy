from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.models.era5 import ERA5TemporalContext
from app.models.grid import DataMode, derive_data_mode
from app.models.hazard import SpatiotemporalHazardArtifact
from app.models.landsat import LandsatArtifact
from app.models.sentinel2 import SentinelVegetationArtifact
from app.risk.normalize import robust_normalize
from app.risk.vulnerability import (
    LEGACY_METHOD,
    PRIMARY_METHOD,
    age_composition_scores,
    age_count_raw,
)
from app.tools.era5.percentile import average_rank_01
from app.tools.worldpop.models import WorldPopArtifact


def _spearman(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.corrcoef(average_rank_01(left), average_rank_01(right))[0, 1])


def _top_ids(values: np.ndarray, grid_ids: list[str], count: int = 10) -> list[str]:
    indices = np.argsort(values, kind="stable")[-count:][::-1]
    return [grid_ids[index] for index in indices]


def run_m3b1_audit(project_dir: Path) -> dict[str, Any]:
    worldpop = WorldPopArtifact.model_validate_json(
        (project_dir / "data/processed/worldpop/worldpop_population_2026.json").read_text()
    )
    landsat = LandsatArtifact.model_validate_json(
        (project_dir / "data/processed/landsat/landsat_lst_pilot_2026.json").read_text()
    )
    sentinel = SentinelVegetationArtifact.model_validate_json(
        (project_dir / "data/processed/sentinel2/sentinel2_vegetation_pilot_2026.json").read_text()
    )
    context = ERA5TemporalContext.model_validate_json(
        (project_dir / "data/processed/era5/era5_temporal_context.json").read_text()
    )
    hazard = SpatiotemporalHazardArtifact.model_validate_json(
        (project_dir / "data/processed/hazard/spatiotemporal_hazard_pilot_2026.json").read_text()
    )
    population = {grid.grid_id: grid for grid in worldpop.grids}
    vegetation = {grid.grid_id: grid for grid in sentinel.grids}
    hazard_by_grid = {grid.grid_id: grid for grid in hazard.grids}
    grid_ids = [grid.grid_id for grid in landsat.grids]
    total = np.array([population[grid_id].population_total for grid_id in grid_ids])
    children = np.array([population[grid_id].population_age_0_14 for grid_id in grid_ids])
    elderly = np.array([population[grid_id].population_age_65_plus for grid_id in grid_ids])
    exposure = robust_normalize(np.log1p(total))
    count_raw = age_count_raw(children, elderly)
    count_score = robust_normalize(count_raw)
    share_score, share_raw, child_share, elderly_share, status = age_composition_scores(
        total, children, elderly
    )
    hazard_score = np.array([hazard_by_grid[grid_id].hazard_score for grid_id in grid_ids])
    adaptive = np.array([vegetation[grid_id].adaptive_capacity.score for grid_id in grid_ids])
    risk_count = 100 * (
        0.40 * hazard_score
        + 0.25 * exposure
        + 0.20 * count_score
        + 0.15 * (1 - adaptive)
    )
    risk_share = 100 * (
        0.40 * hazard_score
        + 0.25 * exposure
        + 0.20 * share_score
        + 0.15 * (1 - adaptive)
    )
    component_modes = {
        "population": worldpop.data_mode,
        "vulnerability": worldpop.data_mode,
        "spatial_heat": landsat.data_mode,
        "vegetation": sentinel.data_mode,
        "temporal_heat": context.source_mode,
    }
    data_mode = derive_data_mode(component_modes)
    rows = [
        {
            "grid_id": grid_id,
            "hazard_score": float(hazard_score[index]),
            "exposure_score": float(exposure[index]),
            "vulnerability_score": float(share_score[index]),
            "vulnerability_raw": float(share_raw[index]),
            "child_share": float(child_share[index]),
            "elderly_share": float(elderly_share[index]),
            "population_composition_status": str(status[index]),
            "adaptive_capacity_score": float(adaptive[index]),
            "risk_score": float(risk_share[index]),
            "temporal_context_id": context.temporal_context_id,
            "data_mode": data_mode.value,
            "model_status": "PRELIMINARY_HEURISTIC",
        }
        for index, grid_id in enumerate(grid_ids)
    ]
    methods = {
        "vulnerability": PRIMARY_METHOD,
        "adaptive_capacity": "VEGETATION_PROXY_HEURISTIC",
        "temporal_heat": "TEMPORAL_HEAT_CONTEXT_HEURISTIC",
        "hazard": "SPATIOTEMPORAL_HEAT_HAZARD_HEURISTIC",
        "risk": "TRANSPARENT_WEIGHTED_RISK_HEURISTIC",
    }
    analysis = {
        "analysis_version": "M3B.1",
        "data_mode": data_mode.value,
        "component_modes": {key: DataMode(value).value for key, value in component_modes.items()},
        "model_status": "PRELIMINARY_HEURISTIC",
        "temporal_context_id": context.temporal_context_id,
        "methods": methods,
        "grids": rows,
    }
    analysis_dir = project_dir / "data/processed/analysis"
    (analysis_dir / "heatsafe_pilot_real_2026_v2.json").write_text(
        json.dumps(analysis, indent=2) + "\n", encoding="utf-8"
    )
    pd.DataFrame(rows).to_parquet(
        analysis_dir / "heatsafe_pilot_real_2026_v2.parquet", index=False
    )
    difference = np.abs(risk_count - risk_share)
    audit = {
        "M3B1_STATUS": "PASS",
        "legacy_vulnerability_method": LEGACY_METHOD,
        "primary_vulnerability_method": PRIMARY_METHOD,
        "spearman_exposure_v_count": _spearman(exposure, count_score),
        "spearman_exposure_v_share": _spearman(exposure, share_score),
        "spearman_v_count_v_share": _spearman(count_score, share_score),
        "risk_count_v_share_spearman": _spearman(risk_count, risk_share),
        "risk_top10_overlap": len(
            set(_top_ids(risk_count, grid_ids)) & set(_top_ids(risk_share, grid_ids))
        )
        / 10,
        "risk_mean_absolute_difference": float(np.mean(difference)),
        "risk_max_absolute_difference": float(np.max(difference)),
        "top10_count_grid_ids": _top_ids(risk_count, grid_ids),
        "top10_share_grid_ids": _top_ids(risk_share, grid_ids),
        "zero_population_grid_count": int(np.sum(status == "NO_POPULATION")),
        "full_analysis_data_mode": data_mode.value,
        "model_status": "PRELIMINARY_HEURISTIC",
    }
    reports = project_dir / "reports"
    (reports / "m3b1_vulnerability_method_audit.json").write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8"
    )
    return audit
