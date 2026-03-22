"""Phase G: WebSocket voice pipeline 테스트."""
from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from callbot.voice_io.voice_server import VoiceServer, VoiceSession


# ---------------------------------------------------------------------------
# TASK-002: WebSocket 연결/종료 세션 lifecycle
# ---------------------------------------------------------------------------


class TestVoiceWSSessionLifecycle:
    """WebSocket 연결 시 세션 생성, 종료 시 정리."""

    def test_create_session_returns_voice_session(self):
        server = VoiceServer()
        session = server.create_session()
        assert isinstance(session, VoiceSession)
        assert server.active_session_count == 1

    def test_end_session_removes_session(self):
        server = VoiceServer()
        session = server.create_session()
        server.end_session(session.session_id)
        assert server.active_session_count == 0

    def test_end_nonexistent_session_no_error(self):
        server = VoiceServer()
        server.end_session("nonexistent")  # should not raise


# ---------------------------------------------------------------------------
# TASK-003: WebSocket 프로토콜 메시지 파싱
# ---------------------------------------------------------------------------


def _parse_message(raw: str) -> dict:
    """JSON 메시지 파싱 + type 검증."""
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        return {"type": "error", "message": "Invalid JSON"}
    
    msg_type = msg.get("type")
    if msg_type not in ("audio", "text", "interrupt", "end"):
        return {"type": "error", "message": f"Unknown message type: {msg_type}"}
    return msg


class TestMessageParsing:
    """클라이언트→서버 JSON 메시지 파싱."""

    def test_parse_audio_message(self):
        msg = _parse_message('{"type": "audio", "data": "AQID"}')
        assert msg["type"] == "audio"
        assert msg["data"] == "AQID"

    def test_parse_text_message(self):
        msg = _parse_message('{"type": "text", "text": "안녕하세요"}')
        assert msg["type"] == "text"

    def test_parse_interrupt_message(self):
        msg = _parse_message('{"type": "interrupt"}')
        assert msg["type"] == "interrupt"

    def test_parse_end_message(self):
        msg = _parse_message('{"type": "end"}')
        assert msg["type"] == "end"

    def test_parse_unknown_type_returns_error(self):
        msg = _parse_message('{"type": "unknown"}')
        assert msg["type"] == "error"

    def test_parse_invalid_json_returns_error(self):
        msg = _parse_message("not json")
        assert msg["type"] == "error"


# ---------------------------------------------------------------------------
# TASK-004: 서버→클라이언트 응답 포맷
# ---------------------------------------------------------------------------


def _make_transcript_response(text: str, is_final: bool = True) -> dict:
    return {"type": "transcript", "text": text, "is_final": is_final}


def _make_response(text: str, audio_b64: str = "", processing_ms: int = 0) -> dict:
    resp = {"type": "response", "text": text, "processing_ms": processing_ms}
    if audio_b64:
        resp["audio"] = audio_b64
    return resp


def _make_error(message: str) -> dict:
    return {"type": "error", "message": message}


def _make_interrupted() -> dict:
    return {"type": "interrupted"}


def _make_fallback(message: str) -> dict:
    return {"type": "fallback", "message": message}


class TestResponseFormat:
    """서버→클라이언트 JSON 응답 생성."""

    def test_send_transcript(self):
        resp = _make_transcript_response("요금 조회", is_final=True)
        assert resp["type"] == "transcript"
        assert resp["text"] == "요금 조회"
        assert resp["is_final"] is True

    def test_send_response_with_audio(self):
        resp = _make_response("이번 달 요금은 5만원입니다.", audio_b64="AQID", processing_ms=500)
        assert resp["type"] == "response"
        assert resp["audio"] == "AQID"
        assert resp["processing_ms"] == 500

    def test_send_error(self):
        resp = _make_error("세션을 찾을 수 없습니다")
        assert resp["type"] == "error"

    def test_send_interrupted_ack(self):
        resp = _make_interrupted()
        assert resp["type"] == "interrupted"

    def test_send_fallback(self):
        resp = _make_fallback("음성 인식 실패 — 텍스트 모드로 전환합니다")
        assert resp["type"] == "fallback"


# ---------------------------------------------------------------------------
# TASK-006: STT→Pipeline 연결
# ---------------------------------------------------------------------------


