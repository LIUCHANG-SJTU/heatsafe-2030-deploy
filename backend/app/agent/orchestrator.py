from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.fixtures.pipeline import build_fixture_cells, write_fixture_dataset
from app.models.api import (
    AnalysisRequest,
    AnalysisResponse,
    AnalysisSummary,
)
from app.models.era5 import ERA5TemporalContext
from app.models.hazard import SpatiotemporalHazardArtifact
from app.models.grid import (
    ComponentModes,
    DataMode,
    GridCell,
    RawGridCell,
    derive_data_mode,
)
from app.models.landsat import CoverageQuality, LandsatArtifact
from app.models.sentinel2 import SentinelVegetationArtifact
from app.models.provenance import ProvenanceRecord
from app.risk.score import RiskEngine
from app.risk.vulnerability import age_composition_raw
from app.tools.worldpop.models import WorldPopArtifact

from .planner import DeterministicPlanner
from .verifier import EvidenceClaim, Verifier


HIGH_RISK_THRESHOLD = 70.0
SCENARIO_DISCLAIMER = (
    "Scenario sensitivity estimate based on a preliminary transparent heuristic; "
    "not a causal prediction, validated risk model, or representative citywide analysis."
)


class HeatSafeOrchestrator:
    def __init__(
        self,
        fixture_grid_path: Path,
        provenance_path: Path,
        worldpop_artifact_path: Path | None = None,
        landsat_artifact_path: Path | None = None,
        sentinel_artifact_path: Path | None = None,
        era5_temporal_context_path: Path | None = None,
        hazard_artifact_path: Path | None = None,
        risk_engine: RiskEngine | None = None,
    ) -> None:
        self.fixture_grid_path = fixture_grid_path
        self.provenance_path = provenance_path
        self.worldpop_artifact_path = worldpop_artifact_path
        self.landsat_artifact_path = landsat_artifact_path
        self.sentinel_artifact_path = sentinel_artifact_path
        self.era5_temporal_context_path = era5_temporal_context_path
        self.hazard_artifact_path = hazard_artifact_path
        self.risk_engine = risk_engine or RiskEngine()
        self.planner = DeterministicPlanner()
        self.verifier = Verifier()

    def _ensure_fixture(self) -> None:
        if not self.fixture_grid_path.exists() or not self.provenance_path.exists():
            write_fixture_dataset(self.fixture_grid_path, self.provenance_path)

    def raw_cells(
        self,
        population_mode: str = "fixture",
        temperature_mode: str = "fixture",
        vegetation_mode: str = "fixture",
        temporal_mode: str = "fixture",
    ) -> list[RawGridCell]:
        self._ensure_fixture()
        payload = json.loads(self.fixture_grid_path.read_text(encoding="utf-8"))
        if payload.get("data_mode") != "FIXTURE":
            raise ValueError("M0 fixture pipeline received a non-fixture dataset")
        fixture_cells = [RawGridCell.model_validate(cell) for cell in payload["cells"]]
        if population_mode not in {"fixture", "real"}:
            raise ValueError("population_mode must be fixture or real")
        if temperature_mode not in {"fixture", "real"}:
            raise ValueError("temperature_mode must be fixture or real")
        if temperature_mode == "real" and population_mode != "real":
            raise ValueError(
                "temperature_mode=real requires population_mode=real so both artifacts "
                "use the canonical projected pilot_v1 grid"
            )
        if vegetation_mode not in {"fixture", "real"}:
            raise ValueError("vegetation_mode must be fixture or real")
        if vegetation_mode == "real" and population_mode != "real":
            raise ValueError(
                "vegetation_mode=real requires population_mode=real so both artifacts "
                "use the canonical projected pilot_v1 grid"
            )
        if temporal_mode not in {"fixture", "real"}:
            raise ValueError("temporal_mode must be fixture or real")
        if temporal_mode == "real" and not all(
            mode == "real"
            for mode in (population_mode, temperature_mode, vegetation_mode)
        ):
            raise ValueError(
                "temporal_mode=real requires population_mode, temperature_mode, "
                "and vegetation_mode all set to real"
            )
        cells = (
            self._join_real_population(fixture_cells)
            if population_mode == "real"
            else fixture_cells
        )
        cells = (
            self._join_real_landsat(cells)
            if temperature_mode == "real"
            else cells
        )
        cells = (
            self._join_real_sentinel(cells)
            if vegetation_mode == "real"
            else cells
        )
        return self._join_real_temporal(cells) if temporal_mode == "real" else cells

    def _join_real_population(
        self, fixture_cells: list[RawGridCell]
    ) -> list[RawGridCell]:
        if self.worldpop_artifact_path is None or not self.worldpop_artifact_path.exists():
            raise ValueError(
                "population_mode=real requested but WorldPop REAL artifact is unavailable"
            )
        artifact = WorldPopArtifact.model_validate_json(
            self.worldpop_artifact_path.read_text(encoding="utf-8")
        )
        if artifact.data_mode != "REAL" or len(artifact.grids) != len(fixture_cells):
            raise ValueError("WorldPop REAL artifact must contain all 100 pilot grids")
        joined: list[RawGridCell] = []
        for fixture, population in zip(fixture_cells, artifact.grids, strict=True):
            payload = fixture.model_dump()
            fixture_sources = [
                source_id
                for source_id in fixture.data_source_ids
                if source_id
                not in {"fixture:worldpop-total", "fixture:worldpop-age-sex"}
            ]
            component_modes = ComponentModes(
                hazard=DataMode.FIXTURE,
                exposure=DataMode.REAL,
                vulnerability=DataMode.REAL,
                adaptive_capacity=DataMode.FIXTURE,
                risk=DataMode.MIXED,
                population=DataMode.REAL,
                spatial_heat=DataMode.FIXTURE,
                vegetation=DataMode.FIXTURE,
                temporal_heat=DataMode.FIXTURE,
            )
            payload.update(
                grid_id=population.grid_id,
                geometry=population.geometry_wgs84,
                lat=population.centroid_lat,
                lon=population.centroid_lon,
                population_total=population.population_total,
                population_age_0_14=population.population_age_0_14,
                population_age_65_plus=population.population_age_65_plus,
                data_source_ids=fixture_sources + [population.source_id],
                data_mode=DataMode.MIXED,
                component_modes=component_modes,
                component_source_ids={
                    "hazard": ["fixture:landsat-st", "fixture:era5-land"],
                    "exposure": [population.source_id],
                    "vulnerability": [population.source_id],
                    "adaptive_capacity": ["fixture:sentinel-2-ndvi"],
                    "risk": fixture_sources + [population.source_id],
                },
            )
            joined.append(RawGridCell.model_validate(payload))
        return joined

    def _join_real_sentinel(
        self, source_cells: list[RawGridCell]
    ) -> list[RawGridCell]:
        if self.sentinel_artifact_path is None or not self.sentinel_artifact_path.exists():
            raise ValueError(
                "vegetation_mode=real requested but Sentinel REAL artifact is unavailable"
            )
        artifact = SentinelVegetationArtifact.model_validate_json(
            self.sentinel_artifact_path.read_text(encoding="utf-8")
        )
        by_grid = {grid.grid_id: grid for grid in artifact.grids}
        if artifact.data_mode != "REAL" or set(by_grid) != {
            cell.grid_id for cell in source_cells
        }:
            raise ValueError("Sentinel REAL artifact must contain all 100 pilot grids")
        insufficient = [
            grid.grid_id
            for grid in artifact.grids
            if grid.quality_flag == CoverageQuality.INSUFFICIENT
            or grid.adaptive_capacity.score is None
        ]
        if insufficient:
            raise ValueError(
                "Sentinel artifact has INSUFFICIENT coverage and cannot enter risk: "
                + ", ".join(insufficient)
            )
        joined: list[RawGridCell] = []
        for source in source_cells:
            vegetation = by_grid[source.grid_id]
            payload = source.model_dump()
            retained_sources = [
                source_id
                for source_id in source.data_source_ids
                if source_id != "fixture:sentinel-2-ndvi"
            ]
            previous = source.component_modes
            component_modes = ComponentModes(
                hazard=previous.hazard,
                exposure=previous.exposure,
                vulnerability=previous.vulnerability,
                adaptive_capacity=DataMode.REAL,
                risk=DataMode.MIXED,
                population=previous.population,
                spatial_heat=previous.spatial_heat,
                vegetation=DataMode.REAL,
                temporal_heat=previous.temporal_heat,
            )
            sources = dict(source.component_source_ids)
            sources["adaptive_capacity"] = [vegetation.source_id]
            sources["vegetation"] = [vegetation.source_id]
            sources["risk"] = sorted(set(retained_sources + [vegetation.source_id]))
            payload.update(
                ndvi=(
                    vegetation.ndvi_median
                    if vegetation.ndvi_median is not None
                    else 0.0
                ),
                vegetation=vegetation,
                adaptive_capacity=vegetation.adaptive_capacity,
                data_source_ids=sorted(set(retained_sources + [vegetation.source_id])),
                data_mode=DataMode.MIXED,
                component_modes=component_modes,
                component_source_ids=sources,
            )
            joined.append(RawGridCell.model_validate(payload))
        return joined

    def _join_real_landsat(
        self, source_cells: list[RawGridCell]
    ) -> list[RawGridCell]:
        if self.landsat_artifact_path is None or not self.landsat_artifact_path.exists():
            raise ValueError(
                "temperature_mode=real requested but Landsat REAL artifact is unavailable"
            )
        artifact = LandsatArtifact.model_validate_json(
            self.landsat_artifact_path.read_text(encoding="utf-8")
        )
        by_grid = {grid.grid_id: grid for grid in artifact.grids}
        if artifact.data_mode != "REAL" or set(by_grid) != {
            cell.grid_id for cell in source_cells
        }:
            raise ValueError("Landsat REAL artifact must contain all 100 pilot grids")
        insufficient = [
            grid.grid_id
            for grid in artifact.grids
            if grid.quality_flag == CoverageQuality.INSUFFICIENT
            or grid.lst_median_c is None
        ]
        if insufficient:
            raise ValueError(
                "Landsat artifact has INSUFFICIENT coverage and cannot enter hazard: "
                + ", ".join(insufficient)
            )
        joined: list[RawGridCell] = []
        for source in source_cells:
            temperature = by_grid[source.grid_id]
            payload = source.model_dump()
            retained_sources = [
                source_id
                for source_id in source.data_source_ids
                if source_id != "fixture:landsat-st"
            ]
            previous_modes = source.component_modes
            population_is_real = previous_modes.exposure == DataMode.REAL
            component_modes = ComponentModes(
                hazard=DataMode.MIXED,
                exposure=DataMode.REAL if population_is_real else DataMode.FIXTURE,
                vulnerability=DataMode.REAL if population_is_real else DataMode.FIXTURE,
                adaptive_capacity=previous_modes.adaptive_capacity,
                risk=DataMode.MIXED,
                population=previous_modes.population,
                spatial_heat=DataMode.REAL,
                vegetation=previous_modes.vegetation,
                temporal_heat=previous_modes.temporal_heat,
            )
            sources = dict(source.component_source_ids)
            sources["hazard"] = [
                temperature.source_id,
                "fixture:era5-land",
            ]
            sources["surface_temperature"] = [temperature.source_id]
            sources["risk"] = sorted(set(retained_sources + [temperature.source_id]))
            payload.update(
                land_surface_temperature=temperature.lst_median_c,
                surface_temperature=temperature,
                data_source_ids=sorted(set(retained_sources + [temperature.source_id])),
                data_mode=DataMode.MIXED,
                component_modes=component_modes,
                component_source_ids=sources,
            )
            joined.append(RawGridCell.model_validate(payload))
        return joined

    def _join_real_temporal(
        self, source_cells: list[RawGridCell]
    ) -> list[RawGridCell]:
        if (
            self.era5_temporal_context_path is None
            or not self.era5_temporal_context_path.exists()
        ):
            raise ValueError(
                "temporal_mode=real requested but ERA5 REAL artifact is unavailable"
            )
        if self.hazard_artifact_path is None or not self.hazard_artifact_path.exists():
            raise ValueError(
                "temporal_mode=real requested but REAL hazard artifact is unavailable"
            )
        context = ERA5TemporalContext.model_validate_json(
            self.era5_temporal_context_path.read_text(encoding="utf-8")
        )
        hazard = SpatiotemporalHazardArtifact.model_validate_json(
            self.hazard_artifact_path.read_text(encoding="utf-8")
        )
        by_grid = {grid.grid_id: grid for grid in hazard.grids}
        if set(by_grid) != {cell.grid_id for cell in source_cells}:
            raise ValueError("REAL hazard artifact must contain all 100 pilot grids")
        if hazard.temporal_context_id != context.temporal_context_id:
            raise ValueError("ERA5 context and hazard artifact IDs differ")
        joined: list[RawGridCell] = []
        for source in source_cells:
            previous = source.component_modes
            if not all(
                mode == DataMode.REAL
                for mode in (
                    previous.population,
                    previous.vulnerability,
                    previous.spatial_heat,
                    previous.vegetation,
                    previous.adaptive_capacity,
                )
            ):
                raise ValueError("REAL temporal hazard requires every prior component REAL")
            grid_hazard = by_grid[source.grid_id]
            retained_sources = [
                source_id
                for source_id in source.data_source_ids
                if source_id != "fixture:era5-land"
            ]
            modes = ComponentModes(
                hazard=DataMode.REAL,
                exposure=DataMode.REAL,
                vulnerability=DataMode.REAL,
                adaptive_capacity=DataMode.REAL,
                risk=DataMode.REAL,
                population=DataMode.REAL,
                spatial_heat=DataMode.REAL,
                vegetation=DataMode.REAL,
                temporal_heat=DataMode.REAL,
            )
            payload = source.model_dump()
            sources = dict(source.component_source_ids)
            sources["temporal_heat"] = [context.source_id]
            sources["hazard"] = [grid_hazard.source_id if hasattr(grid_hazard, "source_id") else hazard.source_id]
            sources["risk"] = sorted(set(retained_sources + [context.source_id, hazard.source_id]))
            payload.update(
                temporal_context_id=context.temporal_context_id,
                spatiotemporal_hazard=grid_hazard,
                temperature_percentile=context.temperature_percentile,
                heat_exceedance_hours=context.consecutive_hot_hours_at_reference,
                data_timestamp=context.satellite_reference_time,
                data_source_ids=sorted(set(retained_sources + [context.source_id, hazard.source_id])),
                data_mode=DataMode.REAL,
                component_modes=modes,
                component_source_ids=sources,
            )
            joined.append(RawGridCell.model_validate(payload))
        return joined

    def provenance(self) -> list[ProvenanceRecord]:
        self._ensure_fixture()
        payload = json.loads(self.provenance_path.read_text(encoding="utf-8"))
        return [ProvenanceRecord.model_validate(payload)]

    @staticmethod
    def _filter_bbox(
        cells: list[RawGridCell],
        bbox: tuple[float, float, float, float] | None,
    ) -> list[RawGridCell]:
        if bbox is None:
            return cells
        west, south, east, north = bbox
        return [
            cell
            for cell in cells
            if west <= cell.lon <= east and south <= cell.lat <= north
        ]

    def baseline_grids(
        self,
        population_mode: str = "fixture",
        temperature_mode: str = "fixture",
        vegetation_mode: str = "fixture",
        temporal_mode: str = "fixture",
    ) -> list[GridCell]:
        return self.risk_engine.score(
            self.raw_cells(population_mode, temperature_mode, vegetation_mode, temporal_mode)
        )

    def analyze(self, request: AnalysisRequest) -> AnalysisResponse:
        plan = self.planner.plan(request)
        selected = self._filter_bbox(
            self.raw_cells(
                request.population_mode,
                request.temperature_mode,
                request.vegetation_mode,
                request.temporal_mode,
            ),
            plan.area,
        )
        if not selected:
            raise ValueError("requested bbox does not intersect the fixture grid")

        scored = self.risk_engine.score(
            selected, temperature_delta=request.scenario_temperature_delta
        )
        ordered = sorted(scored, key=lambda cell: cell.risk_score, reverse=True)
        high_risk = [cell for cell in scored if cell.risk_score >= HIGH_RISK_THRESHOLD]
        risk_values = np.array([cell.risk_score for cell in scored], dtype=float)
        population_values = np.array(
            [cell.population_total for cell in selected], dtype=float
        )
        vulnerability_values, _, _, _ = age_composition_raw(
            population_values,
            np.array([cell.population_age_0_14 for cell in selected], dtype=float),
            np.array([cell.population_age_65_plus for cell in selected], dtype=float),
        )
        provenance_records = self.provenance()
        provenance = [record.model_dump(mode="json") for record in provenance_records]
        if request.population_mode == "real":
            real_artifact = WorldPopArtifact.model_validate_json(
                self.worldpop_artifact_path.read_text(encoding="utf-8")
            )
            api_data_sources = sorted(
                {grid.data_source for grid in real_artifact.grids}
            )
            provenance.append(
                {
                    "dataset": ", ".join(api_data_sources),
                    "provider": "WorldPop",
                    "source_url": "https://api.worldpop.org/v2",
                    "license": "CC BY 4.0",
                    "data_mode": "REAL",
                    "artifact_path": str(self.worldpop_artifact_path),
                    "note": "API-returned source string retained; no asserted Hub ID/version/DOI mapping. Per-grid sidecars are stored on disk.",
                }
            )
        if request.temperature_mode == "real":
            artifact = LandsatArtifact.model_validate_json(
                self.landsat_artifact_path.read_text(encoding="utf-8")
            )
            provenance.append(
                {
                    "dataset": "Landsat Collection 2 Level-2 Surface Temperature",
                    "provider": "U.S. Geological Survey",
                    "access_service": "Microsoft Planetary Computer",
                    "data_mode": "REAL",
                    "artifact_path": str(self.landsat_artifact_path),
                    "scene_id": artifact.scene_id,
                    "note": "Single-scene LST aggregated to the 250 m HeatSafe grid; not a complete temporal heat hazard.",
                }
            )
        if request.vegetation_mode == "real":
            artifact = SentinelVegetationArtifact.model_validate_json(
                self.sentinel_artifact_path.read_text(encoding="utf-8")
            )
            provenance.append(
                {
                    "dataset": "Sentinel-2 Level-2A Surface Reflectance",
                    "provider": "ESA / Copernicus",
                    "access_service": "Microsoft Planetary Computer",
                    "data_mode": "REAL",
                    "artifact_path": str(self.sentinel_artifact_path),
                    "scene_ids": artifact.scene_ids,
                    "method": "VEGETATION_PROXY_HEURISTIC",
                    "note": "REAL vegetation observations feed a preliminary adaptive-capacity proxy; this is not a validated complete capacity model.",
                }
            )
        temporal_context = None
        if request.temporal_mode == "real":
            temporal_context = ERA5TemporalContext.model_validate_json(
                self.era5_temporal_context_path.read_text(encoding="utf-8")
            )
            provenance.append(
                {
                    "dataset": "ERA5-Land hourly time-series data on single levels",
                    "provider": "Copernicus Climate Change Service / ECMWF",
                    "access_service": "Copernicus Climate Data Store",
                    "data_mode": "REAL",
                    "artifact_path": str(self.era5_temporal_context_path),
                    "temporal_context_id": temporal_context.temporal_context_id,
                    "note": "One shared nearest-grid temporal context; no 250 m ERA5 spatial field is implied.",
                }
            )
        has_real_component = "real" in {
            request.population_mode,
            request.temperature_mode,
            request.vegetation_mode,
            request.temporal_mode,
        }
        component_modes = selected[0].component_modes
        analysis_mode = derive_data_mode(component_modes)
        if analysis_mode == DataMode.REAL:
            provenance = [
                record for record in provenance if record.get("data_mode") != "FIXTURE"
            ]
        claims = [
            EvidenceClaim(
                claim="Grid risk values were calculated by the deterministic M0 engine.",
                source_ids=[record.dataset for record in provenance_records],
                is_scenario_estimate=request.scenario_temperature_delta > 0,
                causal_language=False,
            )
        ]
        verification = self.verifier.verify(claims)

        return AnalysisResponse(
            data_mode=analysis_mode,
            component_modes=component_modes,
            summary=AnalysisSummary(
                area_label=(
                    "pilot_v1 engineering AOI (MIXED real and fixture inputs)"
                    if analysis_mode == DataMode.MIXED
                    else "pilot_v1 engineering AOI (all source observations REAL)"
                    if analysis_mode == DataMode.REAL
                    else "Hangzhou pilot bbox (synthetic fixture)"
                ),
                data_mode=analysis_mode,
                grid_count=len(scored),
                scenario_temperature_delta=request.scenario_temperature_delta,
                high_risk_grid_count=len(high_risk),
                exposed_population_in_high_risk_grids=round(
                    sum(cell.population_total for cell in high_risk)
                ),
                disclaimer=SCENARIO_DISCLAIMER,
            ),
            top_risk_grids=ordered[: request.top_n],
            statistics={
                "risk_score_min": round(float(risk_values.min()), 3),
                "risk_score_mean": round(float(risk_values.mean()), 3),
                "risk_score_max": round(float(risk_values.max()), 3),
                "high_risk_threshold": HIGH_RISK_THRESHOLD,
                "verification": verification.model_dump(),
                "analysis_plan": plan.model_dump(mode="json"),
                "normalization": {
                    "method": "robust percentile scaling with clipping",
                    "lower_percentile": 5,
                    "upper_percentile": 95,
                    "reference_population": f"{len(selected)} selected pilot grids",
                    "exposure_raw_bounds": {
                        "p05_log1p_population": round(
                            float(np.percentile(np.log1p(population_values), 5)), 6
                        ),
                        "p95_log1p_population": round(
                            float(np.percentile(np.log1p(population_values), 95)), 6
                        ),
                    },
                    "vulnerability_raw_bounds": {
                        "method": "AGE_COMPOSITION_VULNERABILITY_HEURISTIC",
                        "p05_weighted_age_share": round(
                            float(np.percentile(vulnerability_values, 5)), 6
                        ),
                        "p95_weighted_age_share": round(
                            float(np.percentile(vulnerability_values, 95)), 6
                        ),
                    },
                },
            },
            provenance=provenance,
            temporal_context=temporal_context,
            methods={
                "vulnerability": "AGE_COMPOSITION_VULNERABILITY_HEURISTIC",
                "adaptive_capacity": "VEGETATION_PROXY_HEURISTIC",
                "temporal_heat": "TEMPORAL_HEAT_CONTEXT_HEURISTIC",
                "hazard": "SPATIOTEMPORAL_HEAT_HAZARD_HEURISTIC",
                "risk": "TRANSPARENT_WEIGHTED_RISK_HEURISTIC",
            },
        )
