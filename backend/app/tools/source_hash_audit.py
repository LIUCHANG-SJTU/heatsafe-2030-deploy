from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


FROZEN_SOURCE_HASHES = {
    "data/processed/worldpop/worldpop_population_2026.json": "99ba9ed803ea9efdd51bf309b2e99053cb1f6545211eea04faa710cb32a90707",
    "data/processed/worldpop/worldpop_population_2026.parquet": "29488664ee2f39b0f0242274df6710f892749c24ab0f1361e98ea429da36aadf",
    "reports/m1_worldpop_audit.json": "10922e4e78feb945e95b7dda7c4675e495551dc411d4f583dfb85647f417ba6e",
    "data/processed/landsat/landsat_lst_pilot_2026.json": "c2205f867730bc2955e11f0b38175f7b3e6fae97b950803a4545df06aa53000b",
    "data/processed/landsat/landsat_lst_pilot_2026.parquet": "27c83fcd1b0e7fab420595abccec5b588f36ffa3e72334a8949366b3ca70e0dc",
    "data/processed/sentinel2/sentinel2_vegetation_pilot_2026.json": "23eada446c6da5fc0536a45f8446a3b0de3b8dbe3c3e1c237b30563bbfb175d4",
    "data/processed/sentinel2/sentinel2_vegetation_pilot_2026.parquet": "a455567d0a4a8e5493cca0afb05e001b6bbcf32aea285e0f02fd66471f852326",
    "data/raw/era5/responses/baseline-1991-2020-e70927bc00bd3adbe626847556e0ef18434f0195141d4871e63e6899ded99100.nc": "331a5c48310c7011b0df8afbc5262fa2d50298ee5b1ffec039f49b2c0b715071",
    "data/processed/event_selection/m4a_selected_event_2026.json": "6b1845462145955a0f3ffd03a9f1a14fbfe4ee1177cfee293769201c92bf4091",
    "data/processed/demo_aoi_selection/m4b_satellite_top8.json": "edd72f203a9cee4028de6fb6cd94a8b5845933ef2e4814602a75a6dbc0aace53",
}


def audit_frozen_source_hashes(project_dir: Path) -> dict[str, Any]:
    artifacts: dict[str, dict[str, Any]] = {}
    for relative, expected in FROZEN_SOURCE_HASHES.items():
        path = project_dir / relative
        current = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        artifacts[relative] = {
            "expected_sha256": expected,
            "current_sha256": current,
            "unchanged": current == expected,
        }
    passed = all(item["unchanged"] for item in artifacts.values())
    report = {"status": "PASS" if passed else "FAIL", "artifacts": artifacts}
    path = project_dir / "reports/m3b1_m4a_source_artifact_hash_audit.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not passed:
        raise RuntimeError("one or more frozen source artifact hashes changed")
    return report
