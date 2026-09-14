from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.grid.pilot import PilotGridCell

from .client import WorldPopClient
from .models import (
    CachedTaskResult,
    WorldPopEndpoint,
    WorldPopGridPopulation,
    WorldPopQuery,
)
from .provenance import WorldPopApiProvenance, file_checksum


CHILD_CODES = {"00", "01", "05", "10"}
ELDERLY_CODES = {"65", "70", "75", "80", "85", "90"}


def normalize_age_code(value: Any) -> str:
    text = str(value).strip().lower().replace("+", "")
    if text.isdigit():
        return text.zfill(2)
    raise ValueError(f"unsupported WorldPop age class: {value!r}")


def _row_population(row: dict[str, Any]) -> float:
    if "both" in row and row["both"] is not None:
        value = float(row["both"])
    elif "total" in row and row["total"] is not None:
        value = float(row["total"])
    elif "male" in row and "female" in row:
        value = float(row["male"]) + float(row["female"])
    else:
        raise ValueError("age-sex row has no supported population fields")
    if value < 0:
        raise ValueError("WorldPop estimated population cannot be negative")
    return value


def parse_agesex_result(
    result: dict[str, Any],
) -> tuple[float, float, float, str, dict[str, float]]:
    rows = result.get("agesex_pyramid") or result.get("agesexpyramid")
    if not isinstance(rows, list) or not rows:
        raise ValueError("WorldPop result has no non-empty age-sex pyramid")
    by_code: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict) or "class" not in row:
            raise ValueError("WorldPop age-sex row has no class field")
        code = normalize_age_code(row["class"])
        by_code[code] = by_code.get(code, 0.0) + _row_population(row)

    missing = (CHILD_CODES | ELDERLY_CODES) - by_code.keys()
    if missing:
        raise ValueError(
            "WorldPop response is missing required age classes: "
            + ", ".join(sorted(missing))
        )
    pyramid_total = sum(by_code.values())
    total = float(result.get("total_population", pyramid_total))
    if total < 0:
        raise ValueError("WorldPop total estimated population cannot be negative")
    child = sum(by_code[code] for code in CHILD_CODES)
    elderly = sum(by_code[code] for code in ELDERLY_CODES)
    tolerance = max(1e-6, total * 1e-6)
    if child + elderly > total + tolerance:
        raise ValueError("WorldPop age subsets exceed total estimated population")
    data_source = str(result.get("data_source") or "WorldPop API response")
    return total, child, elderly, data_source, by_code


class WorldPopAPIBackend:
    def __init__(
        self,
        client: WorldPopClient,
        provenance_dir: Path,
    ) -> None:
        self.client = client
        self.provenance_dir = provenance_dir
        provenance_dir.mkdir(parents=True, exist_ok=True)

    def fetch_grid(self, cell: PilotGridCell) -> WorldPopGridPopulation:
        query = WorldPopQuery(
            endpoint=WorldPopEndpoint.AGESEX,
            geojson=cell.geometry_wgs84,
            year=2026,
            resolution="100m",
            sex="both",
        )
        completed = self.client.execute(query)
        total, child, elderly, data_source, _ = parse_agesex_result(completed.result)
        source_id = f"worldpop:api:2026:100m:{completed.request_hash}"
        population = WorldPopGridPopulation(
            grid_id=cell.grid_id,
            geometry_wgs84=cell.geometry_wgs84,
            centroid_lat=cell.centroid_lat,
            centroid_lon=cell.centroid_lon,
            projected_crs=cell.projected_crs,
            area_m2=cell.area_m2,
            population_total=total,
            population_age_0_14=child,
            population_age_65_plus=elderly,
            data_source=data_source,
            source_id=source_id,
            task_id=completed.task_id,
            request_hash=completed.request_hash,
            raw_response_path=str(completed.response_path),
        )
        self._write_provenance(cell, population, completed)
        return population

    def fetch_whole_population(
        self, geometry_wgs84: dict[str, Any]
    ) -> tuple[float, CachedTaskResult, str]:
        completed = self.client.execute(
            WorldPopQuery(
                endpoint=WorldPopEndpoint.POPULATION,
                geojson=geometry_wgs84,
                year=2026,
                resolution="100m",
            )
        )
        if "total_population" not in completed.result:
            raise ValueError("whole-area response has no total_population")
        total = float(completed.result["total_population"])
        if total < 0:
            raise ValueError("whole-area estimated population cannot be negative")
        return (
            total,
            completed,
            str(completed.result.get("data_source") or "WorldPop API response"),
        )

    def _write_provenance(
        self,
        cell: PilotGridCell,
        population: WorldPopGridPopulation,
        completed: CachedTaskResult,
    ) -> None:
        provenance = WorldPopApiProvenance(
            dataset=population.data_source,
            api_url=self.client.base_url,
            endpoint="/agesex",
            year=2026,
            resolution="100m",
            data_source=population.data_source,
            grid_id=cell.grid_id,
            geometry_wgs84=cell.geometry_wgs84,
            task_id=completed.task_id,
            request_hash=completed.request_hash,
            submitted_at=completed.submitted_at,
            retrieved_at=completed.retrieved_at,
            raw_response_path=str(completed.response_path),
            checksum=file_checksum(completed.response_path),
        )
        path = self.provenance_dir / f"{cell.grid_id}.json"
        path.write_text(provenance.model_dump_json(indent=2) + "\n", encoding="utf-8")

