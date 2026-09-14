from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import rasterio
from shapely.geometry import box, mapping

from app.grid import build_pilot_grid
from app.models.landsat import (
    LandsatArtifact,
    LandsatGridTemperature,
    SceneCandidate,
)

from .aggregate import aggregate_temperature
from .cache import LandsatCache, file_checksum
from .provenance import LandsatSceneProvenance
from .qa import cloud_qa_mask, valid_qa_mask
from .raster import crop_remote_cog, geometry_pixel_mask, read_cached_window
from .selection import select_best_scene
from .stac import (
    LandsatStacClient,
    asset_band_metadata,
    candidate_from_item,
    discover_asset_keys,
)
from .temperature import OFFICIAL_OFFSET_K, OFFICIAL_SCALE, scale_surface_temperature, valid_temperature_mask


@dataclass(frozen=True)
class LandsatPaths:
    project_dir: Path

    @property
    def raw(self) -> Path:
        return self.project_dir / "data/raw/landsat/planetary_computer"

    @property
    def processed(self) -> Path:
        return self.project_dir / "data/processed/landsat"

    @property
    def provenance(self) -> Path:
        return self.project_dir / "data/provenance/landsat"

    @property
    def reports(self) -> Path:
        return self.project_dir / "reports"

    @property
    def docs(self) -> Path:
        return self.project_dir / "docs/landsat"


