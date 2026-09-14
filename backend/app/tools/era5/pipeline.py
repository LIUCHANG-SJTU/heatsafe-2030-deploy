from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.models.era5 import ERA5BaselineStatistics, ERA5TemporalContext
from app.models.hazard import SpatiotemporalHazardArtifact, SpatiotemporalHazardGrid
from app.models.landsat import LandsatArtifact
from app.risk.hazard import spatiotemporal_hazard
from app.risk.spatial_heat import spatial_heat_scores
from app.tools.method_audit import run_m3b1_audit

from .cache import ERA5Cache, file_checksum
from .client import ERA5CDSClient
from .climatology import QUANTILE_METHOD, baseline_statistics, hourly_july_p90
from .contract import DATASET_ID, REQUEST_LATITUDE, REQUEST_LONGITUDE, request_for
from .humidity import relative_humidity_percent
from .parsing import ParsedERA5Point, parse_era5_point
from .percentile import average_rank_01, empirical_percentile
from .persistence import evaluate_persistence
from .provenance import ERA5ArtifactProvenance
from .temperature import nearest_hour
from .temporal_score import temporal_severity


SATELLITE_REFERENCE_TIME = datetime(2026, 7, 31, 2, 31, 22, tzinfo=UTC)
BASELINE_RANGE = "1991-01-01/2020-12-31"
EVENT_RANGE = "2026-07-27/2026-08-01"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _expected_same_hour_samples(start_year: int, end_year: int) -> int:
    timestamps = pd.date_range(
        f"{start_year}-01-01", f"{end_year + 1}-01-01", freq="D", inclusive="left"
    )
    return int(np.sum(timestamps.month == 7))


def _spearman(left: np.ndarray, right: np.ndarray) -> float:
    left_rank = average_rank_01(left)
    right_rank = average_rank_01(right)
    return float(np.corrcoef(left_rank, right_rank)[0, 1])


def _top_overlap(left: np.ndarray, right: np.ndarray, count: int = 10) -> float:
    left_top = set(np.argsort(left, kind="stable")[-count:])
    right_top = set(np.argsort(right, kind="stable")[-count:])
    return len(left_top & right_top) / count