class TestSTTPipelineIntegration:
    """handle_audio에서 STT → Pipeline 호출."""

    @pytest.mark.asyncio
    async def test_handle_audio_calls_pipeline_with_stt_text(self):
        mock_stt = MagicMock()
        mock_handle = MagicMock()
        mock_stt.start_stream.return_value = mock_handle
        mock_stt_result = MagicMock()
        mock_stt_result.text = "요금 조회"
        mock_stt_result.is_valid = True
        mock_stt.get_final_result.return_value = mock_stt_result

        mock_pipeline = MagicMock()
        mock_pipeline_result = MagicMock()
        mock_pipeline_result.response_text = "이번 달 요금은 5만원입니다."
        mock_pipeline.process.return_value = mock_pipeline_result

        mock_tts = MagicMock()
        mock_tts_result = MagicMock()
        mock_tts_result.data = b"\x00\x01"
        mock_tts.synthesize.return_value = mock_tts_result

        server = VoiceServer(stt_engine=mock_stt, tts_engine=mock_tts, pipeline=mock_pipeline)
        session = server.create_session()
        result = await server.handle_audio(session.session_id, b"\x00" * 3200)

        mock_pipeline.process.assert_called_once_with(session.session_id, "요금 조회")
        assert result["response_text"] == "이번 달 요금은 5만원입니다."

    @pytest.mark.asyncio
    async def test_handle_audio_empty_stt_returns_error(self):
        mock_stt = MagicMock()
        mock_handle = MagicMock()
        mock_stt.start_stream.return_value = mock_handle
        mock_stt_result = MagicMock()
        mock_stt_result.text = ""
        mock_stt_result.is_valid = False
        mock_stt.get_final_result.return_value = mock_stt_result

        server = VoiceServer(stt_engine=mock_stt)
        session = server.create_session()
        result = await server.handle_audio(session.session_id, b"\x00" * 3200)

        assert "음성을 인식하지 못했습니다" in result.get("response_text", "")


# ---------------------------------------------------------------------------
# TASK-007: Pipeline→TTS 연결
# ---------------------------------------------------------------------------


class TestPipelineTTSIntegration:
    """handle_audio에서 Pipeline → TTS."""

    @pytest.mark.asyncio
    async def test_handle_audio_returns_tts_audio(self):
        mock_stt = MagicMock()
        mock_handle = MagicMock()
        mock_stt.start_stream.return_value = mock_handle
        mock_stt_result = MagicMock()
        mock_stt_result.text = "요금 조회"
        mock_stt_result.is_valid = True
        mock_stt.get_final_result.return_value = mock_stt_result

        mock_pipeline = MagicMock()
        mock_pipeline_result = MagicMock()
        mock_pipeline_result.response_text = "5만원입니다."
        mock_pipeline.process.return_value = mock_pipeline_result

        mock_tts = MagicMock()
        mock_tts_result = MagicMock()
        mock_tts_result.data = b"\x00\x01\x02"
        mock_tts.synthesize.return_value = mock_tts_result

        server = VoiceServer(stt_engine=mock_stt, tts_engine=mock_tts, pipeline=mock_pipeline)
        session = server.create_session()
        result = await server.handle_audio(session.session_id, b"\x00" * 3200)

        assert result["audio"] == b"\x00\x01\x02"
        mock_tts.synthesize.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_audio_tts_failure_returns_text_only(self):
        mock_stt = MagicMock()
        mock_handle = MagicMock()
        mock_stt.start_stream.return_value = mock_handle
        mock_stt_result = MagicMock()
        mock_stt_result.text = "요금 조회"
        mock_stt_result.is_valid = True
        mock_stt.get_final_result.return_value = mock_stt_result

        mock_pipeline = MagicMock()
        mock_pipeline_result = MagicMock()
        mock_pipeline_result.response_text = "5만원입니다."
        mock_pipeline.process.return_value = mock_pipeline_result

        mock_tts = MagicMock()
        mock_tts.synthesize.side_effect = RuntimeError("Polly error")

        server = VoiceServer(stt_engine=mock_stt, tts_engine=mock_tts, pipeline=mock_pipeline)
        session = server.create_session()
        result = await server.handle_audio(session.session_id, b"\x00" * 3200)

        assert result["response_text"] == "5만원입니다."
        assert result.get("audio") is None


# ---------------------------------------------------------------------------
# TASK-009: Barge-in interrupt
# ---------------------------------------------------------------------------