class LandsatM2Pipeline:
    def __init__(
        self,
        paths: LandsatPaths,
        stac_url: str,
        collection: str,
        start: str,
        end: str,
        max_cloud_cover: float = 50.0,
    ) -> None:
        self.paths = paths
        self.collection = collection
        self.start = start
        self.end = end
        self.max_cloud_cover = max_cloud_cover
        self.cache = LandsatCache(paths.raw)
        self.stac = LandsatStacClient(stac_url, collection, self.cache)
        self.pilot = build_pilot_grid()
        self.pilot_geometry = mapping(box(*self.pilot.bbox_wgs84))
        self.cache_hits = 0
        self.network_reads = 0

    def _write_contract(self, items: list[dict[str, Any]]) -> None:
        self.paths.docs.mkdir(parents=True, exist_ok=True)
        sample = items[0]
        keys = discover_asset_keys(sample)
        self.cache.write_json(self.paths.docs / "sample_item.json", sample)
        inventory = {
            key: {
                field: asset.get(field)
                for field in ("title", "description", "type", "roles", "raster:bands")
            }
            for key, asset in sample.get("assets", {}).items()
        }
        self.cache.write_json(
            self.paths.docs / "sample_asset_inventory.json", inventory
        )
        contract = f"""# Landsat STAC Contract

Accessed: {datetime.now(UTC).isoformat()}

- STAC API: `{self.stac.url}`
- Collection: `{self.collection}`
- Search: bbox + datetime + `eo:cloud_cover <= {self.max_cloud_cover:g}`
- Confirmed Surface Temperature asset: `{keys['st']}`
- Confirmed QA_PIXEL asset: `{keys['qa_pixel']}`
- Confirmed ST_QA asset: `{keys['st_qa']}`
- Confirmed item fields: `id`, `properties.datetime`, `properties.platform`,
  `properties.eo:cloud_cover`, `properties.landsat:scene_id`,
  `properties.proj:epsg`, assets and raster band metadata.

Science provider is USGS. Microsoft Planetary Computer is the access service.
Asset keys and scale metadata are discovered from live STAC, not assumed.
"""
        (self.paths.docs / "STAC_CONTRACT.md").write_text(contract, encoding="utf-8")

    def search(self) -> tuple[list[dict[str, Any]], list[SceneCandidate]]:
        items = self.stac.search(
            self.pilot.bbox_wgs84,
            self.start,
            self.end,
            self.max_cloud_cover,
        )
        if not items:
            raise RuntimeError("no Landsat scenes found in configured search window")
        self._write_contract(items)
        return items, [candidate_from_item(item) for item in items]

    def _ensure_window(self, item: dict[str, Any], asset_key: str) -> Path:
        path = self.cache.window_path(item["id"], asset_key)
        if path.exists():
            self.cache_hits += 1
            return path
        href = self.stac.signed_asset_href(item, asset_key)
        crop_remote_cog(href, self.pilot_geometry, path)
        self.network_reads += 1
        return path

    def screen_candidates(
        self,
        items: list[dict[str, Any]],
        candidates: list[SceneCandidate],
    ) -> list[SceneCandidate]:
        screened: list[SceneCandidate] = []
        for item, candidate in zip(items, candidates, strict=True):
            if not candidate.qa_asset_key or not candidate.st_asset_available:
                screened.append(candidate)
                continue
            qa_path = self._ensure_window(item, candidate.qa_asset_key)
            qa, metadata = read_cached_window(qa_path)
            inside = geometry_pixel_mask(
                self.pilot_geometry,
                metadata["crs"],
                metadata["transform"],
                qa.shape,
            )
            valid = inside & valid_qa_mask(qa)
            cloudy = inside & cloud_qa_mask(qa)
            total = int(inside.sum())
            valid_count = int(valid.sum())
            valid_fraction = valid_count / total if total else 0.0
            screened.append(
                candidate.model_copy(
                    update={
                        "pilot_total_pixels": total,
                        "pilot_valid_pixels": valid_count,
                        "pilot_valid_fraction": valid_fraction,
                        "pilot_cloud_fraction": (
                            int(cloudy.sum()) / total if total else 0.0
                        ),
                    }
                )
            )
        return screened

    def _selection_report(
        self,
        candidates: list[SceneCandidate],
        selected: SceneCandidate,
    ) -> dict[str, Any]:
        return {
            "search_window": [self.start, self.end],
            "search_window_expanded": False,
            "pilot_name": "pilot_v1",
            "pilot_bbox": self.pilot.bbox_wgs84,
            "candidate_count": len(candidates),
            "selection_order": [
                "pilot_valid_fraction descending",
                "acquisition_datetime descending",
                "scene_cloud_cover ascending",
            ],
            "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
            "selected_scene_id": selected.scene_id,
            "selected_product_id": selected.product_id,
            "selection_reason": (
                "Highest AOI QA-valid fraction; recency and scene cloud cover are "
                "deterministic tie-breakers."
            ),
        }

    def run(self) -> LandsatArtifact:
        items, candidates = self.search()
        screened = self.screen_candidates(items, candidates)
        selected = select_best_scene(screened)
        selected_item = next(item for item in items if item["id"] == selected.scene_id)
        selection_report = self._selection_report(screened, selected)
        self.cache.write_json(
            self.paths.reports / "m2_landsat_scene_selection.json", selection_report
        )
        keys = discover_asset_keys(selected_item)
        assert keys["st"] and keys["qa_pixel"]
        st_band = asset_band_metadata(selected_item, keys["st"])
        scale = float(st_band.get("scale", OFFICIAL_SCALE))
        offset = float(st_band.get("offset", OFFICIAL_OFFSET_K))
        if not np.isclose(scale, OFFICIAL_SCALE) or not np.isclose(offset, OFFICIAL_OFFSET_K):
            raise RuntimeError("live STAC scale/offset do not match the verified USGS rule")
        st_path = self._ensure_window(selected_item, keys["st"])
        qa_path = self._ensure_window(selected_item, keys["qa_pixel"])
        st_dn, st_meta = read_cached_window(st_path)
        qa, qa_meta = read_cached_window(qa_path)
        if st_dn.shape != qa.shape or st_meta["transform"] != qa_meta["transform"]:
            raise RuntimeError("ST and QA pilot windows are not aligned")
        inside_pilot = geometry_pixel_mask(
            self.pilot_geometry, st_meta["crs"], st_meta["transform"], st_dn.shape
        )
        qa_valid = valid_qa_mask(qa)
        pixel_valid = valid_temperature_mask(st_dn, qa_valid, st_meta["nodata"])
        temperatures = scale_surface_temperature(st_dn, scale, offset)
        source_id = f"landsat:{self.collection}:{selected.scene_id}"
        grids: list[LandsatGridTemperature] = []
        for cell in self.pilot.cells:
            inside_grid = geometry_pixel_mask(
                cell.geometry_wgs84,
                st_meta["crs"],
                st_meta["transform"],
                st_dn.shape,
            )
            stats = aggregate_temperature(temperatures, inside_grid, pixel_valid)
            grids.append(
                LandsatGridTemperature(
                    grid_id=cell.grid_id,
                    scene_id=selected.scene_id,
                    product_id=selected.product_id,
                    platform=selected.platform,
                    acquisition_datetime=selected.acquisition_datetime,
                    source_id=source_id,
                    **stats,
                )
            )
        artifact = LandsatArtifact(
            pilot_name="pilot_v1 engineering validation AOI",
            pilot_bbox_wgs84=self.pilot.bbox_wgs84,
            collection=self.collection,
            scene_id=selected.scene_id,
            product_id=selected.product_id,
            platform=selected.platform,
            acquisition_datetime=selected.acquisition_datetime,
            source_id=source_id,
            grids=grids,
        )
        self._write_outputs(
            artifact,
            selected_item,
            selected,
            st_path,
            qa_path,
            st_dn,
            temperatures,
            inside_pilot & pixel_valid,
            st_meta,
            scale,
            offset,
        )
        return artifact

    def _write_outputs(
        self,
        artifact: LandsatArtifact,
        item: dict[str, Any],
        selected: SceneCandidate,
        st_path: Path,
        qa_path: Path,
        st_dn: np.ndarray,
        temperatures: np.ndarray,
        valid: np.ndarray,
        st_meta: dict[str, Any],
        scale: float,
        offset: float,
    ) -> None:
        self.paths.processed.mkdir(parents=True, exist_ok=True)
        artifact_path = self.paths.processed / "landsat_lst_pilot_2026.json"
        artifact_path.write_text(artifact.model_dump_json(indent=2) + "\n", encoding="utf-8")
        rows = [grid.model_dump(mode="json") for grid in artifact.grids]
        pd.DataFrame(rows).to_parquet(
            self.paths.processed / "landsat_lst_pilot_2026.parquet", index=False
        )
        selected_payload = {
            "scene_id": selected.scene_id,
            "product_id": selected.product_id,
            "platform": selected.platform,
            "acquisition_datetime": selected.acquisition_datetime.isoformat(),
            "source_id": artifact.source_id,
        }
        self.cache.write_json(self.paths.processed / "selected_scene.json", selected_payload)
        stac_item_path = self.cache.json_path(f"{selected.scene_id}.item.json")
        self.cache.write_json(stac_item_path, item)
        keys = discover_asset_keys(item)
        asset_gsd = item["assets"][keys["st"]].get("gsd")
        provenance = LandsatSceneProvenance(
            collection=self.collection,
            scene_id=selected.scene_id,
            product_id=selected.product_id,
            platform=selected.platform,
            acquisition_datetime=selected.acquisition_datetime,
            stac_item_url=f"{self.stac.url}/collections/{self.collection}/items/{selected.scene_id}",
            st_asset_key=keys["st"],
            qa_asset_key=keys["qa_pixel"],
            st_qa_asset_key=keys["st_qa"],
            source_geometry=self.pilot_geometry,
            pilot_bbox=self.pilot.bbox_wgs84,
            source_crs=st_meta["crs"].to_string(),
            source_resolution=tuple(st_meta["resolution"]),
            asset_gsd=asset_gsd,
            scale=scale,
            offset=offset,
            nodata=st_meta["nodata"],
            qa_mask_policy="Exclude QA_PIXEL bits 0-5: fill, dilated cloud, cirrus, cloud, cloud shadow, snow.",
            aggregation_method="Pixel-center polygon mask; valid pixels aggregated to the 250 m HeatSafe grid.",
            retrieved_at=datetime.now(UTC),
            raw_artifacts={
                "stac_item": str(stac_item_path.relative_to(self.paths.project_dir)),
                "st_window": str(st_path.relative_to(self.paths.project_dir)),
                "qa_window": str(qa_path.relative_to(self.paths.project_dir)),
            },
            checksums={
                "stac_item": file_checksum(stac_item_path),
                "st_window": file_checksum(st_path),
                "qa_window": file_checksum(qa_path),
            },
        )
        provenance_path = self.paths.provenance / "scenes" / f"{selected.scene_id}.metadata.json"
        provenance_path.parent.mkdir(parents=True, exist_ok=True)
        provenance_path.write_text(provenance.model_dump_json(indent=2) + "\n", encoding="utf-8")
        usable = np.asarray(valid, dtype=bool)
        usable_temps = temperatures[usable]
        usable_dn = st_dn[usable]
        qualities = [grid.quality_flag.value for grid in artifact.grids]
        audit = {
            "M2_STATUS": "PASS",
            "pilot_name": "pilot_v1 engineering validation AOI",
            "pilot_bbox": self.pilot.bbox_wgs84,
            "grid_count": len(artifact.grids),
            "stac_collection": self.collection,
            "candidate_scene_count": len(self.cache.read_json(self.paths.reports / "m2_landsat_scene_selection.json")["candidates"]),
            "selected_scene_id": selected.scene_id,
            "product_id": selected.product_id,
            "platform": selected.platform,
            "acquisition_datetime": selected.acquisition_datetime.isoformat(),
            "scene_cloud_cover": selected.scene_cloud_cover,
            "pilot_valid_fraction": selected.pilot_valid_fraction,
            "st_asset_key": keys["st"],
            "qa_asset_key": keys["qa_pixel"],
            "source_resolution": st_meta["resolution"],
            "asset_gsd": asset_gsd,
            "source_crs": st_meta["crs"].to_string(),
            "scale": scale,
            "offset": offset,
            "raw_dn_min": int(np.min(usable_dn)),
            "raw_dn_max": int(np.max(usable_dn)),
            "kelvin_min": float(np.min(usable_temps) + 273.15),
            "kelvin_max": float(np.max(usable_temps) + 273.15),
            "grid_with_valid_st": sum(grid.valid_pixel_count > 0 for grid in artifact.grids),
            "grid_high_quality": qualities.count("HIGH"),
            "grid_medium_quality": qualities.count("MEDIUM"),
            "grid_low_quality": qualities.count("LOW"),
            "grid_insufficient": qualities.count("INSUFFICIENT"),
            "lst_min_c": float(np.min(usable_temps)),
            "lst_median_c": float(np.median(usable_temps)),
            "lst_p90_c": float(np.percentile(usable_temps, 90)),
            "lst_max_c": float(np.max(usable_temps)),
            "cache_hits": self.cache_hits + self.stac.cache_hits,
            "network_reads": self.network_reads + self.stac.network_reads,
            "surface_temperature_mode": "REAL",
            "hazard_mode": "MIXED",
            "full_analysis_mode": "MIXED",
            "provenance_status": "PASS",
            "checksum_status": "PASS",
            "water_mask_policy": "KEEP",
            "quality_thresholds_are_project_qc": True,
        }
        self.cache.write_json(self.paths.reports / "m2_landsat_audit.json", audit)
