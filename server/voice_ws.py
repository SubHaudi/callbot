"""callbot.server.voice_ws — FastAPI WebSocket 음성 라우터 (FR-001, FR-002)

/api/v1/ws/voice 엔드포인트. VoiceServer를 app.state에서 DI.
프로토콜: JSON 메시지 (audio/text/interrupt/end → transcript/response/error/fallback/interrupted)
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)

router = APIRouter()


# ---- Protocol helpers (FR-002) ----

def parse_client_message(raw: str) -> Dict[str, Any]:
    """클라이언트→서버 JSON 메시지 파싱."""
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        return {"type": "error", "message": "Invalid JSON"}

    msg_type = msg.get("type")
    if msg_type not in ("audio", "text", "interrupt", "end"):
        return {"type": "error", "message": f"Unknown message type: {msg_type}"}
    return msg


def make_transcript(text: str, is_final: bool = True) -> Dict[str, Any]:
    return {"type": "transcript", "text": text, "is_final": is_final}


def make_response(text: str, audio_b64: str = "", processing_ms: int = 0) -> Dict[str, Any]:
    resp: Dict[str, Any] = {"type": "response", "text": text, "processing_ms": processing_ms}
    if audio_b64:
        resp["audio"] = audio_b64
    return resp


def make_error(message: str) -> Dict[str, Any]:
    return {"type": "error", "message": message}


def make_interrupted() -> Dict[str, Any]:
    return {"type": "interrupted"}


def make_fallback(message: str) -> Dict[str, Any]:
    return {"type": "fallback", "message": message}


# ---- WebSocket endpoint ----

@router.websocket("/api/v1/ws/voice")
async def voice_websocket(websocket: WebSocket) -> None:
    """음성 WebSocket 엔드포인트 (FR-001)."""
    voice_server = websocket.app.state.voice_server  # DI via app.state

    await websocket.accept()

    # 세션 생성
    try:
        session = voice_server.create_session()
    except RuntimeError as e:
        await websocket.send_text(json.dumps(make_error(str(e))))
        await websocket.close(code=1008, reason="max sessions reached")
        return

    session_id = session.session_id
    logger.info("Voice WS connected: session=%s", session_id)

    try:
        while True:
            raw = await websocket.receive_text()
            msg = parse_client_message(raw)

            if msg["type"] == "error":
                await websocket.send_text(json.dumps(msg))
                continue

            if msg["type"] == "audio":
                audio_bytes = base64.b64decode(msg.get("data", ""))
                result = await voice_server.handle_audio_chunk(session_id, audio_bytes)
                if "error" in result:
                    await websocket.send_text(json.dumps(make_error(result["error"])))
                    continue
                # Drain partial queue
                await _drain_partial_queue(websocket, session)

            elif msg["type"] == "text":
                text = msg.get("text", "")
                result = await voice_server.handle_text(session_id, text)
                await _send_text_result(websocket, result)

            elif msg["type"] == "interrupt":
                result = await voice_server.handle_interrupt(session_id)
                if result.get("status") == "interrupted":
                    await websocket.send_text(json.dumps(make_interrupted()))
                # not_playing → 무시 (ACK 불필요)

            elif msg["type"] == "end":
                # Drain remaining partials first
                await _drain_partial_queue(websocket, session)
                # STT final → Pipeline → TTS → response
                result = await voice_server.handle_end(session_id)
                if "error" in result:
                    await websocket.send_text(json.dumps(make_error(result["error"])))
                else:
                    await _send_end_result(websocket, result)

    except WebSocketDisconnect:
        logger.info("Voice WS disconnected: session=%s", session_id)
    except Exception as e:
        logger.exception("Voice WS error: session=%s", session_id)
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_text(json.dumps(make_error(f"Internal error: {type(e).__name__}")))
    finally:
        voice_server.end_session(session_id)
        logger.info("Voice WS session cleaned up: session=%s", session_id)


async def _drain_partial_queue(ws: WebSocket, session: Any) -> None:
    """세션의 partial_queue에서 모든 partial transcript를 클라이언트로 전송."""
    while True:
        try:
            item = session.partial_queue.get_nowait()
            await ws.send_text(json.dumps(make_transcript(
                text=item["text"],
                is_final=item.get("is_final", False),
            )))
        except asyncio.QueueEmpty:
            break


async def _send_end_result(ws: WebSocket, result: Dict[str, Any]) -> None:
    """handle_end 결과를 프로토콜로 전송 (final transcript + response)."""
    transcript = result.get("transcript", "")
    if transcript:
        await ws.send_text(json.dumps(make_transcript(transcript, is_final=True)))

    await ws.send_text(json.dumps(make_response(
        text=result.get("response_text", ""),
        audio_b64=result.get("audio_b64", ""),
        processing_ms=result.get("processing_ms", 0),
    )))


async def _send_text_result(ws: WebSocket, result: Dict[str, Any]) -> None:
    """handle_text 결과를 FR-002 프로토콜로 전송."""
    if "error" in result:
        await ws.send_text(json.dumps(make_error(result.get("message", result["error"]))))
        return

    await ws.send_text(json.dumps(make_response(
        text=result.get("response_text", ""),
        audio_b64=result.get("audio_b64", ""),
        processing_ms=result.get("processing_ms", 0),
    )))
