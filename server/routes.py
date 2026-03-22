"""callbot.server.routes — REST API 라우터"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1", tags=["api"])


class TurnRequest(BaseModel):
    """턴 요청."""
    session_id: Optional[str] = None
    caller_id: str
    text: str


class TurnResponse(BaseModel):
    """턴 응답."""
    session_id: str
    response_text: str
    action_type: str
    context: dict = {}


@router.post("/turn", response_model=TurnResponse)
async def turn_endpoint(body: TurnRequest, request: Request) -> TurnResponse:
    """POST /api/v1/turn — 텍스트 턴 처리."""
    if not getattr(request.app.state, "healthy", False):
        return JSONResponse(
            status_code=503,
            content={"detail": "Service unavailable — dependencies not initialized"},
        )

    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        return JSONResponse(
            status_code=503,
            content={"detail": "Pipeline not initialized"},
        )
    result = await pipeline.process(
        session_id=body.session_id,
        caller_id=body.caller_id,
        text=body.text,
    )

    return TurnResponse(
        session_id=result.session_id,
        response_text=result.response_text,
        action_type=result.action_type,
        context=result.context,
    )
