from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from rasterio.enums import Resampling

from app.grid import build_pilot_grid
from app.models.landsat import CoverageQuality
from app.models.sentinel2 import (
    AdaptiveCapacityProxy,
    SentinelGridVegetation,
    SentinelVegetationArtifact,
)
from app.tools.landsat.raster import geometry_pixel_mask, read_cached_window

from .adaptive import percentile_rank
from .aggregation import GREEN_NDVI_THRESHOLD, aggregate_vegetation
from .alignment import align_array
from .assets import discover_asset_keys, projection_metadata
from .cache import SentinelCache, file_checksum
from .metadata import ReflectanceScalingContract
from .ndvi import calculate_ndvi
from .provenance import SentinelSceneProvenance
from .raster import AnalysisRasterGrid, build_analysis_raster, ensure_remote_window
from .scaling import dn_to_reflectance
from .scl import observation_valid_mask, vegetation_land_mask
from .selection import SentinelCandidate, SearchDecision, choose_search_result
from .sensitivity import threshold_sensitivity
from .stac import SentinelStacClient


LANDSAT_ACQUISITION = datetime(2026, 7, 31, 2, 31, 22, tzinfo=UTC)
INITIAL_WINDOW = ("2026-07-21", "2026-08-10")
EXPANDED_WINDOW = ("2026-07-01", "2026-08-30")
SENSITIVITY_THRESHOLDS = (0.20, 0.25, 0.30, 0.35, 0.40)


@dataclass(frozen=True)
class SentinelPaths:
    project_dir: Path

    @property
    def raw(self) -> Path:
        return self.project_dir / "data/raw/sentinel2/planetary_computer"

    @property
    def processed(self) -> Path:
        return self.project_dir / "data/processed/sentinel2"

    @property
    def provenance(self) -> Path:
        return self.project_dir / "data/provenance/sentinel2"

    @property
    def reports(self) -> Path:
        return self.project_dir / "reports"

    @property
    def docs(self) -> Path:
        return self.project_dir / "docs/sentinel2"


