from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pyproj import CRS, Transformer
from shapely.geometry import box, mapping, shape
from shapely.ops import transform, unary_union


SEARCH_CENTER_WGS84 = (120.093, 30.211)
SEARCH_SIZE_M = 30_000
CANDIDATE_SIZE_M = 5_000
GRID_SIZE_M = 250
POPULATION_CELL_SIZE_M = 1_000
REFINEMENT_OFFSET_M = 2_500
BASE_ROWS = SEARCH_SIZE_M // CANDIDATE_SIZE_M
BASE_COLUMNS = SEARCH_SIZE_M // CANDIDATE_SIZE_M


class DemoAOICandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    phase: Literal["BASE", "REFINED"]
    source_candidate_ids: list[str] = Field(min_length=1)
    row: int | None = None
    column: int | None = None
    projected_crs: str
    bounds_projected: tuple[float, float, float, float]
    geometry_projected: dict[str, Any]
    geometry_wgs84: dict[str, Any]
    bbox_wgs84: tuple[float, float, float, float]
    centroid_lon: float
    centroid_lat: float
    width_m: int = CANDIDATE_SIZE_M
    height_m: int = CANDIDATE_SIZE_M
    area_m2: float = Field(gt=0)
    future_grid_rows: int = 20
    future_grid_columns: int = 20
    future_grid_count: int = 400
    coarse_grid_rows: int = 5
    coarse_grid_columns: int = 5
    coarse_grid_count: int = 25


class TemporaryAnalysisCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grid_id: str
    row: int
    column: int
    bounds_projected: tuple[float, float, float, float]
    geometry_projected: dict[str, Any]
    geometry_wgs84: dict[str, Any]
    area_m2: float


class DemoAOISearchGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    center_lon: float
    center_lat: float
    projected_crs: str
    projected_crs_wkt: str
    bounds_projected: tuple[float, float, float, float]
    geometry_projected: dict[str, Any]
    geometry_wgs84: dict[str, Any]
    bbox_wgs84: tuple[float, float, float, float]
    width_m: int
    height_m: int
    area_m2: float
    base_rows: int
    base_columns: int
    base_candidate_count: int
    candidates: list[DemoAOICandidate]


def build_search_crs(
    center_wgs84: tuple[float, float] = SEARCH_CENTER_WGS84,
) -> CRS:
    lon, lat = center_wgs84
    if not -180 <= lon <= 180 or not -90 < lat < 90:
        raise ValueError("search center is outside valid longitude/latitude bounds")
    crs = CRS.from_dict(
        {
            "proj": "aeqd",
            "lat_0": lat,
            "lon_0": lon,
            "datum": "WGS84",
            "units": "m",
        }
    )
    if not crs.is_projected:
        raise RuntimeError("M4B search CRS must be projected")
    axis_units = {axis.unit_name.lower() for axis in crs.axis_info}
    if not axis_units <= {"metre", "meter"}:
        raise RuntimeError("M4B search CRS axes must use meters")
    return crs


def _transformers(crs: CRS) -> tuple[Transformer, Transformer]:
    return (
        Transformer.from_crs("EPSG:4326", crs, always_xy=True),
        Transformer.from_crs(crs, "EPSG:4326", always_xy=True),
    )


def _stable_refined_id(bounds: tuple[float, float, float, float]) -> str:
    canonical = ",".join(f"{value:.3f}" for value in bounds)
    digest = hashlib.sha256(canonical.encode("ascii")).hexdigest()[:10].upper()
    return f"M4B-R-{digest}"


