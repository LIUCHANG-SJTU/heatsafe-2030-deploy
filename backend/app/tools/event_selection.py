from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.config import settings
from app.models.landsat import SceneCandidate
from app.tools.era5.cache import ERA5Cache, file_checksum
from app.tools.era5.client import ERA5CDSClient
from app.tools.era5.climatology import (
    QUANTILE_METHOD,
    month_hour_p90,
    month_hour_statistics,
    month_same_hour,
)
from app.tools.era5.contract import DATASET_ID, REQUEST_LATITUDE, REQUEST_LONGITUDE, request_for
from app.tools.era5.parsing import ParsedERA5Point, parse_era5_point
from app.tools.era5.percentile import empirical_percentile
from app.tools.era5.persistence import evaluate_month_hour_persistence
from app.tools.era5.provenance import ERA5ArtifactProvenance
from app.tools.era5.temperature import nearest_hour
from app.tools.era5.temporal_score import temporal_severity
from app.tools.landsat.pipeline import LandsatM2Pipeline, LandsatPaths
from app.tools.landsat.stac import candidate_from_item
from app.tools.source_hash_audit import audit_frozen_source_hashes


SEARCH_START = "2026-06-01"
SEARCH_END = "2026-08-20"
SUMMER_EVENT_RANGE = "2026-05-29/2026-08-20"
QA_THRESHOLD = 0.80
SELECTION_METHOD = "MAX_TEMPORAL_SEVERITY_AFTER_LANDSAT_QA"
MONTHS = (6, 7, 8)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def candidate_qa_rejection(candidate: SceneCandidate) -> str | None:
    if not candidate.st_asset_available:
        return "MISSING_ST_ASSET"
    if not candidate.qa_asset_available:
        return "MISSING_QA_ASSET"
    if candidate.pilot_valid_fraction is None:
        return "QA_NOT_EVALUATED"
    if candidate.pilot_valid_fraction < QA_THRESHOLD:
        return "PILOT_VALID_FRACTION_BELOW_0.80"
    return None


def rank_eligible_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    eligible = [event for event in events if event.get("eligible")]
    return sorted(
        eligible,
        key=lambda event: (
            -float(event["temporal_severity_score"]),
            -float(event["pilot_valid_fraction"]),
            float(event["scene_cloud_cover"]),
            abs(float(event["time_offset_minutes"])),
            str(event["landsat_acquisition_time"]),
            str(event["scene_id"]),
        ),
    )


