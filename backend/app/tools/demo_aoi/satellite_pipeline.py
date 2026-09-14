from __future__ import annotations

import json
import warnings
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from affine import Affine
from pyproj import CRS, Transformer
from pydantic import BaseModel, ConfigDict
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.windows import Window, from_bounds
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

from app.config import settings
from app.models.landsat import CoverageQuality
from app.tools.landsat.aggregate import aggregate_temperature
from app.tools.landsat.qa import valid_qa_mask
from app.tools.landsat.raster import crop_remote_cog, read_cached_window, transform_geometry
from app.tools.landsat.stac import (
    LandsatStacClient,
    asset_band_metadata,
    discover_asset_keys as discover_landsat_assets,
)
from app.tools.landsat.temperature import (
    OFFICIAL_OFFSET_K,
    OFFICIAL_SCALE,
    scale_surface_temperature,
    valid_temperature_mask,
)
from app.tools.sentinel2.aggregation import aggregate_vegetation
from app.tools.sentinel2.alignment import align_array
from app.tools.sentinel2.assets import discover_asset_keys as discover_sentinel_assets
from app.tools.sentinel2.cache import SentinelCache
from app.tools.sentinel2.ndvi import calculate_ndvi
from app.tools.sentinel2.pipeline import SentinelM3APipeline
from app.tools.sentinel2.raster import AnalysisRasterGrid
from app.tools.sentinel2.scaling import dn_to_reflectance
from app.tools.sentinel2.scl import observation_valid_mask, vegetation_land_mask, water_mask
from app.tools.sentinel2.stac import SentinelStacClient
from app.tools.source_hash_audit import audit_frozen_source_hashes

from .cache import M4BSatelliteCache, PROCESSING_CONTRACT, checksum
from .geometry import (
    DemoAOICandidate,
    DemoAOISearchGeometry,
    build_refinement_candidates,
    build_search_geometry,
    build_temporary_analysis_cells,
    deduplicate_candidates,
)
from .satellite import (
    LandsatCandidateMetrics,
    SatelliteScreeningResult,
    SentinelCandidateMetrics,
    candidate_valid_fraction,
    finite_quantiles,
    green_saturation_fraction,
    rank_satellite_candidates,
    select_satellite_top8,
    select_top_base_for_refinement,
)


LANDSAT_QA_GATE = 0.90
SENTINEL_QA_GATE = 0.90
WATER_GATE = 0.25
HIGH_OBSERVATION_GATE = 0.80
SENTINEL_RESOLUTION_M = 10


@dataclass(frozen=True)
class SentinelItemRaster:
    item: dict[str, Any]
    acquisition: datetime
    scl: np.ndarray
    footprint_projected: Any


@dataclass(frozen=True)
class SentinelChoice:
    method: str
    items: tuple[dict[str, Any], ...]
    acquisition_times: tuple[datetime, ...]
    valid_fraction: float


@dataclass(frozen=True)
class PreparedVegetation:
    ndvi: np.ndarray
    observation: np.ndarray
    land: np.ndarray
    water: np.ndarray


class SatellitePipelineInputs(BaseModel):
    """No population, hazard, or risk field is accepted by the selection path."""

    model_config = ConfigDict(extra="forbid")

    m4a_event_path: Path
    geometry_path: Path


def sentinel_search_windows(acquisition: datetime) -> dict[str, tuple[str, str]]:
    date = acquisition.astimezone(UTC).date()
    return {
        "initial": (
            (date - timedelta(days=10)).isoformat(),
            (date + timedelta(days=10)).isoformat(),
        ),
        "extended": (
            (date - timedelta(days=30)).isoformat(),
            (date + timedelta(days=30)).isoformat(),
        ),
    }


def scene_coverage_fraction(
    candidate: DemoAOICandidate, scene_geometry_wgs84: dict[str, Any]
) -> float:
    transformer = Transformer.from_crs(
        "EPSG:4326", candidate.projected_crs, always_xy=True
    )
    footprint = transform(transformer.transform, shape(scene_geometry_wgs84))
    polygon = shape(candidate.geometry_projected)
    return float(polygon.intersection(footprint).area / polygon.area)


def _local_geometry_mask(
    geometry: dict[str, Any],
    *,
    geometry_crs: str,
    raster_crs: Any,
    raster_transform: Affine,
    raster_shape: tuple[int, int],
) -> tuple[tuple[slice, slice], np.ndarray]:
    source = _cached_crs(str(geometry_crs))
    target = _cached_crs(str(raster_crs))
    if source.equals(target):
        projected = geometry
    else:
        transformer = _cached_transformer(source.srs, target.srs)
        projected = mapping(transform(transformer.transform, shape(geometry)))
    bounds = shape(projected).bounds
    raw = from_bounds(*bounds, transform=raster_transform)
    row_start = max(0, int(np.floor(raw.row_off)))
    column_start = max(0, int(np.floor(raw.col_off)))
    row_stop = min(raster_shape[0], int(np.ceil(raw.row_off + raw.height)))
    column_stop = min(raster_shape[1], int(np.ceil(raw.col_off + raw.width)))
    if row_stop <= row_start or column_stop <= column_start:
        return (slice(0, 0), slice(0, 0)), np.zeros((0, 0), dtype=bool)
    window = Window(
        column_start,
        row_start,
        column_stop - column_start,
        row_stop - row_start,
    )
    local_transform = raster_transform * Affine.translation(
        window.col_off, window.row_off
    )
    mask = geometry_mask(
        [projected],
        out_shape=(row_stop - row_start, column_stop - column_start),
        transform=local_transform,
        invert=True,
        all_touched=False,
    )
    return (slice(row_start, row_stop), slice(column_start, column_stop)), mask