def _candidate_from_polygon(
    polygon,
    crs: CRS,
    to_wgs84: Transformer,
    *,
    candidate_id: str,
    phase: Literal["BASE", "REFINED"],
    source_candidate_ids: list[str],
    row: int | None = None,
    column: int | None = None,
) -> DemoAOICandidate:
    west, south, east, north = polygon.bounds
    if not (
        abs((east - west) - CANDIDATE_SIZE_M) < 1e-6
        and abs((north - south) - CANDIDATE_SIZE_M) < 1e-6
    ):
        raise ValueError("candidate must be exactly 5000 m by 5000 m")
    polygon_wgs84 = transform(to_wgs84.transform, polygon)
    centroid = polygon_wgs84.centroid
    return DemoAOICandidate(
        candidate_id=candidate_id,
        phase=phase,
        source_candidate_ids=source_candidate_ids,
        row=row,
        column=column,
        projected_crs=crs.to_string(),
        bounds_projected=tuple(float(value) for value in polygon.bounds),
        geometry_projected=mapping(polygon),
        geometry_wgs84=mapping(polygon_wgs84),
        bbox_wgs84=tuple(round(value, 8) for value in polygon_wgs84.bounds),
        centroid_lon=round(centroid.x, 8),
        centroid_lat=round(centroid.y, 8),
        area_m2=float(polygon.area),
    )


def build_base_candidates(
    crs: CRS | None = None,
    center_wgs84: tuple[float, float] = SEARCH_CENTER_WGS84,
) -> list[DemoAOICandidate]:
    crs = crs or build_search_crs(center_wgs84)
    to_projected, to_wgs84 = _transformers(crs)
    center_x, center_y = to_projected.transform(*center_wgs84)
    origin_x = center_x - SEARCH_SIZE_M / 2
    origin_y = center_y - SEARCH_SIZE_M / 2
    candidates: list[DemoAOICandidate] = []
    for row in range(BASE_ROWS):
        for column in range(BASE_COLUMNS):
            west = origin_x + column * CANDIDATE_SIZE_M
            south = origin_y + row * CANDIDATE_SIZE_M
            candidate_id = f"M4B-B-R{row:02d}-C{column:02d}"
            candidates.append(
                _candidate_from_polygon(
                    box(
                        west,
                        south,
                        west + CANDIDATE_SIZE_M,
                        south + CANDIDATE_SIZE_M,
                    ),
                    crs,
                    to_wgs84,
                    candidate_id=candidate_id,
                    phase="BASE",
                    source_candidate_ids=[candidate_id],
                    row=row,
                    column=column,
                )
            )
    return candidates


def build_search_geometry(
    center_wgs84: tuple[float, float] = SEARCH_CENTER_WGS84,
) -> DemoAOISearchGeometry:
    crs = build_search_crs(center_wgs84)
    to_projected, to_wgs84 = _transformers(crs)
    center_x, center_y = to_projected.transform(*center_wgs84)
    envelope = box(
        center_x - SEARCH_SIZE_M / 2,
        center_y - SEARCH_SIZE_M / 2,
        center_x + SEARCH_SIZE_M / 2,
        center_y + SEARCH_SIZE_M / 2,
    )
    envelope_wgs84 = transform(to_wgs84.transform, envelope)
    candidates = build_base_candidates(crs, center_wgs84)
    return DemoAOISearchGeometry(
        center_lon=center_wgs84[0],
        center_lat=center_wgs84[1],
        projected_crs=crs.to_string(),
        projected_crs_wkt=crs.to_wkt(),
        bounds_projected=tuple(float(value) for value in envelope.bounds),
        geometry_projected=mapping(envelope),
        geometry_wgs84=mapping(envelope_wgs84),
        bbox_wgs84=tuple(round(value, 8) for value in envelope_wgs84.bounds),
        width_m=SEARCH_SIZE_M,
        height_m=SEARCH_SIZE_M,
        area_m2=float(envelope.area),
        base_rows=BASE_ROWS,
        base_columns=BASE_COLUMNS,
        base_candidate_count=len(candidates),
        candidates=candidates,
    )