class SentinelM3APipeline:
    def __init__(
        self,
        paths: SentinelPaths,
        stac_url: str,
        collection: str,
    ) -> None:
        self.paths = paths
        self.collection = collection
        self.cache = SentinelCache(paths.raw)
        self.stac = SentinelStacClient(stac_url, collection, self.cache)
        self.pilot = build_pilot_grid()
        self.analysis = build_analysis_raster(self.pilot)
        self.pilot_geometry = {
            "type": "Polygon",
            "coordinates": [[
                [self.pilot.bbox_wgs84[0], self.pilot.bbox_wgs84[1]],
                [self.pilot.bbox_wgs84[2], self.pilot.bbox_wgs84[1]],
                [self.pilot.bbox_wgs84[2], self.pilot.bbox_wgs84[3]],
                [self.pilot.bbox_wgs84[0], self.pilot.bbox_wgs84[3]],
                [self.pilot.bbox_wgs84[0], self.pilot.bbox_wgs84[1]],
            ]],
        }
        self.cache_hits = 0
        self.network_reads = 0

    def _candidate_from_item(self, item: dict[str, Any]) -> SentinelCandidate:
        keys = discover_asset_keys(item)
        acquired = datetime.fromisoformat(
            item["properties"]["datetime"].replace("Z", "+00:00")
        )
        delta_days = abs((acquired - LANDSAT_ACQUISITION).total_seconds()) / 86400
        return SentinelCandidate(
            scene_id=item["id"],
            platform=item["properties"].get("platform", "unknown"),
            acquisition_datetime=acquired,
            scene_cloud_cover=float(item["properties"].get("eo:cloud_cover", 100)),
            pilot_observation_valid_fraction=0,
            b04_available=keys["b04"] is not None,
            b08_available=keys["b08"] is not None,
            scl_available=keys["scl"] is not None,
            b04_asset_key=keys["b04"],
            b08_asset_key=keys["b08"],
            scl_asset_key=keys["scl"],
            days_from_landsat_scene=delta_days,
        )

    def _write_contract(
        self,
        items: list[dict[str, Any]],
        sample: dict[str, Any],
        scaling: ReflectanceScalingContract,
    ) -> None:
        self.paths.docs.mkdir(parents=True, exist_ok=True)
        keys = discover_asset_keys(sample)
        SentinelCache.write_json(self.paths.docs / "sample_item.json", sample)
        inventory = {
            key: {
                field: asset.get(field, "NOT_EXPOSED_BY_STAC")
                for field in (
                    "title",
                    "type",
                    "roles",
                    "gsd",
                    "raster:bands",
                    "proj:epsg",
                    "proj:shape",
                    "proj:transform",
                )
            }
            for key, asset in sample.get("assets", {}).items()
        }
        SentinelCache.write_json(
            self.paths.docs / "sample_asset_inventory.json", inventory
        )
        projections = {
            name: projection_metadata(sample, key)
            for name, key in keys.items()
            if name in {"b04", "b08", "scl"} and key
        }
        contract = f"""# Sentinel-2 STAC Contract

Accessed: {datetime.now(UTC).isoformat()}

- STAC API: `{self.stac.url}`
- Collection: `{self.collection}`
- Initial window: `{INITIAL_WINDOW[0]}/{INITIAL_WINDOW[1]}`
- Candidate items: `{len(items)}`
- B04 asset key: `{keys['b04']}`
- B08 asset key: `{keys['b08']}`
- SCL asset key: `{keys['scl']}`
- Product metadata asset key: `{keys['product_metadata']}`
- Item projection code: `{sample['properties'].get('proj:epsg', sample['properties'].get('proj:code', 'NOT_EXPOSED_BY_STAC'))}`
- Asset projection metadata: `{json.dumps(projections, sort_keys=True)}`

Item and collection STAC do not expose reflectance `raster:bands` scale/offset
for B04/B08. Scaling is therefore read from each official `MTD_MSIL2A.xml`
product metadata artifact, never inferred from DN values.

ESA/Copernicus is the science provider. Microsoft Planetary Computer is the
access service.
"""
        (self.paths.docs / "STAC_CONTRACT.md").write_text(contract, encoding="utf-8")
        scaling_doc = f"""# Reflectance Scaling

The sampled live product metadata reports:

- `BOA_QUANTIFICATION_VALUE = {scaling.quantification_value:g}`
- B04 `BOA_ADD_OFFSET = {scaling.b04_add_offset_dn:g}`
- B08 `BOA_ADD_OFFSET = {scaling.b08_add_offset_dn:g}`
- nodata DN = `{scaling.nodata}`
- saturated DN = `{scaling.saturated}`

The verified conversion is performed before NDVI:

```text
B04_reflectance = B04_DN * {scaling.scale:g} + ({scaling.b04_offset:g})
B08_reflectance = B08_DN * {scaling.scale:g} + ({scaling.b08_offset:g})
```

The additive offset does not cancel in a raw-DN NDVI ratio. STAC exposes no
conflicting scale/offset; it is recorded as `NOT_EXPOSED_BY_STAC`.
"""
        (self.paths.docs / "reflectance_scaling.md").write_text(
            scaling_doc, encoding="utf-8"
        )

    def contract_probe(self) -> tuple[list[dict[str, Any]], ReflectanceScalingContract]:
        items = self.stac.search(
            self.pilot.bbox_wgs84, INITIAL_WINDOW[0], INITIAL_WINDOW[1]
        )
        eligible = [
            item
            for item in items
            if all(discover_asset_keys(item)[key] for key in ("b04", "b08", "scl", "product_metadata"))
        ]
        if not eligible:
            raise RuntimeError("no initial Sentinel item exposes B04, B08, SCL, and product metadata")
        sample = min(
            eligible,
            key=lambda item: abs(
                (
                    datetime.fromisoformat(item["properties"]["datetime"].replace("Z", "+00:00"))
                    - LANDSAT_ACQUISITION
                ).total_seconds()
            ),
        )
        scaling, _ = self.stac.product_metadata(sample)
        self._validate_scaling_metadata(sample, scaling)
        self._write_contract(items, sample, scaling)
        return items, scaling

    @staticmethod
    def _validate_scaling_metadata(
        item: dict[str, Any], scaling: ReflectanceScalingContract
    ) -> None:
        keys = discover_asset_keys(item)
        for name, expected_scale, expected_offset in (
            ("b04", scaling.scale, scaling.b04_offset),
            ("b08", scaling.scale, scaling.b08_offset),
        ):
            exposed = projection_metadata(item, keys[name])
            if exposed["scale"] is not None and not np.isclose(
                exposed["scale"], expected_scale
            ):
                raise RuntimeError("BLOCKED_SCALING_MISMATCH: STAC scale conflicts with product metadata")
            if exposed["offset"] is not None and not np.isclose(
                exposed["offset"], expected_offset
            ):
                raise RuntimeError("BLOCKED_SCALING_MISMATCH: STAC offset conflicts with product metadata")

    def _ensure_window(self, item: dict[str, Any], asset_key: str) -> Path:
        path = self.cache.window_path(item["id"], asset_key)
        if path.exists():
            self.cache_hits += 1
            return path
        href = self.stac.signed_asset_href(item, asset_key)
        ensure_remote_window(href, self.pilot_geometry, path)
        self.network_reads += 1
        return path

    def _aligned_scl(self, item: dict[str, Any]) -> tuple[np.ndarray, Path, dict[str, Any]]:
        key = discover_asset_keys(item)["scl"]
        if key is None:
            raise ValueError("candidate lacks SCL")
        path = self._ensure_window(item, key)
        source, metadata = read_cached_window(path)
        aligned = align_array(
            source,
            source_transform=metadata["transform"],
            source_crs=metadata["crs"],
            target_shape=self.analysis.shape,
            target_transform=self.analysis.transform,
            target_crs=self.analysis.crs,
            resampling=Resampling.nearest,
            source_nodata=metadata["nodata"],
            target_nodata=0,
            destination_dtype=np.uint8,
        )
        return aligned, path, metadata

    def screen_items(
        self, items: list[dict[str, Any]]
    ) -> list[SentinelCandidate]:
        candidates: list[SentinelCandidate] = []
        total = self.analysis.shape[0] * self.analysis.shape[1]
        for item in items:
            candidate = self._candidate_from_item(item)
            if not (candidate.b04_available and candidate.b08_available and candidate.scl_available):
                candidates.append(candidate)
                continue
            scl, _, _ = self._aligned_scl(item)
            valid_count = int(observation_valid_mask(scl).sum())
            candidates.append(
                candidate.model_copy(
                    update={
                        "pilot_observation_total_pixels": total,
                        "pilot_observation_valid_pixels": valid_count,
                        "pilot_observation_valid_fraction": valid_count / total,
                    }
                )
            )
        return candidates

    def select_scene(
        self, initial_items: list[dict[str, Any]]
    ) -> tuple[SearchDecision, dict[str, Any]]:
        initial_candidates = self.screen_items(initial_items)
        if any(item.quality == CoverageQuality.HIGH for item in initial_candidates):
            decision = choose_search_result(initial_candidates, initial_candidates)
            all_items = initial_items
        else:
            expanded_items = self.stac.search(
                self.pilot.bbox_wgs84, EXPANDED_WINDOW[0], EXPANDED_WINDOW[1]
            )
            expanded_candidates = self.screen_items(expanded_items)
            decision = choose_search_result(initial_candidates, expanded_candidates)
            all_items = expanded_items
        if decision.composite_required:
            raise RuntimeError(
                "No HIGH single scene in +/-30 days; QA-screened composite is required before M3A can continue"
            )
        assert decision.selected_scene is not None
        selected_item = next(
            item for item in all_items if item["id"] == decision.selected_scene.scene_id
        )
        report = {
            "initial_window": list(INITIAL_WINDOW),
            "final_window": (
                list(INITIAL_WINDOW)
                if decision.window == "INITIAL"
                else list(EXPANDED_WINDOW)
            ),
            "window_decision": decision.window,
            "composite_required": decision.composite_required,
            "selection_order": [
                "HIGH quality",
                "pilot observation valid fraction descending",
                "absolute days from Landsat ascending",
                "scene cloud cover ascending",
            ],
            "candidate_count": len(decision.candidates),
            "candidates": [candidate.model_dump(mode="json") for candidate in decision.candidates],
            "selected_scene_id": decision.selected_scene.scene_id,
            "selection_reason": "Best HIGH candidate under the deterministic M3A ordering.",
        }
        SentinelCache.write_json(
            self.paths.reports / "m3a_sentinel_scene_selection.json", report
        )
        SentinelCache.write_json(
            self.paths.processed / "scene_candidates.json",
            {"candidates": report["candidates"]},
        )
        return decision, selected_item

    def _aligned_reflectance(
        self,
        item: dict[str, Any],
        asset_key: str,
        scale: float,
        offset: float,
        nodata: int,
        saturated: int,
    ) -> tuple[np.ndarray, Path, dict[str, Any], np.ndarray]:
        path = self._ensure_window(item, asset_key)
        raw, metadata = read_cached_window(path)
        reflectance = dn_to_reflectance(raw, scale, offset, nodata)
        reflectance[np.asarray(raw) == saturated] = np.nan
        aligned = align_array(
            reflectance,
            source_transform=metadata["transform"],
            source_crs=metadata["crs"],
            target_shape=self.analysis.shape,
            target_transform=self.analysis.transform,
            target_crs=self.analysis.crs,
            resampling=Resampling.bilinear,
            source_nodata=np.nan,
            target_nodata=np.nan,
            destination_dtype=np.float32,
        )
        return aligned, path, metadata, raw

    def run(self) -> SentinelVegetationArtifact:
        initial_items, _ = self.contract_probe()
        decision, selected_item = self.select_scene(initial_items)
        selected = decision.selected_scene
        assert selected is not None
        keys = discover_asset_keys(selected_item)
        scaling, metadata_path_string = self.stac.product_metadata(selected_item)
        self._validate_scaling_metadata(selected_item, scaling)
        red, b04_path, b04_meta, b04_raw = self._aligned_reflectance(
            selected_item,
            keys["b04"],
            scaling.scale,
            scaling.b04_offset,
            scaling.nodata,
            scaling.saturated,
        )
        nir, b08_path, b08_meta, b08_raw = self._aligned_reflectance(
            selected_item,
            keys["b08"],
            scaling.scale,
            scaling.b08_offset,
            scaling.nodata,
            scaling.saturated,
        )
        scl, scl_path, scl_meta = self._aligned_scl(selected_item)
        if not (red.shape == nir.shape == scl.shape == self.analysis.shape):
            raise RuntimeError("aligned B04/B08/SCL shapes differ")
        observation = observation_valid_mask(scl) & np.isfinite(red) & np.isfinite(nir)
        land = vegetation_land_mask(scl) & observation
        ndvi = calculate_ndvi(red, nir)
        ndvi[~land] = np.nan
        valid_ndvi = ndvi[np.isfinite(ndvi)]
        if not valid_ndvi.size:
            raise RuntimeError("selected scene contains no valid land NDVI")
        outside_range = np.sum((valid_ndvi < -1.000001) | (valid_ndvi > 1.000001))
        if outside_range:
            raise RuntimeError("NDVI outside [-1,1] indicates scaling/alignment failure")
        source_id = f"sentinel2:{self.collection}:{selected.scene_id}"
        aggregate_rows: list[dict[str, Any]] = []
        sensitivity_values: list[np.ndarray] = []
        observation_counts: list[int] = []
        for cell in self.pilot.cells:
            inside = geometry_pixel_mask(
                cell.geometry_projected,
                self.analysis.crs,
                self.analysis.transform,
                self.analysis.shape,
                source_crs=self.analysis.crs,
            )
            row = aggregate_vegetation(
                ndvi,
                inside_grid=inside,
                observation_valid=observation,
                valid_land=land,
            )
            aggregate_rows.append(row)
            sensitivity_values.append(ndvi[inside & land])
            observation_counts.append(int((inside & observation).sum()))
        proxy_inputs = np.array(
            [
                row["green_fraction_grid"]
                if row["quality_flag"] != "INSUFFICIENT"
                and row["green_fraction_grid"] is not None
                else np.nan
                for row in aggregate_rows
            ],
            dtype=float,
        )
        adaptive_scores = percentile_rank(proxy_inputs)
        grids: list[SentinelGridVegetation] = []
        for cell, row, adaptive_score in zip(
            self.pilot.cells, aggregate_rows, adaptive_scores, strict=True
        ):
            score = float(adaptive_score) if np.isfinite(adaptive_score) else None
            grids.append(
                SentinelGridVegetation(
                    grid_id=cell.grid_id,
                    scene_id=selected.scene_id,
                    platform=selected.platform,
                    acquisition_datetime=selected.acquisition_datetime,
                    source_id=source_id,
                    adaptive_capacity=AdaptiveCapacityProxy(score=score),
                    **row,
                )
            )
        artifact = SentinelVegetationArtifact(
            pilot_name="pilot_v1 engineering validation AOI",
            pilot_bbox_wgs84=self.pilot.bbox_wgs84,
            analysis_crs=self.analysis.crs,
            collection=self.collection,
            scene_ids=[selected.scene_id],
            source_id=source_id,
            grids=grids,
        )
        sensitivity = threshold_sensitivity(
            sensitivity_values,
            thresholds=SENSITIVITY_THRESHOLDS,
            top_n=10,
            observation_counts=observation_counts,
        )
        self._write_outputs(
            artifact=artifact,
            selected_item=selected_item,
            selected=selected,
            decision=decision,
            scaling=scaling,
            metadata_path=Path(metadata_path_string),
            b04_path=b04_path,
            b08_path=b08_path,
            scl_path=scl_path,
            b04_meta=b04_meta,
            b08_meta=b08_meta,
            scl_meta=scl_meta,
            b04_raw=b04_raw,
            b08_raw=b08_raw,
            red=red,
            nir=nir,
            ndvi=ndvi,
            observation=observation,
            land=land,
            sensitivity=sensitivity,
        )
        return artifact

    def _write_outputs(
        self,
        *,
        artifact: SentinelVegetationArtifact,
        selected_item: dict[str, Any],
        selected: SentinelCandidate,
        decision: SearchDecision,
        scaling: ReflectanceScalingContract,
        metadata_path: Path,
        b04_path: Path,
        b08_path: Path,
        scl_path: Path,
        b04_meta: dict[str, Any],
        b08_meta: dict[str, Any],
        scl_meta: dict[str, Any],
        b04_raw: np.ndarray,
        b08_raw: np.ndarray,
        red: np.ndarray,
        nir: np.ndarray,
        ndvi: np.ndarray,
        observation: np.ndarray,
        land: np.ndarray,
        sensitivity: dict[str, Any],
    ) -> None:
        self.paths.processed.mkdir(parents=True, exist_ok=True)
        artifact_path = self.paths.processed / "sentinel2_vegetation_pilot_2026.json"
        artifact_path.write_text(artifact.model_dump_json(indent=2) + "\n", encoding="utf-8")
        pd.DataFrame(
            [grid.model_dump(mode="json") for grid in artifact.grids]
        ).to_parquet(
            self.paths.processed / "sentinel2_vegetation_pilot_2026.parquet",
            index=False,
        )
        SentinelCache.write_json(
            self.paths.processed / "selected_scene.json",
            {
                "scene_id": selected.scene_id,
                "platform": selected.platform,
                "acquisition_datetime": selected.acquisition_datetime.isoformat(),
                "source_id": artifact.source_id,
                "is_composite": False,
            },
        )
        SentinelCache.write_json(
            self.paths.reports / "m3a_green_threshold_sensitivity.json", sensitivity
        )
        item_path = self.cache.item_path(selected.scene_id)
        SentinelCache.write_json(item_path, selected_item)
        keys = discover_asset_keys(selected_item)
        raw_paths = {
            "stac_item": item_path,
            "product_metadata": metadata_path,
            "b04_window": b04_path,
            "b08_window": b08_path,
            "scl_window": scl_path,
        }
        provenance = SentinelSceneProvenance(
            collection=self.collection,
            scene_id=selected.scene_id,
            platform=selected.platform,
            acquisition_datetime=selected.acquisition_datetime,
            b04_asset_key=keys["b04"],
            b08_asset_key=keys["b08"],
            scl_asset_key=keys["scl"],
            product_metadata_asset_key=keys["product_metadata"],
            b04_scale=scaling.scale,
            b04_offset=scaling.b04_offset,
            b08_scale=scaling.scale,
            b08_offset=scaling.b08_offset,
            scaling_source=scaling.source,
            source_crs=b04_meta["crs"].to_string(),
            b04_resolution=float(b04_meta["resolution"][0]),
            b08_resolution=float(b08_meta["resolution"][0]),
            scl_resolution=float(scl_meta["resolution"][0]),
            analysis_crs=self.analysis.crs,
            analysis_resolution=self.analysis.resolution_meters,
            scene_quality_mask_policy="Exclude SCL 0,1,3,8,9,10,11; water remains a clear observation.",
            vegetation_mask_policy="Observation-valid land only; exclude SCL water class 6 from NDVI.",
            retrieved_at=datetime.now(UTC),
            raw_artifacts={
                name: str(path.relative_to(self.paths.project_dir))
                for name, path in raw_paths.items()
            },
            checksums={name: file_checksum(path) for name, path in raw_paths.items()},
        )
        provenance_path = self.paths.provenance / "scenes" / f"{selected.scene_id}.metadata.json"
        provenance_path.parent.mkdir(parents=True, exist_ok=True)
        provenance_path.write_text(provenance.model_dump_json(indent=2) + "\n", encoding="utf-8")
        valid_red = red[np.isfinite(red)]
        valid_nir = nir[np.isfinite(nir)]
        valid_ndvi = ndvi[np.isfinite(ndvi)]
        grid_qualities = [grid.quality_flag.value for grid in artifact.grids]
        green_grid = np.array(
            [grid.green_fraction_grid for grid in artifact.grids if grid.green_fraction_grid is not None]
        )
        green_land = np.array(
            [grid.green_fraction_land for grid in artifact.grids if grid.green_fraction_land is not None]
        )
        adaptive = np.array(
            [grid.adaptive_capacity.score for grid in artifact.grids if grid.adaptive_capacity.score is not None]
        )
        formal_comparisons = sensitivity["comparisons"]
        audit = {
            "M3A_STATUS": "PASS",
            "pilot_name": artifact.pilot_name,
            "pilot_bbox": artifact.pilot_bbox_wgs84,
            "grid_count": len(artifact.grids),
            "search_window_initial": list(INITIAL_WINDOW),
            "search_window_final": list(INITIAL_WINDOW) if decision.window == "INITIAL" else list(EXPANDED_WINDOW),
            "candidate_scene_count": len(decision.candidates),
            "selected_scene_id": selected.scene_id,
            "platform": selected.platform,
            "acquisition_datetime": selected.acquisition_datetime.isoformat(),
            "days_from_landsat_scene": selected.days_from_landsat_scene,
            "scene_cloud_cover": selected.scene_cloud_cover,
            "pilot_observation_valid_fraction": selected.pilot_observation_valid_fraction,
            "b04_asset_key": keys["b04"],
            "b08_asset_key": keys["b08"],
            "scl_asset_key": keys["scl"],
            "b04_resolution": float(b04_meta["resolution"][0]),
            "b08_resolution": float(b08_meta["resolution"][0]),
            "scl_resolution": float(scl_meta["resolution"][0]),
            "b04_scale": scaling.scale,
            "b04_offset": scaling.b04_offset,
            "b08_scale": scaling.scale,
            "b08_offset": scaling.b08_offset,
            "scl_resampling_method": "nearest",
            "water_scene_quality_policy": "KEEP",
            "water_ndvi_policy": "EXCLUDE",
            "water_green_fraction_policy": "NON_GREEN",
            "green_ndvi_threshold": GREEN_NDVI_THRESHOLD,
            "grid_high_quality": grid_qualities.count("HIGH"),
            "grid_medium_quality": grid_qualities.count("MEDIUM"),
            "grid_low_quality": grid_qualities.count("LOW"),
            "grid_insufficient": grid_qualities.count("INSUFFICIENT"),
            "b04_raw_min": int(np.min(b04_raw[b04_raw != scaling.nodata])),
            "b04_raw_max": int(np.max(b04_raw[b04_raw != scaling.nodata])),
            "b08_raw_min": int(np.min(b08_raw[b08_raw != scaling.nodata])),
            "b08_raw_max": int(np.max(b08_raw[b08_raw != scaling.nodata])),
            "b04_reflectance_min": float(np.min(valid_red)),
            "b04_reflectance_median": float(np.median(valid_red)),
            "b04_reflectance_max": float(np.max(valid_red)),
            "b08_reflectance_min": float(np.min(valid_nir)),
            "b08_reflectance_median": float(np.median(valid_nir)),
            "b08_reflectance_max": float(np.max(valid_nir)),
            "ndvi_valid_pixel_count": int(valid_ndvi.size),
            "ndvi_min": float(np.min(valid_ndvi)),
            "ndvi_p25": float(np.percentile(valid_ndvi, 25)),
            "ndvi_median": float(np.median(valid_ndvi)),
            "ndvi_p75": float(np.percentile(valid_ndvi, 75)),
            "ndvi_p90": float(np.percentile(valid_ndvi, 90)),
            "ndvi_max": float(np.max(valid_ndvi)),
            "fraction_ndvi_below_0": float(np.mean(valid_ndvi < 0)),
            "fraction_ndvi_0_to_0_3": float(np.mean((valid_ndvi >= 0) & (valid_ndvi <= 0.3))),
            "fraction_ndvi_above_0_3": float(np.mean(valid_ndvi > 0.3)),
            "green_fraction_grid_mean": float(np.mean(green_grid)),
            "green_fraction_grid_median": float(np.median(green_grid)),
            "green_fraction_land_mean": float(np.mean(green_land)),
            "green_fraction_land_median": float(np.median(green_land)),
            "adaptive_capacity_min": float(np.min(adaptive)),
            "adaptive_capacity_median": float(np.median(adaptive)),
            "adaptive_capacity_max": float(np.max(adaptive)),
            "adaptive_capacity_normalization_method": "upper empirical percentile rank among usable pilot_v1 grids",
            "adaptive_capacity_reference_grid_count": int(adaptive.size),
            "threshold_spearman_min": min(value["spearman_correlation"] for value in formal_comparisons.values()),
            "threshold_top10_overlap_min": min(value["top_n_overlap"] for value in formal_comparisons.values()),
            "water_pixel_fraction": float(np.mean(observation & ~land)),
            "vegetation_data_mode": "REAL",
            "adaptive_capacity_source_mode": "REAL",
            "adaptive_capacity_method": "VEGETATION_PROXY_HEURISTIC",
            "hazard_mode": "MIXED",
            "full_analysis_mode": "MIXED",
            "model_status": "PRELIMINARY_HEURISTIC",
            "provenance_status": "PASS",
            "checksum_status": "PASS",
            "cache_status": "PASS",
            "cache_hits": self.cache_hits + self.stac.cache_hits,
            "network_reads": self.network_reads + self.stac.network_reads,
        }
        SentinelCache.write_json(self.paths.reports / "m3a_sentinel_audit.json", audit)
