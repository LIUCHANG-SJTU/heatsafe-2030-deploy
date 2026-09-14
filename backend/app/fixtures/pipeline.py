from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path

from app.models.grid import DataMode, RawGridCell
from app.models.provenance import ProvenanceRecord


# Approximately 2.5 km by 2.5 km at Hangzhou latitude, divided into 10 x 10.
FIXTURE_BBOX = (120.08, 30.20, 120.10598, 30.22246)
FIXTURE_TIMESTAMP = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
FIXTURE_SOURCE_IDS = [
    "fixture:landsat-st",
    "fixture:era5-land",
    "fixture:worldpop-total",
    "fixture:worldpop-age-sex",
    "fixture:sentinel-2-ndvi",
]


def _polygon(west: float, south: float, east: float, north: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [west, south],
                [east, south],
                [east, north],
                [west, north],
                [west, south],
            ]
        ],
    }


def build_fixture_cells(size: int = 10) -> list[RawGridCell]:
    """Build deterministic synthetic cells for pipeline and API testing."""

    if size <= 1:
        raise ValueError("fixture size must be greater than 1")
    west, south, east, north = FIXTURE_BBOX
    lon_step = (east - west) / size
    lat_step = (north - south) / size
    cells: list[RawGridCell] = []

    for row in range(size):
        for column in range(size):
            x = column / (size - 1)
            y = row / (size - 1)
            urban_core = math.exp(-(((x - 0.68) ** 2 + (y - 0.38) ** 2) / 0.055))
            secondary_core = math.exp(
                -(((x - 0.25) ** 2 + (y - 0.72) ** 2) / 0.04)
            )
            vegetation = max(
                0.08,
                min(0.82, 0.62 - 0.42 * urban_core + 0.08 * math.sin(row)),
            )
            population = 180 + 3200 * urban_core + 1500 * secondary_core + 25 * row
            elderly_share = 0.10 + 0.07 * secondary_core + 0.02 * y
            child_share = 0.12 + 0.05 * urban_core
            lst = 31.5 + 8.5 * urban_core + 3.2 * secondary_core - 3.0 * vegetation
            anomaly_percentile = max(
                0.05, min(0.99, 0.42 + 0.48 * urban_core + 0.18 * secondary_core)
            )
            exceedance = 2.0 + 12.0 * urban_core + 6.0 * secondary_core

            cell_west = west + column * lon_step
            cell_south = south + row * lat_step
            cell_east = cell_west + lon_step
            cell_north = cell_south + lat_step
            cells.append(
                RawGridCell(
                    grid_id=f"HZ-FIX-{row * size + column + 1:05d}",
                    geometry=_polygon(cell_west, cell_south, cell_east, cell_north),
                    lat=round((cell_south + cell_north) / 2, 7),
                    lon=round((cell_west + cell_east) / 2, 7),
                    population_total=round(population, 3),
                    population_age_0_14=round(population * child_share, 3),
                    population_age_65_plus=round(population * elderly_share, 3),
                    land_surface_temperature=round(lst, 3),
                    temperature_percentile=round(anomaly_percentile, 6),
                    heat_exceedance_hours=round(exceedance, 3),
                    ndvi=round(vegetation, 6),
                    data_timestamp=FIXTURE_TIMESTAMP,
                    data_source_ids=FIXTURE_SOURCE_IDS,
                    data_mode=DataMode.FIXTURE,
                )
            )
    return cells


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def write_fixture_dataset(grid_path: Path, provenance_path: Path) -> None:
    cells = build_fixture_cells()
    grid_path.parent.mkdir(parents=True, exist_ok=True)
    provenance_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "data_mode": "FIXTURE",
        "warning": "Synthetic fixture values. Not a real analysis of Hangzhou.",
        "grid_size_meters": 250,
        "cells": [cell.model_dump(mode="json") for cell in cells],
    }
    grid_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    provenance = ProvenanceRecord(
        dataset="HeatSafe deterministic M0 fixture grid",
        provider="HeatSafe 2030 development team",
        source_url="https://example.invalid/heatsafe-fixture",
        retrieved_at=datetime.now(UTC),
        time_range="Synthetic fixture timestamp: 2026-08-01",
        bbox=FIXTURE_BBOX,
        license="Development fixture only; not an external dataset",
        checksum=_sha256(grid_path),
        data_mode="FIXTURE",
        notes="Generated locally by scripts/generate_fixture.py; contains no observations.",
    )
    provenance_path.write_text(
        provenance.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