def build_temporary_analysis_cells(
    candidate: DemoAOICandidate,
) -> list[TemporaryAnalysisCell]:
    crs = CRS.from_user_input(candidate.projected_crs)
    _, to_wgs84 = _transformers(crs)
    west, south, east, north = candidate.bounds_projected
    if not (
        abs(east - west - CANDIDATE_SIZE_M) < 1e-6
        and abs(north - south - CANDIDATE_SIZE_M) < 1e-6
    ):
        raise ValueError("temporary grid requires a 5 km candidate")
    count = CANDIDATE_SIZE_M // GRID_SIZE_M
    cells: list[TemporaryAnalysisCell] = []
    for row in range(count):
        for column in range(count):
            cell_west = west + column * GRID_SIZE_M
            cell_south = south + row * GRID_SIZE_M
            polygon = box(
                cell_west,
                cell_south,
                cell_west + GRID_SIZE_M,
                cell_south + GRID_SIZE_M,
            )
            cells.append(
                TemporaryAnalysisCell(
                    grid_id=f"{candidate.candidate_id}-G{row:02d}{column:02d}",
                    row=row,
                    column=column,
                    bounds_projected=tuple(float(value) for value in polygon.bounds),
                    geometry_projected=mapping(polygon),
                    geometry_wgs84=mapping(transform(to_wgs84.transform, polygon)),
                    area_m2=float(polygon.area),
                )
            )
    return cells


def build_refinement_candidates(
    base_candidates: list[DemoAOICandidate],
    search: DemoAOISearchGeometry,
) -> list[DemoAOICandidate]:
    crs = CRS.from_user_input(search.projected_crs)
    _, to_wgs84 = _transformers(crs)
    envelope = shape(search.geometry_projected)
    offsets = (
        (0, 0),
        (REFINEMENT_OFFSET_M, 0),
        (-REFINEMENT_OFFSET_M, 0),
        (0, REFINEMENT_OFFSET_M),
        (0, -REFINEMENT_OFFSET_M),
        (REFINEMENT_OFFSET_M, REFINEMENT_OFFSET_M),
        (REFINEMENT_OFFSET_M, -REFINEMENT_OFFSET_M),
        (-REFINEMENT_OFFSET_M, REFINEMENT_OFFSET_M),
        (-REFINEMENT_OFFSET_M, -REFINEMENT_OFFSET_M),
    )
    refined: list[DemoAOICandidate] = []
    for source in base_candidates:
        source_polygon = shape(source.geometry_projected)
        center_x, center_y = source_polygon.centroid.coords[0]
        for offset_x, offset_y in offsets:
            polygon = box(
                center_x + offset_x - CANDIDATE_SIZE_M / 2,
                center_y + offset_y - CANDIDATE_SIZE_M / 2,
                center_x + offset_x + CANDIDATE_SIZE_M / 2,
                center_y + offset_y + CANDIDATE_SIZE_M / 2,
            )
            if not envelope.covers(polygon):
                continue
            bounds = tuple(float(value) for value in polygon.bounds)
            refined.append(
                _candidate_from_polygon(
                    polygon,
                    crs,
                    to_wgs84,
                    candidate_id=_stable_refined_id(bounds),
                    phase="REFINED",
                    source_candidate_ids=[source.candidate_id],
                )
            )
    return deduplicate_candidates(refined)


def deduplicate_candidates(
    candidates: list[DemoAOICandidate],
) -> list[DemoAOICandidate]:
    unique: dict[tuple[float, float, float, float], DemoAOICandidate] = {}
    sources: dict[tuple[float, float, float, float], set[str]] = {}
    for candidate in candidates:
        key = tuple(round(value, 3) for value in candidate.bounds_projected)
        sources.setdefault(key, set()).update(candidate.source_candidate_ids)
        current = unique.get(key)
        if current is None or candidate.candidate_id < current.candidate_id:
            unique[key] = candidate
    result = []
    for key in sorted(unique):
        candidate = unique[key]
        result.append(
            candidate.model_copy(update={"source_candidate_ids": sorted(sources[key])})
        )
    return result


