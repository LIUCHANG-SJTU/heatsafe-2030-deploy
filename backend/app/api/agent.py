from __future__ import annotations

import json
import asyncio
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.agent.orchestrator_v1 import GroundedAgent
from app.agent.config import agent_settings
from app.agent.evidence import EvidenceFact
from app.agent.schemas import AgentQueryRequest, AgentQueryResponse
from app.agent.localization import agent_status_message
from app.agent.validator import AgentResponseValidator
from app.dependencies import get_grounded_agent


router = APIRouter(prefix="/api/v1/agent", tags=["agent"])
_concurrency = asyncio.Semaphore(agent_settings.max_concurrent)


@router.get("/status")
async def agent_status(agent: GroundedAgent = Depends(get_grounded_agent)) -> dict:
    return agent.status()


@router.post("/query", response_model=AgentQueryResponse)
async def agent_query(payload: AgentQueryRequest, agent: GroundedAgent = Depends(get_grounded_agent)) -> AgentQueryResponse:
    try:
        if _concurrency._value <= 0:  # bounded public endpoint; no queue growth during demos
            raise HTTPException(status_code=429, detail="AGENT_BUSY")
        async with _concurrency:
            response = await agent.answer(payload)
        _validate_visible_response(response)
        return response
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/stream")
async def agent_stream(payload: AgentQueryRequest, request: Request, agent: GroundedAgent = Depends(get_grounded_agent)) -> StreamingResponse:
    request_id = str(uuid.uuid4())

    async def events() -> AsyncIterator[str]:
        yield _event("request", {"request_id": request_id})
        yield _event("status", {"message": agent_status_message(payload.context.locale, "reading")})
        try:
            if _concurrency._value <= 0:
                message = "HeatSafe Agent 正忙，请稍后再试。" if payload.context.locale == "zh-CN" else "HeatSafe Agent is busy. Please try again shortly."
                yield _event("error", {"request_id": request_id, "code": "AGENT_BUSY", "message": message})
                return
            async with _concurrency:
                response = await agent.answer(payload, request_id=request_id)
            # Defense in depth: validate the exact string and Evidence set that
            # will cross the API boundary before emitting any user-visible data.
            _validate_visible_response(response)
            for trace in response.tool_trace:
                yield _event("tool", trace.model_dump())
            if response.evidence:
                yield _event("evidence", {"items": response.evidence})
            yield _event("status", {"message": agent_status_message(payload.context.locale, "validating")})
            # The answer is validated before any token is exposed to the client.
            words = response.answer.split(" ")
            for index, word in enumerate(words):
                if await request.is_disconnected():
                    return
                yield _event("token", {"text": word + (" " if index < len(words) - 1 else "")})
            yield _event("done", response.model_dump())
        except Exception as error:
            if isinstance(error, ValueError) and str(error).startswith("visible response failed validation:"):
                detail = str(error).removeprefix("visible response failed validation: ")
                message = (
                    f"HeatSafe Agent 响应验证失败：{detail}"
                    if payload.context.locale == "zh-CN"
                    else f"HeatSafe Agent response validation failed: {detail}"
                )
            else:
                message = "HeatSafe Agent 请求失败。" if payload.context.locale == "zh-CN" else "HeatSafe Agent request failed."
            yield _event("error", {"request_id": request_id, "code": "AGENT_REQUEST_FAILED", "message": message})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _validate_visible_response(response: AgentQueryResponse) -> None:
    evidence = [EvidenceFact.model_validate(item) for item in response.evidence]
    validation = AgentResponseValidator().validate(response.answer, evidence, response.map_actions)
    if validation.status != "PASS":
        raise ValueError("visible response failed validation: " + "; ".join(validation.errors))