@lru_cache(maxsize=16)
def _cached_transformer(source_crs: str, target_crs: str) -> Transformer:
    return Transformer.from_crs(source_crs, target_crs, always_xy=True)


@lru_cache(maxsize=16)
def _cached_crs(crs: str) -> CRS:
    return CRS.from_user_input(crs)


def _analysis_raster(search: DemoAOISearchGeometry) -> AnalysisRasterGrid:
    west, south, east, north = search.bounds_projected
    return AnalysisRasterGrid(
        crs=search.projected_crs,
        transform=from_origin(west, north, SENTINEL_RESOLUTION_M, SENTINEL_RESOLUTION_M),
        shape=(
            round((north - south) / SENTINEL_RESOLUTION_M),
            round((east - west) / SENTINEL_RESOLUTION_M),
        ),
        resolution_meters=SENTINEL_RESOLUTION_M,
        bounds=search.bounds_projected,
    )


class M4BSatellitePipeline:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.search = build_search_geometry()
        self.analysis = _analysis_raster(self.search)
        self.cache = M4BSatelliteCache(
            project_dir / "data/raw/demo_aoi_selection/satellite"
        )
        sentinel_cache = SentinelCache(project_dir / "data/raw/sentinel2/planetary_computer")
        self.sentinel_stac = SentinelStacClient(
            settings.sentinel_stac_url, settings.sentinel_collection, sentinel_cache
        )
        self.sentinel_item_rasters: dict[str, SentinelItemRaster] = {}
        self.prepared_vegetation: dict[tuple[str, ...], PreparedVegetation] = {}
        self.landsat_arrays: tuple[np.ndarray, np.ndarray, dict[str, Any]] | None = None
        self.landsat_item: dict[str, Any] | None = None
        self.event: dict[str, Any] = {}
        self.sentinel_windows: dict[str, tuple[str, str]] = {}
        self.extended_window_used = False
        self.initial_sentinel_items: list[dict[str, Any]] = []
        self.extended_sentinel_items: list[dict[str, Any]] = []

    def _load_event(self) -> None:
        event_path = (
            self.project_dir
            / "data/processed/event_selection/m4a_selected_event_2026.json"
        )
        self.event = json.loads(event_path.read_text(encoding="utf-8"))
        scene_id = self.event["scene_id"]
        item_path = (
            self.project_dir
            / f"data/raw/landsat/planetary_computer/stac/{scene_id}.item.json"
        )
        if not item_path.exists():
            raise RuntimeError("M4A selected Landsat STAC item is unavailable")
        self.landsat_item = json.loads(item_path.read_text(encoding="utf-8"))
        if self.landsat_item["id"] != scene_id:
            raise RuntimeError("M4A event and cached Landsat item identities differ")
        acquisition = datetime.fromisoformat(
            self.event["landsat_acquisition_time"].replace("Z", "+00:00")
        )
        self.sentinel_windows = sentinel_search_windows(acquisition)

    def _ensure_window(
        self,
        provider: str,
        item: dict[str, Any],
        asset_key: str,
        href: Callable[[], str],
    ) -> Path:
        return self.cache.ensure_window(
            provider,
            item["id"],
            asset_key,
            self.search.bounds_projected,
            lambda path: crop_remote_cog(
                href(), self.search.geometry_wgs84, path
            ),
        )

    def _prepare_landsat(self) -> None:
        assert self.landsat_item is not None
        keys = discover_landsat_assets(self.landsat_item)
        if not keys["st"] or not keys["qa_pixel"]:
            raise RuntimeError("M4A selected Landsat scene lacks ST or QA_PIXEL")
        band = asset_band_metadata(self.landsat_item, keys["st"])
        scale = float(band.get("scale", OFFICIAL_SCALE))
        offset = float(band.get("offset", OFFICIAL_OFFSET_K))
        if not np.isclose(scale, OFFICIAL_SCALE) or not np.isclose(
            offset, OFFICIAL_OFFSET_K
        ):
            raise RuntimeError("selected Landsat scaling differs from M2 contract")
        client = LandsatStacClient(
            settings.landsat_stac_url,
            settings.landsat_collection,
            # Signing does not use the cache object.
            cache=None,  # type: ignore[arg-type]
        )
        paths = []
        for asset_key in (keys["st"], keys["qa_pixel"]):
            paths.append(
                self._ensure_window(
                    "landsat",
                    self.landsat_item,
                    asset_key,
                    lambda asset_key=asset_key: client.signed_asset_href(
                        self.landsat_item, asset_key
                    ),
                )
            )
        st_dn, st_meta = read_cached_window(paths[0])
        qa, qa_meta = read_cached_window(paths[1])
        if st_dn.shape != qa.shape or st_meta["transform"] != qa_meta["transform"]:
            raise RuntimeError("M4B Landsat ST and QA windows are not aligned")
        valid = valid_temperature_mask(
            st_dn, valid_qa_mask(qa), st_meta["nodata"]
        )
        self.landsat_arrays = (
            scale_surface_temperature(st_dn, scale, offset),
            valid,
            st_meta,
        )

    def _screen_landsat(self, candidate: DemoAOICandidate) -> LandsatCandidateMetrics:
        assert self.landsat_item is not None and self.landsat_arrays is not None
        temperatures, valid, metadata = self.landsat_arrays
        coverage = scene_coverage_fraction(candidate, self.landsat_item["geometry"])
        qualities: list[str] = []
        medians: list[float | None] = []
        for cell in build_temporary_analysis_cells(candidate):
            slices, inside = _local_geometry_mask(
                cell.geometry_projected,
                geometry_crs=candidate.projected_crs,
                raster_crs=metadata["crs"],
                raster_transform=metadata["transform"],
                raster_shape=temperatures.shape,
            )
            stats = aggregate_temperature(
                temperatures[slices], inside, valid[slices]
            )
            qualities.append(str(stats["quality_flag"]))
            medians.append(stats["lst_median_c"])
        valid_fraction = candidate_valid_fraction(qualities)
        quantiles = finite_quantiles(medians)
        reasons = []
        if coverage < 0.999:
            reasons.append("LANDSAT_OUTSIDE_SCENE")
        if valid_fraction < LANDSAT_QA_GATE:
            reasons.append("LOW_LANDSAT_QA")
        if quantiles["p10"] is None or quantiles["p90"] is None:
            reasons.append("LANDSAT_METRICS_NOT_FINITE")
        counts = {quality: qualities.count(quality) for quality in CoverageQuality}
        return LandsatCandidateMetrics(
            scene_id=self.event["scene_id"],
            acquisition_time=self.event["landsat_acquisition_time"],
            scene_coverage_fraction=coverage,
            valid_fraction=valid_fraction,
            high_quality_cell_count=counts[CoverageQuality.HIGH],
            medium_quality_cell_count=counts[CoverageQuality.MEDIUM],
            low_quality_cell_count=counts[CoverageQuality.LOW],
            insufficient_cell_count=counts[CoverageQuality.INSUFFICIENT],
            lst_candidate_median_c=quantiles["p50"],
            lst_p10_c=quantiles["p10"],
            lst_p25_c=quantiles["p25"],
            lst_p50_c=quantiles["p50"],
            lst_p75_c=quantiles["p75"],
            lst_p90_c=quantiles["p90"],
            lst_iqr_c=(
                None
                if quantiles["p25"] is None or quantiles["p75"] is None
                else quantiles["p75"] - quantiles["p25"]
            ),
            lst_p90_p10_spread_c=(
                None
                if quantiles["p10"] is None or quantiles["p90"] is None
                else quantiles["p90"] - quantiles["p10"]
            ),
            eligible=not reasons,
            rejection_reasons=reasons,
        )

    def _sentinel_items(self, window: str) -> list[dict[str, Any]]:
        start, end = self.sentinel_windows[window]
        items = self.sentinel_stac.search(self.search.bbox_wgs84, start, end)
        return [
            item
            for item in items
            if all(
                discover_sentinel_assets(item)[key]
                for key in ("b04", "b08", "scl", "product_metadata")
            )
        ]

    def _load_scl_item(self, item: dict[str, Any]) -> SentinelItemRaster:
        cached = self.sentinel_item_rasters.get(item["id"])
        if cached is not None:
            return cached
        key = discover_sentinel_assets(item)["scl"]
        assert key is not None
        path = self._ensure_window(
            "sentinel",
            item,
            key,
            lambda: self.sentinel_stac.signed_asset_href(item, key),
        )
        values, metadata = read_cached_window(path)
        aligned = align_array(
            values,
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
        transformer = Transformer.from_crs(
            "EPSG:4326", self.search.projected_crs, always_xy=True
        )
        result = SentinelItemRaster(
            item=item,
            acquisition=datetime.fromisoformat(
                item["properties"]["datetime"].replace("Z", "+00:00")
            ),
            scl=aligned,
            footprint_projected=transform(
                transformer.transform, shape(item["geometry"])
            ),
        )
        self.sentinel_item_rasters[item["id"]] = result
        return result

    def _candidate_array(self, array: np.ndarray, candidate: DemoAOICandidate) -> np.ndarray:
        slices, inside = _local_geometry_mask(
            candidate.geometry_projected,
            geometry_crs=candidate.projected_crs,
            raster_crs=self.analysis.crs,
            raster_transform=self.analysis.transform,
            raster_shape=self.analysis.shape,
        )
        values = array[slices]
        result = np.zeros(values.shape, dtype=values.dtype)
        result[inside] = values[inside]
        return result

    @staticmethod
    def _group_by_acquisition(
        rasters: list[SentinelItemRaster],
    ) -> list[list[SentinelItemRaster]]:
        groups: dict[str, list[SentinelItemRaster]] = defaultdict(list)
        for raster in rasters:
            key = raster.acquisition.isoformat()
            groups[key].append(raster)
        return [sorted(groups[key], key=lambda value: value.item["id"]) for key in sorted(groups)]

    def _choice_from_items(
        self,
        candidate: DemoAOICandidate,
        items: list[dict[str, Any]],
        *,
        extended: bool,
    ) -> SentinelChoice | None:
        rasters = [self._load_scl_item(item) for item in items]
        polygon = shape(candidate.geometry_projected)
        acquisition = datetime.fromisoformat(
            self.event["landsat_acquisition_time"].replace("Z", "+00:00")
        )
        singles = []
        for raster in rasters:
            coverage = polygon.intersection(raster.footprint_projected).area / polygon.area
            local = self._candidate_array(raster.scl, candidate)
            valid = float(np.mean(observation_valid_mask(local)))
            if coverage >= 0.999 and valid >= HIGH_OBSERVATION_GATE:
                singles.append((raster, valid))
        if singles:
            selected, valid = sorted(
                singles,
                key=lambda pair: (
                    -pair[1],
                    abs((pair[0].acquisition - acquisition).total_seconds()),
                    float(pair[0].item["properties"].get("eo:cloud_cover", 100)),
                    pair[0].item["id"],
                ),
            )[0]
            return SentinelChoice(
                method=(
                    "EXTENDED_WINDOW_SINGLE_SCENE" if extended else "SINGLE_SCENE"
                ),
                items=(selected.item,),
                acquisition_times=(selected.acquisition,),
                valid_fraction=valid,
            )
        mosaics = []
        for group in self._group_by_acquisition(rasters):
            union = unary_union([raster.footprint_projected for raster in group])
            coverage = polygon.intersection(union).area / polygon.area
            mosaic = np.zeros(self.analysis.shape, dtype=np.uint8)
            for raster in group:
                take = (mosaic == 0) & (raster.scl != 0)
                mosaic[take] = raster.scl[take]
            local = self._candidate_array(mosaic, candidate)
            valid = float(np.mean(observation_valid_mask(local)))
            if coverage >= 0.999 and valid >= HIGH_OBSERVATION_GATE:
                mosaics.append((group, valid))
        if mosaics:
            group, valid = sorted(
                mosaics,
                key=lambda pair: (
                    -pair[1],
                    abs((pair[0][0].acquisition - acquisition).total_seconds()),
                    np.mean(
                        [
                            float(item.item["properties"].get("eo:cloud_cover", 100))
                            for item in pair[0]
                        ]
                    ),
                    tuple(item.item["id"] for item in pair[0]),
                ),
            )[0]
            return SentinelChoice(
                method=(
                    "EXTENDED_WINDOW_TILE_MOSAIC"
                    if extended
                    else "SAME_DATE_TILE_MOSAIC"
                ),
                items=tuple(raster.item for raster in group),
                acquisition_times=tuple(raster.acquisition for raster in group),
                valid_fraction=valid,
            )
        return None

    def _select_sentinel(self, candidate: DemoAOICandidate) -> SentinelChoice:
        choice = self._choice_from_items(
            candidate, self.initial_sentinel_items, extended=False
        )
        if choice is not None:
            return choice
        self.extended_window_used = True
        if not self.extended_sentinel_items:
            self.extended_sentinel_items = self._sentinel_items("extended")
        choice = self._choice_from_items(
            candidate, self.extended_sentinel_items, extended=True
        )
        if choice is None:
            choice = self._composite_choice(candidate, self.extended_sentinel_items)
        if choice is None:
            raise RuntimeError(
                f"BLOCKED_SENTINEL_COVERAGE: {candidate.candidate_id} has no HIGH observation"
            )
        return choice

    def _composite_choice(
        self,
        candidate: DemoAOICandidate,
        items: list[dict[str, Any]],
    ) -> SentinelChoice | None:
        """Build a QA-screened temporal fallback from the extended window."""
        polygon = shape(candidate.geometry_projected)
        contributing: list[SentinelItemRaster] = []
        observations: list[np.ndarray] = []
        for group in self._group_by_acquisition(
            [self._load_scl_item(item) for item in items]
        ):
            footprint = unary_union(
                [raster.footprint_projected for raster in group]
            )
            if polygon.intersection(footprint).area <= 0:
                continue
            mosaic = np.zeros(self.analysis.shape, dtype=np.uint8)
            for raster in group:
                take = (mosaic == 0) & (raster.scl != 0)
                mosaic[take] = raster.scl[take]
            observed = observation_valid_mask(
                self._candidate_array(mosaic, candidate)
            )
            if not np.any(observed):
                continue
            contributing.extend(group)
            observations.append(observed)
        if not observations:
            return None
        valid_fraction = float(np.mean(np.any(np.stack(observations), axis=0)))
        if valid_fraction < HIGH_OBSERVATION_GATE:
            return None
        ordered = sorted(
            {raster.item["id"]: raster for raster in contributing}.values(),
            key=lambda raster: (raster.acquisition, raster.item["id"]),
        )
        return SentinelChoice(
            method="QA_MEDIAN_COMPOSITE",
            items=tuple(raster.item for raster in ordered),
            acquisition_times=tuple(raster.acquisition for raster in ordered),
            valid_fraction=valid_fraction,
        )

    def _aligned_reflectance(
        self, item: dict[str, Any], asset_key: str, scale: float, offset: float,
        nodata: int, saturated: int,
    ) -> np.ndarray:
        path = self._ensure_window(
            "sentinel",
            item,
            asset_key,
            lambda: self.sentinel_stac.signed_asset_href(item, asset_key),
        )
        raw, metadata = read_cached_window(path)
        values = dn_to_reflectance(raw, scale, offset, nodata)
        values[np.asarray(raw) == saturated] = np.nan
        return align_array(
            values,
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

    def _prepare_vegetation(self, choice: SentinelChoice) -> PreparedVegetation:
        key = (choice.method, *sorted(item["id"] for item in choice.items))
        cached = self.prepared_vegetation.get(key)
        if cached is not None:
            return cached
        if choice.method == "QA_MEDIAN_COMPOSITE":
            prepared = self._prepare_composite_vegetation(choice)
            self.prepared_vegetation[key] = prepared
            return prepared
        red = np.full(self.analysis.shape, np.nan, dtype=np.float32)
        nir = np.full(self.analysis.shape, np.nan, dtype=np.float32)
        scl = np.zeros(self.analysis.shape, dtype=np.uint8)
        for item in sorted(choice.items, key=lambda value: value["id"]):
            keys = discover_sentinel_assets(item)
            scaling, _ = self.sentinel_stac.product_metadata(item)
            SentinelM3APipeline._validate_scaling_metadata(item, scaling)
            item_red = self._aligned_reflectance(
                item, keys["b04"], scaling.scale, scaling.b04_offset,
                scaling.nodata, scaling.saturated,
            )
            item_nir = self._aligned_reflectance(
                item, keys["b08"], scaling.scale, scaling.b08_offset,
                scaling.nodata, scaling.saturated,
            )
            item_scl = self._load_scl_item(item).scl
            take = (scl == 0) & (item_scl != 0)
            red[take] = item_red[take]
            nir[take] = item_nir[take]
            scl[take] = item_scl[take]
        observation = observation_valid_mask(scl) & np.isfinite(red) & np.isfinite(nir)
        land = vegetation_land_mask(scl) & observation
        ndvi = calculate_ndvi(red, nir)
        ndvi[~land] = np.nan
        prepared = PreparedVegetation(
            ndvi=ndvi,
            observation=observation,
            land=land,
            water=water_mask(scl) & observation,
        )
        self.prepared_vegetation[key] = prepared
        return prepared

    def _prepare_composite_vegetation(
        self, choice: SentinelChoice
    ) -> PreparedVegetation:
        ndvi_layers: list[np.ndarray] = []
        observation_layers: list[np.ndarray] = []
        water_layers: list[np.ndarray] = []
        item_rasters = [self._load_scl_item(item) for item in choice.items]
        for group in self._group_by_acquisition(item_rasters):
            red = np.full(self.analysis.shape, np.nan, dtype=np.float32)
            nir = np.full(self.analysis.shape, np.nan, dtype=np.float32)
            scl = np.zeros(self.analysis.shape, dtype=np.uint8)
            for raster in group:
                item = raster.item
                keys = discover_sentinel_assets(item)
                scaling, _ = self.sentinel_stac.product_metadata(item)
                SentinelM3APipeline._validate_scaling_metadata(item, scaling)
                item_red = self._aligned_reflectance(
                    item,
                    keys["b04"],
                    scaling.scale,
                    scaling.b04_offset,
                    scaling.nodata,
                    scaling.saturated,
                )
                item_nir = self._aligned_reflectance(
                    item,
                    keys["b08"],
                    scaling.scale,
                    scaling.b08_offset,
                    scaling.nodata,
                    scaling.saturated,
                )
                take = (scl == 0) & (raster.scl != 0)
                red[take] = item_red[take]
                nir[take] = item_nir[take]
                scl[take] = raster.scl[take]
            observation = (
                observation_valid_mask(scl)
                & np.isfinite(red)
                & np.isfinite(nir)
            )
            land = vegetation_land_mask(scl) & observation
            ndvi = calculate_ndvi(red, nir)
            ndvi[~land] = np.nan
            ndvi_layers.append(ndvi)
            observation_layers.append(observation)
            water_layers.append(water_mask(scl) & observation)
        if not ndvi_layers:
            raise RuntimeError("QA median composite has no contributing acquisitions")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            ndvi = np.nanmedian(np.stack(ndvi_layers), axis=0).astype(np.float32)
        observation = np.any(np.stack(observation_layers), axis=0)
        land = np.isfinite(ndvi)
        water = np.any(np.stack(water_layers), axis=0) & observation & ~land
        return PreparedVegetation(
            ndvi=ndvi,
            observation=observation,
            land=land,
            water=water,
        )

    def _screen_sentinel(
        self, candidate: DemoAOICandidate, choice: SentinelChoice
    ) -> SentinelCandidateMetrics:
        prepared = self._prepare_vegetation(choice)
        qualities: list[str] = []
        ndvi_medians: list[float | None] = []
        green: list[float | None] = []
        observed_count = 0
        water_count = 0
        for cell in build_temporary_analysis_cells(candidate):
            slices, inside = _local_geometry_mask(
                cell.geometry_projected,
                geometry_crs=candidate.projected_crs,
                raster_crs=self.analysis.crs,
                raster_transform=self.analysis.transform,
                raster_shape=self.analysis.shape,
            )
            row = aggregate_vegetation(
                prepared.ndvi[slices],
                inside_grid=inside,
                observation_valid=prepared.observation[slices],
                valid_land=prepared.land[slices],
            )
            qualities.append(str(row["quality_flag"]))
            ndvi_medians.append(row["ndvi_median"])
            green.append(row["green_fraction_grid"])
            observed_count += int((inside & prepared.observation[slices]).sum())
            water_count += int((inside & prepared.water[slices]).sum())
        valid_fraction = candidate_valid_fraction(qualities)
        ndvi_quantiles = finite_quantiles(ndvi_medians)
        green_quantiles = finite_quantiles(green)
        saturation = green_saturation_fraction(
            [
                value
                for value, quality in zip(green, qualities, strict=True)
                if quality in {"HIGH", "MEDIUM"}
            ]
        )
        water_fraction = water_count / observed_count if observed_count else 1.0
        reasons = []
        if valid_fraction < SENTINEL_QA_GATE:
            reasons.append("LOW_SENTINEL_QA")
        if water_fraction > WATER_GATE:
            reasons.append("WATER_DOMINATED")
        if (
            ndvi_quantiles["p10"] is None
            or ndvi_quantiles["p90"] is None
            or green_quantiles["p10"] is None
            or green_quantiles["p90"] is None
            or saturation is None
        ):
            reasons.append("SENTINEL_METRICS_NOT_FINITE")
        acquisition = datetime.fromisoformat(
            self.event["landsat_acquisition_time"].replace("Z", "+00:00")
        )
        differences = [
            abs((timestamp - acquisition).total_seconds()) / 86400
            for timestamp in choice.acquisition_times
        ]
        return SentinelCandidateMetrics(
            selection_method=choice.method,
            scene_ids=[item["id"] for item in choice.items],
            acquisition_times=list(choice.acquisition_times),
            minimum_time_difference_days=min(differences),
            maximum_time_difference_days=max(differences),
            valid_fraction=valid_fraction,
            water_fraction=water_fraction,
            ndvi_p10=ndvi_quantiles["p10"],
            ndvi_p50=ndvi_quantiles["p50"],
            ndvi_p90=ndvi_quantiles["p90"],
            ndvi_p90_p10_spread=(
                None
                if ndvi_quantiles["p10"] is None or ndvi_quantiles["p90"] is None
                else ndvi_quantiles["p90"] - ndvi_quantiles["p10"]
            ),
            green_p10=green_quantiles["p10"],
            green_p50=green_quantiles["p50"],
            green_p90=green_quantiles["p90"],
            green_p90_p10_spread=(
                None
                if green_quantiles["p10"] is None or green_quantiles["p90"] is None
                else green_quantiles["p90"] - green_quantiles["p10"]
            ),
            green_saturation_fraction=saturation,
            eligible=not reasons,
            rejection_reasons=reasons,
        )

    def _screen(self, candidate: DemoAOICandidate) -> SatelliteScreeningResult:
        landsat = self._screen_landsat(candidate)
        choice = self._select_sentinel(candidate)
        sentinel = self._screen_sentinel(candidate, choice)
        reasons = [*landsat.rejection_reasons, *sentinel.rejection_reasons]
        return SatelliteScreeningResult(
            candidate_id=candidate.candidate_id,
            phase=candidate.phase,
            source_candidate_ids=candidate.source_candidate_ids,
            centroid_lon=candidate.centroid_lon,
            centroid_lat=candidate.centroid_lat,
            bbox_wgs84=candidate.bbox_wgs84,
            bounds_projected=candidate.bounds_projected,
            landsat=landsat,
            sentinel=sentinel,
            satellite_eligible=not reasons,
            rejection_reasons=reasons,
        )

    @staticmethod
    def _feature_collection(
        candidates: list[DemoAOICandidate], name: str
    ) -> dict[str, Any]:
        return {
            "type": "FeatureCollection",
            "name": name,
            "features": [
                {
                    "type": "Feature",
                    "id": candidate.candidate_id,
                    "geometry": candidate.geometry_wgs84,
                    "properties": {
                        key: value
                        for key, value in candidate.model_dump(mode="json").items()
                        if key != "geometry_wgs84"
                    },
                }
                for candidate in candidates
            ],
        }

    def _write_outputs(
        self,
        base_ranked: list[SatelliteScreeningResult],
        refined: list[DemoAOICandidate],
        all_ranked: list[SatelliteScreeningResult],
        top5: list[SatelliteScreeningResult],
        top8: list[SatelliteScreeningResult],
    ) -> None:
        output = self.project_dir / "data/processed/demo_aoi_selection"
        output.mkdir(parents=True, exist_ok=True)
        rows = [result.model_dump(mode="json") for result in all_ranked]
        self.cache.write_json(
            output / "m4b_satellite_screening.json",
            {
                "processing_contract": PROCESSING_CONTRACT,
                "event_source": "data/processed/event_selection/m4a_selected_event_2026.json",
                "candidates": rows,
            },
        )
        pd.json_normalize(rows, sep=".").to_parquet(
            output / "m4b_satellite_screening.parquet", index=False
        )
        self.cache.write_json(
            output / "m4b_refined_candidates.geojson",
            self._feature_collection(refined, "M4B refinement candidates"),
        )
        self.cache.write_json(
            output / "m4b_satellite_top8.json",
            {
                "selection_method": "SATELLITE_BALANCE_MAXIMIN",
                "worldpop_screening": "NOT_RUN",
                "primary_demo_aoi": "NOT_SELECTED",
                "candidates": [self._shortlist_payload(item) for item in top8],
            },
        )
        base_landsat = [result.landsat for result in base_ranked]
        base_sentinel = [result.sentinel for result in base_ranked]
        reports = self.project_dir / "reports"
        self.cache.write_json(
            reports / "m4b_landsat_screening_audit.json",
            {
                "scene_id": self.event["scene_id"],
                "source_of_truth": "M4A selected event artifact",
                "base_candidate_count": len(base_ranked),
                "scene_covered_candidates": sum(
                    item.scene_coverage_fraction >= 0.999 for item in base_landsat
                ),
                "qa_eligible_candidates": sum(item.eligible for item in base_landsat),
                "qa_gate": LANDSAT_QA_GATE,
                "quality_semantics": "M2 CoverageQuality; HIGH and MEDIUM cells count as candidate-valid",
                "network_reads": self.cache.network_reads["landsat"],
                "cache_hits": self.cache.cache_hits["landsat"],
            },
        )
        scene_ids = sorted(
            {scene for result in all_ranked for scene in result.sentinel.scene_ids}
        )
        self.cache.write_json(
            reports / "m4b_sentinel_screening_audit.json",
            {
                "initial_window": self.sentinel_windows["initial"],
                "extended_window": self.sentinel_windows["extended"],
                "extended_window_used": self.extended_window_used,
                "initial_scenes_discovered": len(self.initial_sentinel_items),
                "extended_scenes_discovered": len(self.extended_sentinel_items),
                "selected_scene_ids": scene_ids,
                "base_qa_eligible_candidates": sum(
                    item.valid_fraction >= SENTINEL_QA_GATE for item in base_sentinel
                ),
                "qa_gate": SENTINEL_QA_GATE,
                "water_gate": WATER_GATE,
                "green_ndvi_threshold": 0.30,
                "scl_resampling": "nearest",
                "network_reads": self.cache.network_reads["sentinel"]
                + self.sentinel_stac.network_reads,
                "cache_hits": self.cache.cache_hits["sentinel"]
                + self.sentinel_stac.cache_hits,
                "initial_acquisition_accounting": self._initial_acquisition_accounting(),
            },
        )
        self.cache.write_json(
            reports / "m4b_satellite_selection_audit.json",
            {
                "M4B_STATUS": "IN_PROGRESS",
                "stages": {
                    "stage_1_geometry": "PASS",
                    "stage_2_landsat": "PASS",
                    "stage_3_sentinel": "PASS",
                    "stage_4_satellite_gate": "PASS",
                    "stage_5_refinement": "PASS",
                    "stage_6_dedup": "PASS",
                    "stage_7_top8": "PASS",
                },
                "base_candidate_count": len(base_ranked),
                "base_satellite_eligible": sum(
                    result.satellite_eligible for result in base_ranked
                ),
                "top5_base_for_refinement": [item.candidate_id for item in top5],
                "refinement_windows_generated": len(refined),
                "deduplicated_total_candidates": len(all_ranked),
                "final_satellite_eligible": sum(
                    result.satellite_eligible for result in all_ranked
                ),
                "satellite_top8": [item.candidate_id for item in top8],
                "worldpop_screening": "NOT_RUN",
                "primary_demo_aoi": "NOT_SELECTED",
                "risk_used_for_selection": False,
                "population_used_for_selection": False,
                "source_hash_audit": audit_frozen_source_hashes(self.project_dir)[
                    "status"
                ],
            },
        )
        provenance = {
            "processing_contract": PROCESSING_CONTRACT,
            "landsat_scene_id": self.event["scene_id"],
            "sentinel_scene_ids": scene_ids,
            "sentinel_selection_by_candidate": {
                result.candidate_id: {
                    "method": result.sentinel.selection_method,
                    "scene_ids": result.sentinel.scene_ids,
                    "acquisition_times": [
                        value.isoformat() for value in result.sentinel.acquisition_times
                    ],
                }
                for result in all_ranked
            },
            "raw_window_checksums": {
                str(path.relative_to(self.project_dir)): checksum(path)
                for path in sorted(self.cache.windows.glob("*.tif"))
            },
        }
        self.cache.write_json(
            self.project_dir
            / "data/provenance/demo_aoi_selection/m4b_satellite.metadata.json",
            provenance,
        )

    @staticmethod
    def _shortlist_payload(item: SatelliteScreeningResult) -> dict[str, Any]:
        return {
            "candidate_id": item.candidate_id,
            "phase": item.phase,
            "source_candidate_ids": item.source_candidate_ids,
            "centroid_lon": item.centroid_lon,
            "centroid_lat": item.centroid_lat,
            "bbox_wgs84": item.bbox_wgs84,
            "bounds_projected": item.bounds_projected,
            "landsat": {
                "scene_id": item.landsat.scene_id,
                "acquisition_time": item.landsat.acquisition_time.isoformat(),
                "scene_coverage_fraction": item.landsat.scene_coverage_fraction,
                "valid_fraction": item.landsat.valid_fraction,
                "lst_p10": item.landsat.lst_p10_c,
                "lst_p50": item.landsat.lst_p50_c,
                "lst_p90": item.landsat.lst_p90_c,
                "lst_p90_p10_spread": item.landsat.lst_p90_p10_spread_c,
            },
            "sentinel": {
                "selection_method": item.sentinel.selection_method,
                "scene_ids": item.sentinel.scene_ids,
                "acquisition_times": [
                    value.isoformat() for value in item.sentinel.acquisition_times
                ],
                "minimum_time_difference_days": item.sentinel.minimum_time_difference_days,
                "maximum_time_difference_days": item.sentinel.maximum_time_difference_days,
                "valid_fraction": item.sentinel.valid_fraction,
                "water_fraction": item.sentinel.water_fraction,
                "ndvi_p90_p10_spread": item.sentinel.ndvi_p90_p10_spread,
                "green_p90_p10_spread": item.sentinel.green_p90_p10_spread,
                "green_saturation_fraction": item.sentinel.green_saturation_fraction,
            },
            "ranks": {
                "lst_spread_rank": item.lst_spread_rank,
                "green_spread_rank": item.green_spread_rank,
                "ndvi_spread_rank": item.ndvi_spread_rank,
                "non_saturation_rank": item.non_saturation_rank,
            },
            "satellite_balance_score": item.satellite_balance_score,
        }

    def _initial_acquisition_accounting(self) -> dict[str, int]:
        path = self.cache.manifests / "initial_acquisition_accounting.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def run(self) -> dict[str, Any]:
        self._load_event()
        self._prepare_landsat()
        self.initial_sentinel_items = self._sentinel_items("initial")
        if not self.initial_sentinel_items:
            raise RuntimeError("BLOCKED_SENTINEL_COVERAGE: no initial Sentinel scenes")
        base = self.search.candidates
        base_results = [self._screen(candidate) for candidate in base]
        base_ranked = rank_satellite_candidates(base_results)
        top5 = select_top_base_for_refinement(base_ranked)
        if not top5:
            raise RuntimeError("M4B has no satellite-eligible base candidate")
        top5_geometry = [
            next(candidate for candidate in base if candidate.candidate_id == result.candidate_id)
            for result in top5
        ]
        refined = build_refinement_candidates(top5_geometry, self.search)
        pool = deduplicate_candidates([*base, *refined])
        base_by_bounds = {
            tuple(round(value, 3) for value in result.bounds_projected): result
            for result in base_results
        }
        all_results = []
        for candidate in pool:
            key = tuple(round(value, 3) for value in candidate.bounds_projected)
            existing = base_by_bounds.get(key)
            if existing is None:
                all_results.append(self._screen(candidate))
            else:
                all_results.append(
                    existing.model_copy(
                        update={
                            "source_candidate_ids": candidate.source_candidate_ids,
                            "phase": candidate.phase,
                        }
                    )
                )
        all_ranked = rank_satellite_candidates(all_results)
        top8 = select_satellite_top8(all_ranked)
        if not top8:
            raise RuntimeError("M4B has no final satellite-eligible candidate")
        self._write_outputs(base_ranked, refined, all_ranked, top5, top8)
        return {
            "M4B_STATUS": "IN_PROGRESS",
            "M4B_STAGE_1_GEOMETRY": "PASS",
            "M4B_STAGE_2_LANDSAT": "PASS",
            "M4B_STAGE_3_SENTINEL": "PASS",
            "M4B_STAGE_4_SATELLITE_GATE": "PASS",
            "M4B_STAGE_5_REFINEMENT": "PASS",
            "M4B_STAGE_6_DEDUP": "PASS",
            "M4B_STAGE_7_TOP8": "PASS",
            "BASE_CANDIDATES": len(base_ranked),
            "LANDSAT_COVERED_CANDIDATES": sum(
                result.landsat.scene_coverage_fraction >= 0.999
                for result in base_ranked
            ),
            "LANDSAT_QA_ELIGIBLE": sum(
                result.landsat.valid_fraction >= LANDSAT_QA_GATE
                for result in base_ranked
            ),
            "SENTINEL_QA_ELIGIBLE": sum(
                result.sentinel.valid_fraction >= SENTINEL_QA_GATE
                for result in base_ranked
            ),
            "BASE_SATELLITE_ELIGIBLE": sum(
                result.satellite_eligible for result in base_ranked
            ),
            "TOP5_BASE_FOR_REFINEMENT": [item.candidate_id for item in top5],
            "REFINEMENT_WINDOWS_GENERATED": len(refined),
            "DEDUPLICATED_TOTAL_CANDIDATES": len(all_ranked),
            "FINAL_SATELLITE_ELIGIBLE": sum(
                result.satellite_eligible for result in all_ranked
            ),
            "SATELLITE_TOP8": [item.model_dump(mode="json") for item in top8],
            "LANDSAT_NETWORK_READS": self.cache.network_reads["landsat"],
            "LANDSAT_CACHE_HITS": self.cache.cache_hits["landsat"],
            "SENTINEL_NETWORK_READS": self.cache.network_reads["sentinel"]
            + self.sentinel_stac.network_reads,
            "SENTINEL_CACHE_HITS": self.cache.cache_hits["sentinel"]
            + self.sentinel_stac.cache_hits,
            "SENTINEL_INITIAL_WINDOW": self.sentinel_windows["initial"],
            "SENTINEL_EXTENDED_WINDOW_USED": self.extended_window_used,
            "SENTINEL_SCENES_DISCOVERED": len(self.initial_sentinel_items)
            + len(self.extended_sentinel_items),
            "WORLDPOP_SCREENING": "NOT_RUN",
            "PRIMARY_DEMO_AOI": "NOT_SELECTED",
        }