def _base_candidates_geojson(search: DemoAOISearchGeometry) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "name": "M4B base demo AOI candidates",
        "metadata": {
            "stage": "M4B_STAGE_1_GEOMETRY",
            "search_center_wgs84": [search.center_lon, search.center_lat],
            "search_crs": search.projected_crs,
            "search_bbox_wgs84": search.bbox_wgs84,
            "search_bounds_projected": search.bounds_projected,
            "search_width_m": search.width_m,
            "search_height_m": search.height_m,
            "candidate_size_m": CANDIDATE_SIZE_M,
            "stride_m": CANDIDATE_SIZE_M,
        },
        "features": [
            {
                "type": "Feature",
                "id": candidate.candidate_id,
                "geometry": candidate.geometry_wgs84,
                "properties": {
                    key: value
                    for key, value in candidate.model_dump(mode="json").items()
                    if key not in {"geometry_wgs84"}
                },
            }
            for candidate in search.candidates
        ],
    }


def write_m4b_geometry_artifacts(project_dir: Path) -> DemoAOISearchGeometry:
    search = build_search_geometry()
    output = project_dir / "data/processed/demo_aoi_selection"
    output.mkdir(parents=True, exist_ok=True)
    geojson_path = output / "m4b_base_candidates.geojson"
    geojson_path.write_text(
        json.dumps(_base_candidates_geojson(search), indent=2) + "\n",
        encoding="utf-8",
    )
    polygons = [shape(candidate.geometry_projected) for candidate in search.candidates]
    union = unary_union(polygons)
    audit = {
        "M4B_STAGE": "STAGE_1_GEOMETRY",
        "status": "PASS",
        "search_center_wgs84": [search.center_lon, search.center_lat],
        "search_crs": search.projected_crs,
        "search_crs_is_projected": CRS.from_user_input(search.projected_crs).is_projected,
        "search_envelope_width_m": search.width_m,
        "search_envelope_height_m": search.height_m,
        "search_envelope_area_m2": search.area_m2,
        "search_bounds_projected": search.bounds_projected,
        "search_bbox_wgs84": search.bbox_wgs84,
        "base_rows": search.base_rows,
        "base_columns": search.base_columns,
        "base_candidate_count": search.base_candidate_count,
        "candidate_width_m": CANDIDATE_SIZE_M,
        "candidate_height_m": CANDIDATE_SIZE_M,
        "candidate_area_m2": CANDIDATE_SIZE_M**2,
        "stride_m": CANDIDATE_SIZE_M,
        "future_analysis_grid": {
            "cell_size_m": GRID_SIZE_M,
            "rows": CANDIDATE_SIZE_M // GRID_SIZE_M,
            "columns": CANDIDATE_SIZE_M // GRID_SIZE_M,
            "cell_count": (CANDIDATE_SIZE_M // GRID_SIZE_M) ** 2,
        },
        "coarse_population_grid": {
            "cell_size_m": POPULATION_CELL_SIZE_M,
            "rows": CANDIDATE_SIZE_M // POPULATION_CELL_SIZE_M,
            "columns": CANDIDATE_SIZE_M // POPULATION_CELL_SIZE_M,
            "cell_count": (CANDIDATE_SIZE_M // POPULATION_CELL_SIZE_M) ** 2,
        },
        "refinement_offset_m": REFINEMENT_OFFSET_M,
        "base_candidate_union_area_m2": float(union.area),
        "base_candidate_overlap_area_m2": float(
            sum(polygon.area for polygon in polygons) - union.area
        ),
        "base_candidates_cover_search_envelope": abs(union.area - search.area_m2)
        < 1e-6,
        "duplicate_base_candidate_count": len(search.candidates)
        - len(deduplicate_candidates(search.candidates)),
        "network_accessed": False,
    }
    report = project_dir / "reports/m4b_geometry_audit.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    return search
