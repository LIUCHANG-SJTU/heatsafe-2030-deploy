from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.action.models import GridActionPlan, HotspotActionOverview
from app.action.service import ActionRecommendationService
from app.agent.evidence_ledger import EvidenceLedger
from app.dependencies import get_action_recommendation_service


router = APIRouter(prefix="/api/v1/actions", tags=["actions"])


@router.get("/grid/{grid_id}", response_model=GridActionPlan)
async def get_grid_actions(
    grid_id: str,
    service: ActionRecommendationService = Depends(get_action_recommendation_service),
) -> GridActionPlan:
    try:
        result = EvidenceLedger().append(service.recommend_for_grid(grid_id))
    except KeyError as error:
        raise HTTPException(status_code=404, detail="demo grid not found") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return GridActionPlan.model_validate(result.data)


@router.get("/hotspots", response_model=HotspotActionOverview)
async def get_hotspot_actions(
    limit: int = Query(default=5, ge=1, le=10),
    service: ActionRecommendationService = Depends(get_action_recommendation_service),
) -> HotspotActionOverview:
    result = EvidenceLedger().append(service.recommend_for_hotspots(limit))
    return HotspotActionOverview.model_validate(result.data)
