from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .models import PopulationConservationAudit, WorldPopArtifact


def write_artifact(
    artifact: WorldPopArtifact, json_path: Path, parquet_path: Path
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(artifact.model_dump_json(indent=2) + "\n", encoding="utf-8")
    records = []
    for grid in artifact.grids:
        record = grid.model_dump(exclude={"geometry_wgs84"})
        record["geometry_wgs84"] = json.dumps(
            grid.geometry_wgs84, sort_keys=True, separators=(",", ":")
        )
        records.append(record)
    pd.DataFrame.from_records(records).to_parquet(parquet_path, index=False)


def write_audit(audit: PopulationConservationAudit, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(audit.model_dump_json(indent=2) + "\n", encoding="utf-8")