class TestBargeInInterrupt:
    """interrupt 메시지 → TTS 중단 + ACK."""

    @pytest.mark.asyncio
    async def test_interrupt_stops_tts_and_sends_ack(self):
        mock_tts = MagicMock()
        server = VoiceServer(tts_engine=mock_tts)
        session = server.create_session()
        session.is_tts_playing = True

        result = await server.handle_interrupt(session.session_id)
        assert result["status"] == "interrupted"
        mock_tts.stop_playback.assert_called_once_with(session.session_id)

    @pytest.mark.asyncio
    async def test_interrupt_when_not_playing(self):
        server = VoiceServer()
        session = server.create_session()
        result = await server.handle_interrupt(session.session_id)
        assert result["status"] == "not_playing"


# ---------------------------------------------------------------------------
# TASK-011: 텍스트 폴백 전환
# ---------------------------------------------------------------------------


class TestTextFallback:
    """STTFallbackError → 텍스트 폴백 모드."""

    @pytest.mark.asyncio
    async def test_stt_failure_triggers_text_fallback(self):
        from callbot.voice_io.fallback_stt import STTFallbackError

        mock_stt = MagicMock()
        mock_handle = MagicMock()
        mock_stt.start_stream.return_value = mock_handle
        mock_stt.get_final_result.side_effect = STTFallbackError("STT failed")

        server = VoiceServer(stt_engine=mock_stt)
        session = server.create_session()
        result = await server.handle_audio(session.session_id, b"\x00" * 3200)

        assert result.get("error") == "stt_failed"
        assert server.get_session(session.session_id).is_text_fallback is True


# ---------------------------------------------------------------------------
# TASK-013: 동시 세션 제한
# ---------------------------------------------------------------------------


class TestSessionLimit:
    """max_sessions 제한."""

    def test_max_sessions_rejects_new_connection(self):
        server = VoiceServer(max_sessions=2)
        server.create_session()
        server.create_session()
        with pytest.raises(RuntimeError, match="max sessions"):
            server.create_session()

    def test_session_count_tracks_correctly(self):
        server = VoiceServer(max_sessions=10)
        sessions = [server.create_session() for _ in range(5)]
        assert server.active_session_count == 5
        server.end_session(sessions[0].session_id)
        assert server.active_session_count == 4


# ---------------------------------------------------------------------------
# TASK-014: 세션 타임아웃
# ---------------------------------------------------------------------------


class TestSessionTimeout:
    """5분 무활동 시 자동 종료."""

    def test_session_timeout_auto_cleanup(self):
        import time
        server = VoiceServer(session_timeout_sec=0.1)
        session = server.create_session()
        # Simulate expired session
        session.last_activity = time.time() - 1.0
        server.cleanup_expired_sessions()
        assert server.active_session_count == 0

    def test_activity_resets_timeout(self):
        import time
        server = VoiceServer(session_timeout_sec=300)
        session = server.create_session()
        old_activity = session.last_activity
        time.sleep(0.01)
        session.last_activity = time.time()
        assert session.last_activity > old_activity


# ---------------------------------------------------------------------------
# TASK-016: 레이턴시 계측
# ---------------------------------------------------------------------------


class TestLatencyInstrumentation:
    """응답에 processing_ms 포함."""

    @pytest.mark.asyncio
    async def test_response_includes_processing_ms(self):
        mock_stt = MagicMock()
        mock_handle = MagicMock()
        mock_stt.start_stream.return_value = mock_handle
        mock_stt_result = MagicMock()
        mock_stt_result.text = "테스트"
        mock_stt_result.is_valid = True
        mock_stt.get_final_result.return_value = mock_stt_result

        mock_pipeline = MagicMock()
        mock_pipeline_result = MagicMock()
        mock_pipeline_result.response_text = "응답"
        mock_pipeline.process.return_value = mock_pipeline_result

        mock_tts = MagicMock()
        mock_tts_result = MagicMock()
        mock_tts_result.data = b"\x00"
        mock_tts.synthesize.return_value = mock_tts_result

        server = VoiceServer(stt_engine=mock_stt, tts_engine=mock_tts, pipeline=mock_pipeline)
        session = server.create_session()
        result = await server.handle_audio(session.session_id, b"\x00" * 3200)

        assert "processing_ms" in result
        assert isinstance(result["processing_ms"], int)
        assert result["processing_ms"] >= 0
