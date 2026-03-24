"""callbot.server.demo_routes — E2E 데모 시나리오 API 라우터.

Phase Q: /api/v1/demo/* 엔드포인트.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from server.demo_scenarios import (
    ScenarioResult,
    TurnResultDetail,
    list_scenarios,
    run_scenario,
    SCENARIOS,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/demo", tags=["demo"])


class ScenarioListItem(BaseModel):
    id: str
    name: str
    description: str
    category: str
    turn_count: int


class TurnDetail(BaseModel):
    turn_number: int
    user_text: str
    bot_response: str
    action_type: str
    expected_intent: str | None
    actual_intent: str | None
    intent_match: bool
    response_time_ms: float


class ScenarioRunResponse(BaseModel):
    scenario_id: str
    scenario_name: str
    success: bool
    session_id: str
    turns: list[TurnDetail]
    total_time_ms: float
    avg_response_time_ms: float
    intent_accuracy: float
    error: str | None = None


@router.get("/scenarios", response_model=list[ScenarioListItem])
async def get_scenarios():
    """데모 시나리오 목록 조회."""
    return list_scenarios()


@router.post("/scenarios/{scenario_id}/run", response_model=ScenarioRunResponse)
async def run_demo_scenario(scenario_id: str, request: Request):
    """시나리오 실행."""
    if scenario_id not in SCENARIOS:
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_id}")

    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")

    result = await run_scenario(scenario_id, pipeline)
    return ScenarioRunResponse(
        scenario_id=result.scenario_id,
        scenario_name=result.scenario_name,
        success=result.success,
        session_id=result.session_id,
        turns=[
            TurnDetail(
                turn_number=t.turn_number,
                user_text=t.user_text,
                bot_response=t.bot_response,
                action_type=t.action_type,
                expected_intent=t.expected_intent,
                actual_intent=t.actual_intent,
                intent_match=t.intent_match,
                response_time_ms=t.response_time_ms,
            )
            for t in result.turns
        ],
        total_time_ms=result.total_time_ms,
        avg_response_time_ms=result.avg_response_time_ms,
        intent_accuracy=result.intent_accuracy,
        error=result.error,
    )


@router.post("/scenarios/run-all", response_model=list[ScenarioRunResponse])
async def run_all_scenarios(request: Request):
    """모든 시나리오 순차 실행."""
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")

    results = []
    for sid in SCENARIOS:
        r = await run_scenario(sid, pipeline)
        results.append(ScenarioRunResponse(
            scenario_id=r.scenario_id,
            scenario_name=r.scenario_name,
            success=r.success,
            session_id=r.session_id,
            turns=[
                TurnDetail(
                    turn_number=t.turn_number,
                    user_text=t.user_text,
                    bot_response=t.bot_response,
                    action_type=t.action_type,
                    expected_intent=t.expected_intent,
                    actual_intent=t.actual_intent,
                    intent_match=t.intent_match,
                    response_time_ms=t.response_time_ms,
                )
                for t in r.turns
            ],
            total_time_ms=r.total_time_ms,
            avg_response_time_ms=r.avg_response_time_ms,
            intent_accuracy=r.intent_accuracy,
            error=r.error,
        ))
    return results
