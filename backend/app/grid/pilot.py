from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pyproj import CRS, Transformer
from shapely.geometry import box, mapping
from shapely.ops import transform


PILOT_CENTER_WGS84 = (120.093, 30.211)


class PilotGridCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grid_id: str
    geometry_projected: dict[str, Any]
    geometry_wgs84: dict[str, Any]
    centroid_lat: float
    centroid_lon: float
    projected_crs: str
    area_m2: float = Field(gt=0)


class PilotGrid(BaseModel):
    pilot_name: str
    description: str
    bbox_wgs84: tuple[float, float, float, float]
    projected_crs: str
    grid_size_meters: int
    rows: int
    columns: int
    cells: list[PilotGridCell]


def derive_utm_crs(lon: float, lat: float) -> CRS:
    if not -180 <= lon <= 180 or not -80 <= lat <= 84:
        raise ValueError("centroid is outside the supported UTM extent")
    zone = math.floor((lon + 180) / 6) + 1
    epsg = (32600 if lat >= 0 else 32700) + zone
    return CRS.from_epsg(epsg)


def build_pilot_grid(
    center_wgs84: tuple[float, float] = PILOT_CENTER_WGS84,
    rows: int = 10,
    columns: int = 10,
    grid_size_meters: int = 250,
) -> PilotGrid:
    if rows <= 0 or columns <= 0 or grid_size_meters <= 0:
        raise ValueError("rows, columns, and grid size must be positive")

    lon, lat = center_wgs84
    projected = derive_utm_crs(lon, lat)
    to_projected = Transformer.from_crs("EPSG:4326", projected, always_xy=True)
    to_wgs84 = Transformer.from_crs(projected, "EPSG:4326", always_xy=True)
    center_x, center_y = to_projected.transform(lon, lat)
    origin_x = center_x - columns * grid_size_meters / 2
    origin_y = center_y - rows * grid_size_meters / 2

    cells: list[PilotGridCell] = []
    for row in range(rows):
        for column in range(columns):
            west = origin_x + column * grid_size_meters
            south = origin_y + row * grid_size_meters
            polygon = box(
                west,
                south,
                west + grid_size_meters,
                south + grid_size_meters,
            )
            polygon_wgs84 = transform(to_wgs84.transform, polygon)
            centroid = polygon_wgs84.centroid
            cells.append(
                PilotGridCell(
                    grid_id=f"HZP-{row * columns + column + 1:04d}",
                    geometry_projected=mapping(polygon),
                    geometry_wgs84=mapping(polygon_wgs84),
                    centroid_lat=round(centroid.y, 8),
                    centroid_lon=round(centroid.x, 8),
                    projected_crs=projected.to_string(),
                    area_m2=polygon.area,
                )
            )

    union_wgs84 = transform(
        to_wgs84.transform,
        box(
            origin_x,
            origin_y,
            origin_x + columns * grid_size_meters,
            origin_y + rows * grid_size_meters,
        ),
    )
    return PilotGrid(
        pilot_name="Hangzhou 2.5 km pilot study area",
        description=(
            "A bounded engineering pilot inside Hangzhou; it does not represent "
            "the city as a whole."
        ),
        bbox_wgs84=tuple(round(value, 8) for value in union_wgs84.bounds),
        projected_crs=projected.to_string(),
        grid_size_meters=grid_size_meters,
        rows=rows,
        columns=columns,
        cells=cells,
    )


def write_pilot_geojson(grid: PilotGrid, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "type": "FeatureCollection",
        "name": grid.pilot_name,
        "metadata": {
            "description": grid.description,
            "bbox_wgs84": grid.bbox_wgs84,
            "projected_crs": grid.projected_crs,
            "grid_size_meters": grid.grid_size_meters,
            "rows": grid.rows,
            "columns": grid.columns,
        },
        "features": [
            {
                "type": "Feature",
                "id": cell.grid_id,
                "geometry": cell.geometry_wgs84,
                "properties": {
                    "grid_id": cell.grid_id,
                    "centroid_lat": cell.centroid_lat,
                    "centroid_lon": cell.centroid_lon,
                    "projected_crs": cell.projected_crs,
                    "area_m2": cell.area_m2,
                    "geometry_projected": cell.geometry_projected,
                },
            }
            for cell in grid.cells
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

