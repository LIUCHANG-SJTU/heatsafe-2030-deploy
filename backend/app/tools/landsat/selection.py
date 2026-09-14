from __future__ import annotations

from app.models.landsat import SceneCandidate


def select_best_scene(candidates: list[SceneCandidate]) -> SceneCandidate:
    eligible = [
        candidate
        for candidate in candidates
        if candidate.st_asset_available
        and candidate.qa_asset_available
        and candidate.pilot_valid_fraction is not None
    ]
    if not eligible:
        raise ValueError("no candidate has ST, QA_PIXEL, and AOI QA coverage")
    return max(
        eligible,
        key=lambda candidate: (
            candidate.pilot_valid_fraction,
            candidate.acquisition_datetime,
            -candidate.scene_cloud_cover,
        ),
    )