class M4AEventSelectionPipeline:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.era_cache = ERA5Cache(project_dir / "data/raw/era5")
        self.era_client = ERA5CDSClient(DATASET_ID, self.era_cache)
        self.landsat = LandsatM2Pipeline(
            LandsatPaths(project_dir),
            settings.landsat_stac_url,
            settings.landsat_collection,
            SEARCH_START,
            SEARCH_END,
            50.0,
        )

    def _baseline(self) -> tuple[ParsedERA5Point, Path]:
        provenance_path = self.project_dir / "data/provenance/era5/baseline.metadata.json"
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        raw_path = self.project_dir / provenance["raw_artifact_path"]
        if file_checksum(raw_path) != provenance["checksum"]:
            raise RuntimeError("M3B baseline checksum mismatch")
        return parse_era5_point(raw_path), raw_path

    def _summer(self) -> tuple[ParsedERA5Point, Path, str]:
        request = request_for(SUMMER_EVENT_RANGE)
        path, key = self.era_client.retrieve(request, "summer-event-2026")
        parsed = parse_era5_point(path)
        provenance = ERA5ArtifactProvenance(
            dataset_id=DATASET_ID,
            requested_latitude=REQUEST_LATITUDE,
            requested_longitude=REQUEST_LONGITUDE,
            returned_latitude=parsed.latitude,
            returned_longitude=parsed.longitude,
            spatial_selection_method="CDS nearest 0.1 degree ERA5-Land grid point",
            variables=["2m_temperature", "2m_dewpoint_temperature"],
            units={
                "2m_temperature": parsed.temperature_units,
                "2m_dewpoint_temperature": parsed.dewpoint_units,
            },
            date_range=SUMMER_EVENT_RANGE,
            retrieved_at=datetime.now(UTC),
            raw_artifact_path=str(path.relative_to(self.project_dir)),
            checksum=file_checksum(path),
            request_payload_redacted=request,
            request_hash=key,
        )
        provenance_path = self.project_dir / "data/provenance/era5/summer_event.metadata.json"
        provenance_path.parent.mkdir(parents=True, exist_ok=True)
        provenance_path.write_text(provenance.model_dump_json(indent=2) + "\n")
        return parsed, path, key

    def _screen_landsat(self) -> list[SceneCandidate]:
        items = self.landsat.stac.search(
            self.landsat.pilot.bbox_wgs84,
            SEARCH_START,
            SEARCH_END,
            50.0,
        )
        candidates = [candidate_from_item(item) for item in items]
        screened = self.landsat.screen_candidates(items, candidates)
        unique: dict[str, SceneCandidate] = {}
        for candidate in screened:
            unique[candidate.scene_id] = candidate
        return sorted(unique.values(), key=lambda item: (item.acquisition_datetime, item.scene_id))

    @staticmethod
    def _evaluate_candidate(
        candidate: SceneCandidate,
        baseline: ParsedERA5Point,
        summer: ParsedERA5Point,
        thresholds: dict[tuple[int, int], dict[str, float | int | str]],
    ) -> dict[str, Any]:
        row = candidate.model_dump(mode="json")
        rejection = candidate_qa_rejection(candidate)
        row.update(eligible=False, rejection_reason=rejection)
        if rejection:
            return row
        acquisition = candidate.acquisition_datetime.astimezone(UTC)
        reference = nearest_hour(acquisition)
        timestamp = pd.Timestamp(reference)
        row.update(
            landsat_acquisition_time=acquisition.isoformat(),
            era5_reference_time=reference.isoformat(),
            time_offset_minutes=abs((reference - acquisition).total_seconds()) / 60,
        )
        if timestamp not in summer.frame.index:
            row["rejection_reason"] = "ERA5_REFERENCE_HOUR_MISSING"
            return row
        threshold_values = {
            key: float(metadata["temperature_p90_c"])
            for key, metadata in thresholds.items()
        }
        persistence = evaluate_month_hour_persistence(
            summer.frame.air_temperature_c, timestamp, threshold_values
        )
        if not persistence.get("event_window_complete"):
            row["rejection_reason"] = "ERA5_72H_WINDOW_INCOMPLETE"
            return row
        air_c = float(summer.frame.loc[timestamp, "air_temperature_c"])
        reference_baseline = month_same_hour(
            baseline.frame.air_temperature_c, reference.month, reference.hour
        )
        stats = month_hour_statistics(
            baseline.frame.air_temperature_c, reference.month, reference.hour
        )
        intensity = empirical_percentile(air_c, reference_baseline.to_numpy())
        persistence_score, severity = temporal_severity(
            intensity, int(persistence["consecutive_hot_hours_at_reference"])
        )
        row.update(
            eligible=True,
            rejection_reason=None,
            air_temperature_c=air_c,
            historical_median_c=stats["historical_median_c"],
            historical_p90_c=stats["historical_p90_c"],
            historical_p95_c=stats["historical_p95_c"],
            baseline_sample_count=stats["baseline_sample_count"],
            temperature_anomaly_c=air_c - float(stats["historical_median_c"]),
            temperature_percentile=intensity,
            **persistence,
            temporal_intensity_score=intensity,
            temporal_persistence_score=persistence_score,
            temporal_severity_score=severity,
        )
        return row

    def run(self) -> dict[str, Any]:
        source_hash_audit = audit_frozen_source_hashes(self.project_dir)
        baseline, baseline_path = self._baseline()
        summer, summer_path, summer_key = self._summer()
        if (baseline.latitude, baseline.longitude) != (summer.latitude, summer.longitude):
            raise RuntimeError("baseline and summer data returned different ERA5 grid points")
        thresholds = month_hour_p90(baseline.frame.air_temperature_c, MONTHS)
        candidates = self._screen_landsat()
        rows = [
            self._evaluate_candidate(candidate, baseline, summer, thresholds)
            for candidate in candidates
        ]
        ranked = rank_eligible_events(rows)
        if not ranked:
            raise RuntimeError("M4A has no eligible Landsat/ERA5 event candidate")
        for rank, row in enumerate(ranked, 1):
            row["rank"] = rank
        output = self.project_dir / "data/processed/event_selection"
        _write_json(
            output / "m4a_landsat_candidates_2026.json",
            {
                "search_window": [SEARCH_START, SEARCH_END],
                "qa_threshold": QA_THRESHOLD,
                "candidates": rows,
            },
        )
        output.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_parquet(
            output / "m4a_heat_event_candidates_2026.parquet", index=False
        )
        winner = {
            "selection_method": SELECTION_METHOD,
            "search_window": [SEARCH_START, SEARCH_END],
            **ranked[0],
        }
        _write_json(output / "m4a_selected_event_2026.json", winner)
        screening = {
            "total_landsat_candidates": len(rows),
            "qa_eligible_candidates": sum(candidate_qa_rejection(c) is None for c in candidates),
            "temporal_complete_candidates": sum(
                row.get("event_window_complete") is True for row in rows
            ),
            "final_eligible_candidates": len(ranked),
            "rejected_by_qa": sum(
                row.get("rejection_reason") == "PILOT_VALID_FRACTION_BELOW_0.80"
                for row in rows
            ),
            "rejected_missing_st": sum(
                row.get("rejection_reason") == "MISSING_ST_ASSET" for row in rows
            ),
            "rejected_temporal_incomplete": sum(
                row.get("rejection_reason") == "ERA5_72H_WINDOW_INCOMPLETE"
                for row in rows
            ),
            "rejected_other": sum(
                not row.get("eligible")
                and row.get("rejection_reason")
                not in {
                    "PILOT_VALID_FRACTION_BELOW_0.80",
                    "MISSING_ST_ASSET",
                    "ERA5_72H_WINDOW_INCOMPLETE",
                }
                for row in rows
            ),
        }
        _write_json(self.project_dir / "reports/m4a_heat_event_screening.json", screening)
        climatology = {
            "months": list(MONTHS),
            "hours_per_month": 24,
            "month_hour_threshold_count": len(thresholds),
            "quantile_method": QUANTILE_METHOD,
            "thresholds": {
                f"{month:02d}-{hour:02d}": metadata
                for (month, hour), metadata in thresholds.items()
            },
        }
        _write_json(
            self.project_dir / "reports/m4a_month_hour_climatology_audit.json",
            climatology,
        )
        audit = {
            "M4A_STATUS": "PASS",
            "selection_method": SELECTION_METHOD,
            "selected_scene_id": winner["scene_id"],
            "eligible_event_count": len(ranked),
            "top_5_events": ranked[:5],
            "returned_coordinate": [summer.longitude, summer.latitude],
            "baseline_raw_path": str(baseline_path.relative_to(self.project_dir)),
            "baseline_checksum": file_checksum(baseline_path),
            "summer_raw_path": str(summer_path.relative_to(self.project_dir)),
            "summer_checksum": file_checksum(summer_path),
            "summer_request_hash": summer_key,
            "era5_cache_hits": self.era_client.cache_hits,
            "era5_network_reads": self.era_client.network_reads,
            "landsat_cache_hits": self.landsat.cache_hits,
            "landsat_network_reads": self.landsat.network_reads,
            "source_artifact_hash_audit": source_hash_audit["status"],
        }
        _write_json(self.project_dir / "reports/m4a_event_selection_audit.json", audit)
        return {"screening": screening, "winner": winner, "audit": audit}
