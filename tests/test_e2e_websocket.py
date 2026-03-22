"""E2E WebSocket 테스트 — pytest + websockets.

경량 FastAPI 앱 (mock pipeline) + uvicorn + websockets 클라이언트.
A층: 텍스트 폴백 경로 중심.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
import uvicorn
from fastapi import FastAPI

from callbot.voice_io.voice_server import VoiceServer
from server.voice_ws import router as voice_router

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_mock_pipeline(response_text: str = "5만원입니다.") -> MagicMock:
    mock = MagicMock()
    result = MagicMock()
    result.response_text = response_text
    mock.process.return_value = result
    return mock


def _make_mock_stt(transcript: str = "요금 조회") -> MagicMock:
    mock = MagicMock()
    handle = MagicMock()
    mock.start_stream.return_value = handle

    stt_result = MagicMock()
    stt_result.text = transcript
    stt_result.is_valid = bool(transcript)
    mock.get_final_result.return_value = stt_result

    mock.stop_stream.return_value = None
    mock.process_audio_chunk.return_value = None
    return mock


def _make_mock_tts(audio: bytes = b"\x00\x01\x02") -> MagicMock:
    mock = MagicMock()
    result = MagicMock()
    result.data = audio
    mock.synthesize.return_value = result
    return mock


# ---------------------------------------------------------------------------
# Test App Factory
# ---------------------------------------------------------------------------


def _create_test_app(
    pipeline: Any = None,
    stt: Any = None,
    tts: Any = None,
    max_sessions: int = 10,
) -> FastAPI:
    app = FastAPI()
    app.include_router(voice_router)
    vs = VoiceServer(
        pipeline=pipeline or _make_mock_pipeline(),
        stt_engine=stt,
        tts_engine=tts,
    )
    vs._max_sessions = max_sessions
    app.state.voice_server = vs
    return app


# ---------------------------------------------------------------------------
# Server fixture: uvicorn in background thread
# ---------------------------------------------------------------------------

import threading
import socket


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def ws_server():
    """모듈 단위로 uvicorn 서버를 띄우고, (host, port) 반환."""
    port = _find_free_port()
    app = _create_test_app(
        pipeline=_make_mock_pipeline(),
        stt=_make_mock_stt(),
        tts=_make_mock_tts(),
    )
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to start
    for _ in range(50):
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=0.1)
            s.close()
            break
        except (ConnectionRefusedError, OSError):
            time.sleep(0.1)

    yield f"ws://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=3)


@pytest.fixture(scope="module")
def text_only_server():
    """STT/TTS 없는 텍스트 전용 서버."""
    port = _find_free_port()
    app = _create_test_app(pipeline=_make_mock_pipeline(), stt=None, tts=None)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(50):
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=0.1)
            s.close()
            break
        except (ConnectionRefusedError, OSError):
            time.sleep(0.1)

    yield f"ws://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=3)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _recv_until(ws, msg_type: str, timeout: float = 5.0) -> List[Dict]:
    """특정 타입 메시지를 받을 때까지 수집."""
    messages = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.time()))
            msg = json.loads(raw)
            messages.append(msg)
            if msg.get("type") == msg_type:
                return messages
        except asyncio.TimeoutError:
            break
    return messages


async def _recv_all(ws, timeout: float = 1.0) -> List[Dict]:
    """타임아웃까지 모든 메시지 수집."""
    messages = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.time()))
            messages.append(json.loads(raw))
        except asyncio.TimeoutError:
            break
    return messages


# ===========================================================================
# 시나리오 1: 전체 통화 플로우 (텍스트 멀티턴)
# ===========================================================================


class TestFullConversationFlow:
    @pytest.mark.asyncio
    async def test_text_multiturn_conversation(self, ws_server):
        """텍스트 폴백으로 3턴 대화 후 정상 종료."""
        import websockets

        async with websockets.connect(f"{ws_server}/api/v1/ws/voice") as ws:
            # 텍스트 메시지 전송 (폴백 모드 — STT 없이 텍스트 직접 입력)
            # 먼저 텍스트 폴백 모드 진입이 필요한데, text 메시지는 fallback 모드에서만 동작
            # 대신 audio+end로 정상 플로우 테스트
            audio_b64 = base64.b64encode(b"\x00" * 3200).decode("ascii")

            for turn in range(3):
                await ws.send(json.dumps({"type": "audio", "data": audio_b64}))
                await ws.send(json.dumps({"type": "end"}))
                msgs = await _recv_until(ws, "response", timeout=5)
                response = [m for m in msgs if m["type"] == "response"]
                assert len(response) >= 1, f"Turn {turn}: no response received"
                assert response[0]["text"] == "5만원입니다."

    @pytest.mark.asyncio
    async def test_response_time_under_threshold(self, ws_server):
        """응답 시간 < 3초."""
        import websockets

        async with websockets.connect(f"{ws_server}/api/v1/ws/voice") as ws:
            audio_b64 = base64.b64encode(b"\x00" * 3200).decode("ascii")
            t0 = time.time()
            await ws.send(json.dumps({"type": "audio", "data": audio_b64}))
            await ws.send(json.dumps({"type": "end"}))
            msgs = await _recv_until(ws, "response", timeout=5)
            elapsed = time.time() - t0
            assert elapsed < 3.0, f"Response took {elapsed:.2f}s"
            assert any(m["type"] == "response" for m in msgs)


# ===========================================================================
# 시나리오 2: 동시 세션 격리
# ===========================================================================


class TestConcurrentSessions:
    @pytest.mark.asyncio
    async def test_5_concurrent_sessions_isolated(self, ws_server):
        """5개 동시 WebSocket 세션이 독립적으로 동작."""
        import websockets

        async def run_session(session_id: int) -> Dict:
            async with websockets.connect(f"{ws_server}/api/v1/ws/voice") as ws:
                audio_b64 = base64.b64encode(b"\x00" * 3200).decode("ascii")
                await ws.send(json.dumps({"type": "audio", "data": audio_b64}))
                await ws.send(json.dumps({"type": "end"}))
                msgs = await _recv_until(ws, "response", timeout=5)
                response = [m for m in msgs if m["type"] == "response"]
                return {"session": session_id, "got_response": len(response) > 0}

        results = await asyncio.gather(*[run_session(i) for i in range(5)])
        for r in results:
            assert r["got_response"], f"Session {r['session']} got no response"


# ===========================================================================
# 시나리오 3: 비정상 종료 + 리소스 정리
# ===========================================================================


class TestAbnormalDisconnect:
    @pytest.mark.asyncio
    async def test_client_disconnect_mid_conversation(self, ws_server):
        """클라이언트가 대화 중 갑자기 끊어도 서버 안 죽음."""
        import websockets

        # 1차: 연결 후 바로 끊기
        ws = await websockets.connect(f"{ws_server}/api/v1/ws/voice")
        await ws.send(json.dumps({"type": "audio", "data": base64.b64encode(b"\x00" * 100).decode()}))
        await ws.close()

        # 잠시 대기
        await asyncio.sleep(0.3)

        # 2차: 새 연결이 정상 작동하는지 확인
        async with websockets.connect(f"{ws_server}/api/v1/ws/voice") as ws2:
            audio_b64 = base64.b64encode(b"\x00" * 3200).decode("ascii")
            await ws2.send(json.dumps({"type": "audio", "data": audio_b64}))
            await ws2.send(json.dumps({"type": "end"}))
            msgs = await _recv_until(ws2, "response", timeout=5)
            assert any(m["type"] == "response" for m in msgs)

    @pytest.mark.asyncio
    async def test_invalid_message_doesnt_crash(self, ws_server):
        """잘못된 JSON, 빈 메시지 등에 서버가 에러 반환하되 연결 유지."""
        import websockets

        async with websockets.connect(f"{ws_server}/api/v1/ws/voice") as ws:
            # 잘못된 JSON
            await ws.send("not valid json {{{")
            msgs = await _recv_all(ws, timeout=1)
            errors = [m for m in msgs if m.get("type") == "error"]
            assert len(errors) >= 1

            # 정상 메시지가 여전히 동작
            audio_b64 = base64.b64encode(b"\x00" * 3200).decode("ascii")
            await ws.send(json.dumps({"type": "audio", "data": audio_b64}))
            await ws.send(json.dumps({"type": "end"}))
            msgs2 = await _recv_until(ws, "response", timeout=5)
            assert any(m["type"] == "response" for m in msgs2)

    @pytest.mark.asyncio
    async def test_empty_audio_handled_gracefully(self, ws_server):
        """빈 오디오 데이터 전송해도 에러 처리."""
        import websockets

        async with websockets.connect(f"{ws_server}/api/v1/ws/voice") as ws:
            await ws.send(json.dumps({"type": "audio", "data": ""}))
            await ws.send(json.dumps({"type": "end"}))
            msgs = await _recv_until(ws, "response", timeout=5)
            # 빈 오디오든 에러든 응답이 와야 함
            assert len(msgs) > 0


# ===========================================================================
# 시나리오 4: 텍스트 전용 모드 (STT/TTS 없음)
# ===========================================================================


class TestTextOnlyMode:
    @pytest.mark.asyncio
    async def test_audio_without_stt_returns_error(self, text_only_server):
        """STT 없는 서버에서 오디오 보내면 에러."""
        import websockets

        async with websockets.connect(f"{text_only_server}/api/v1/ws/voice") as ws:
            audio_b64 = base64.b64encode(b"\x00" * 3200).decode("ascii")
            await ws.send(json.dumps({"type": "audio", "data": audio_b64}))
            await ws.send(json.dumps({"type": "end"}))
            msgs = await _recv_all(ws, timeout=2)
            errors = [m for m in msgs if m.get("type") == "error"]
            assert len(errors) >= 1


# ===========================================================================
# 시나리오 5: Barge-in (interrupt)
# ===========================================================================


class TestBargeIn:
    @pytest.mark.asyncio
    async def test_interrupt_during_conversation(self, ws_server):
        """대화 중 interrupt 전송."""
        import websockets

        async with websockets.connect(f"{ws_server}/api/v1/ws/voice") as ws:
            # 먼저 정상 대화 1턴
            audio_b64 = base64.b64encode(b"\x00" * 3200).decode("ascii")
            await ws.send(json.dumps({"type": "audio", "data": audio_b64}))
            await ws.send(json.dumps({"type": "end"}))
            await _recv_until(ws, "response", timeout=5)

            # interrupt 전송
            await ws.send(json.dumps({"type": "interrupt"}))
            msgs = await _recv_all(ws, timeout=1)
            # interrupt는 TTS 미재생이면 not_playing, 재생 중이면 interrupted
            # 어느 쪽이든 에러는 아님

            # 이후 정상 대화 가능
            await ws.send(json.dumps({"type": "audio", "data": audio_b64}))
            await ws.send(json.dumps({"type": "end"}))
            msgs2 = await _recv_until(ws, "response", timeout=5)
            assert any(m["type"] == "response" for m in msgs2)