class ERA5M3BPipeline:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.cache = ERA5Cache(project_dir / "data/raw/era5")
        self.client = ERA5CDSClient(DATASET_ID, self.cache)

    def acquire_baseline(self) -> tuple[Path, ParsedERA5Point, str]:
        path, key = self.client.retrieve(request_for(BASELINE_RANGE), "baseline-1991-2020")
        return path, parse_era5_point(path), key

    def acquire_event(self) -> tuple[Path, ParsedERA5Point, str]:
        path, key = self.client.retrieve(request_for(EVENT_RANGE), "event-2026")
        return path, parse_era5_point(path), key

    def _provenance(
        self,
        label: str,
        date_range: str,
        raw_path: Path,
        parsed: ParsedERA5Point,
        key: str,
    ) -> Path:
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
            date_range=date_range,
            retrieved_at=datetime.now(UTC),
            raw_artifact_path=str(raw_path.relative_to(self.project_dir)),
            checksum=file_checksum(raw_path),
            request_payload_redacted=request_for(date_range),
            request_hash=key,
        )
        path = self.project_dir / f"data/provenance/era5/{label}.metadata.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(provenance.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return path

    def process(
        self,
        baseline_path: Path,
        baseline: ParsedERA5Point,
        baseline_key: str,
        event_path: Path,
        event: ParsedERA5Point,
        event_key: str,
    ) -> ERA5TemporalContext:
        if (baseline.latitude, baseline.longitude) != (event.latitude, event.longitude):
            raise RuntimeError("baseline and event returned different ERA5 grid points")
        reference_time = nearest_hour(SATELLITE_REFERENCE_TIME)
        reference_timestamp = pd.Timestamp(reference_time)
        if reference_timestamp not in event.frame.index:
            raise RuntimeError("event artifact lacks nearest ERA5 reference hour")
        baseline_temperature = baseline.frame.air_temperature_c
        stats = baseline_statistics(baseline_temperature, reference_time.hour)
        thresholds = hourly_july_p90(baseline_temperature)
        threshold_values = {
            hour: float(metadata["temperature_p90_c"])
            for hour, metadata in thresholds.items()
        }
        persistence = evaluate_persistence(
            event.frame.air_temperature_c, reference_timestamp, threshold_values
        )
        if not persistence.get("event_window_complete"):
            raise RuntimeError("BLOCKED_BASELINE_INCOMPLETE: event lacks one or more of 72 hours")
        target = event.frame.loc[reference_timestamp]
        air_c = float(target.air_temperature_c)
        dewpoint_c = float(target.dewpoint_temperature_c)
        humidity = relative_humidity_percent(air_c, dewpoint_c)
        reference_baseline = baseline_temperature[
            (baseline_temperature.index.month == 7)
            & (baseline_temperature.index.hour == reference_time.hour)
        ].dropna()
        intensity = empirical_percentile(air_c, reference_baseline.to_numpy())
        persistence_score, severity = temporal_severity(
            intensity, int(persistence["consecutive_hot_hours_at_reference"])
        )
        source_id = f"era5:{DATASET_ID}:{baseline.longitude:.1f},{baseline.latitude:.1f}:2026-07-31T03Z"
        context_id = "era5-temporal:pilot_v1:2026-07-31T03Z"
        context = ERA5TemporalContext(
            source_id=source_id,
            temporal_context_id=context_id,
            dataset_id=DATASET_ID,
            requested_latitude=REQUEST_LATITUDE,
            requested_longitude=REQUEST_LONGITUDE,
            returned_latitude=baseline.latitude,
            returned_longitude=baseline.longitude,
            spatial_selection_method="CDS nearest 0.1 degree ERA5-Land grid point",
            satellite_reference_time=SATELLITE_REFERENCE_TIME,
            era5_reference_time=reference_time,
            time_offset_minutes=abs((reference_time - SATELLITE_REFERENCE_TIME).total_seconds()) / 60,
            air_temperature_c=air_c,
            dewpoint_temperature_c=dewpoint_c,
            relative_humidity_percent=humidity,
            historical_median_c=stats["historical_median_c"],
            historical_mean_c=stats["historical_mean_c"],
            historical_p90_c=stats["historical_p90_c"],
            historical_p95_c=stats["historical_p95_c"],
            historical_std_c=stats["historical_std_c"],
            baseline_sample_count=stats["baseline_sample_count"],
            temperature_anomaly_c=air_c - stats["historical_median_c"],
            temperature_percentile=intensity,
            hot_hours_last_24h=int(persistence["hot_hours_last_24h"]),
            hot_hours_last_72h=int(persistence["hot_hours_last_72h"]),
            consecutive_hot_hours_at_reference=int(persistence["consecutive_hot_hours_at_reference"]),
            max_consecutive_hot_hours_last_72h=int(persistence["max_consecutive_hot_hours_last_72h"]),
            event_window_complete=True,
            temporal_intensity_score=intensity,
            temporal_persistence_score=persistence_score,
            temporal_severity_score=severity,
        )
        processed = self.project_dir / "data/processed/era5"
        processed.mkdir(parents=True, exist_ok=True)
        baseline.frame.to_parquet(processed / "era5_baseline_1991_2020.parquet")
        event.frame.to_parquet(processed / "era5_event_2026.parquet")
        _write_json(processed / "era5_hourly_p90.json", {f"{hour:02d}": value for hour, value in thresholds.items()})
        (processed / "era5_temporal_context.json").write_text(context.model_dump_json(indent=2) + "\n", encoding="utf-8")
        self._provenance("baseline", BASELINE_RANGE, baseline_path, baseline, baseline_key)
        self._provenance("event", EVENT_RANGE, event_path, event, event_key)
        expected = _expected_same_hour_samples(1991, 2020)
        baseline_audit = ERA5BaselineStatistics(
            baseline_start="1991-01-01",
            baseline_end="2020-12-31",
            reference_utc_hour=reference_time.hour,
            expected_july_same_hour_samples=expected,
            actual_july_same_hour_samples=stats["baseline_sample_count"],
            missing_samples=max(0, expected - stats["baseline_sample_count"]),
            historical_temperature_mean_c=stats["historical_mean_c"],
            historical_temperature_median_c=stats["historical_median_c"],
            historical_temperature_p90_c=stats["historical_p90_c"],
            historical_temperature_p95_c=stats["historical_p95_c"],
            historical_temperature_std_c=stats["historical_std_c"],
        )
        _write_json(
            self.project_dir / "reports/m3b_era5_baseline_audit.json",
            baseline_audit.model_dump(mode="json"),
        )
        _write_json(
            self.project_dir / "reports/m3b_era5_event_audit.json",
            context.model_dump(mode="json"),
        )
        self._build_hazard_and_analysis(context)
        self._write_sensitivity(context)
        return context

    def _build_hazard_and_analysis(self, context: ERA5TemporalContext) -> None:
        landsat_path = self.project_dir / "data/processed/landsat/landsat_lst_pilot_2026.json"
        landsat = LandsatArtifact.model_validate_json(landsat_path.read_text())
        lst = np.array([grid.lst_median_c for grid in landsat.grids], dtype=float)
        spatial = spatial_heat_scores(lst)
        hazard_scores = spatiotemporal_hazard(spatial, context.temporal_severity_score)
        hazard = SpatiotemporalHazardArtifact(
            temporal_context_id=context.temporal_context_id,
            source_id=f"hazard:{landsat.source_id}:{context.source_id}",
            grids=[
                SpatiotemporalHazardGrid(
                    grid_id=grid.grid_id,
                    spatial_heat_score=float(spatial[index]),
                    temporal_context_id=context.temporal_context_id,
                    temporal_severity_score=context.temporal_severity_score,
                    hazard_score=float(hazard_scores[index]),
                )
                for index, grid in enumerate(landsat.grids)
            ],
        )
        hazard_dir = self.project_dir / "data/processed/hazard"
        hazard_dir.mkdir(parents=True, exist_ok=True)
        (hazard_dir / "spatiotemporal_hazard_pilot_2026.json").write_text(hazard.model_dump_json(indent=2) + "\n")
        pd.DataFrame([grid.model_dump(mode="json") for grid in hazard.grids]).to_parquet(
            hazard_dir / "spatiotemporal_hazard_pilot_2026.parquet", index=False
        )
        run_m3b1_audit(self.project_dir)

    def _write_sensitivity(self, context: ERA5TemporalContext) -> None:
        landsat = LandsatArtifact.model_validate_json(
            (self.project_dir / "data/processed/landsat/landsat_lst_pilot_2026.json").read_text()
        )
        spatial = spatial_heat_scores(np.array([grid.lst_median_c for grid in landsat.grids]))
        temporal_variants = {}
        for weight in (0.6, 0.7, 0.8):
            _, score = temporal_severity(
                context.temporal_intensity_score,
                context.consecutive_hot_hours_at_reference,
                weight,
            )
            temporal_variants[f"{weight:.1f}/{1-weight:.1f}"] = score
        baseline_hazard = spatiotemporal_hazard(spatial, context.temporal_severity_score, 0.7)
        hazard_variants = {}
        for weight in (0.6, 0.7, 0.8):
            values = spatiotemporal_hazard(spatial, context.temporal_severity_score, weight)
            shift = np.abs(values - baseline_hazard)
            hazard_variants[f"{weight:.1f}/{1-weight:.1f}"] = {
                "hazard_score_min": float(np.min(values)),
                "hazard_score_mean": float(np.mean(values)),
                "hazard_score_max": float(np.max(values)),
                "mean_absolute_score_difference": float(np.mean(shift)),
                "max_absolute_score_difference": float(np.max(shift)),
                "spearman": _spearman(baseline_hazard, values),
                "top_10_overlap": _top_overlap(baseline_hazard, values),
            }
        _write_json(
            self.project_dir / "reports/m3b_hazard_sensitivity.json",
            {
                "temporal_intensity_persistence_weights": temporal_variants,
                "spatial_temporal_hazard_weights": hazard_variants,
                "rank_invariance_expected": True,
                "rank_invariance_reason": "ERA5 temporal severity is one shared constant across pilot_v1.",
            },
        )

    def run(self) -> ERA5TemporalContext:
        baseline_path, baseline, baseline_key = self.acquire_baseline()
        event_path, event, event_key = self.acquire_event()
        return self.process(
            baseline_path,
            baseline,
            baseline_key,
            event_path,
            event,
            event_key,
        )
