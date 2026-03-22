"""callbot.server.voice_ws — FastAPI WebSocket 음성 라우터 (FR-001)

/api/v1/ws/voice 엔드포인트. VoiceServer DI로 주입.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/api/v1/ws/voice")
async def voice_websocket(websocket: WebSocket) -> None:
    """음성 WebSocket 엔드포인트 스켈레톤."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(data)  # echo for now
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
