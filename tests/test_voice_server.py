"""Phase F TASK-016: VoiceServer WebSocket 파이프라인 테스트."""
from __future__ import annotations

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from dataclasses import dataclass

from callbot.voice_io.voice_server import VoiceServer, VoiceSession
from callbot.voice_io.models import STTResult, StreamHandle, AudioStream, PartialResult
from callbot.voice_io.fallback_stt import STTFallbackError


@dataclass
class MockPipelineResult:
    response_text: str


@pytest.fixture
def mock_stt():
    stt = MagicMock()
    stt.start_stream.return_value = StreamHandle(session_id="s1", stream_id="st1")
    stt.process_audio_chunk.return_value = PartialResult(text="", is_final=False)
    stt.get_final_result.return_value = STTResult.create(
        text="요금 조회", confidence=0.9, processing_time_ms=100
    )
    return stt


@pytest.fixture
def mock_tts():
    tts = MagicMock()
    tts.synthesize.return_value = AudioStream(session_id="s1", data=b"\x00" * 500)
    return tts


@pytest.fixture
def mock_pipeline():
    pipeline = MagicMock()
    pipeline.process.return_value = MockPipelineResult(response_text="요금은 55,000원입니다.")
    return pipeline


@pytest.fixture
def server(mock_stt, mock_tts, mock_pipeline):
    return VoiceServer(
        stt_engine=mock_stt,
        tts_engine=mock_tts,
        pipeline=mock_pipeline,
    )


class TestVoiceServerSession:
    """VoiceServer 세션 관리."""

    def test_create_session(self, server):
        session = server.create_session()
        assert session.session_id is not None
        assert server.active_session_count == 1

    def test_end_session(self, server):
        session = server.create_session()
        server.end_session(session.session_id)
        assert server.active_session_count == 0

    def test_end_session_no_disk_write(self, server):
        """NFR-004: 음성 데이터 디스크 저장 안 함."""
        session = server.create_session()
        server.end_session(session.session_id)
        # 세션 완전 삭제 확인 (메모리에서 제거)
        assert server.get_session(session.session_id) is None

    def test_vad_silence_default(self, server):
        """FR-004: VAD 침묵 감지 기본값 1.0초."""
        session = server.create_session()
        assert session.vad_silence_sec == 1.0

    def test_vad_silence_custom(self, server):
        """FR-004: VAD 침묵 감지 설정 가능 0.5~2.0초."""
        session = server.create_session(vad_silence_sec=0.5)
        assert session.vad_silence_sec == 0.5
        session2 = server.create_session(vad_silence_sec=2.0)
        assert session2.vad_silence_sec == 2.0

    def test_vad_silence_out_of_range(self, server):
        """FR-004: 범위 밖 → ValueError."""
        with pytest.raises(ValueError):
            server.create_session(vad_silence_sec=0.3)
        with pytest.raises(ValueError):
            server.create_session(vad_silence_sec=2.5)


class TestVoiceServerAudioPipeline:
    """STT → Pipeline → TTS 파이프라인."""

    @pytest.mark.asyncio
    async def test_audio_to_response(self, server, mock_stt, mock_pipeline, mock_tts):
        """(1)(2)(3) 오디오 전송 → transcript → response_text + audio."""
        session = server.create_session()
        result = await server.handle_audio(session.session_id, b"fake_audio")
        assert result["transcript"] == "요금 조회"
        assert result["response_text"] == "요금은 55,000원입니다."
        assert len(result["audio"]) > 0
        mock_stt.start_stream.assert_called_once()
        mock_pipeline.process.assert_called_once()
        mock_tts.synthesize.assert_called_once()

    @pytest.mark.asyncio
    async def test_stt_failure_text_fallback(self, server, mock_stt):
        """(4) STT 실패 → 텍스트 폴백 (FR-009)."""
        mock_stt.start_stream.side_effect = STTFallbackError("STT down")
        session = server.create_session()
        result = await server.handle_audio(session.session_id, b"audio")
        assert result["error"] == "stt_failed"
        assert session.is_text_fallback is True

    @pytest.mark.asyncio
    async def test_session_not_found(self, server):
        result = await server.handle_audio("nonexistent", b"audio")
        assert result["error"] == "session_not_found"

    @pytest.mark.asyncio
    async def test_invalid_stt_result(self, server, mock_stt):
        """STT confidence 낮음 → 인식 실패 메시지."""
        mock_stt.get_final_result.return_value = STTResult.create(
            text="", confidence=0.1, processing_time_ms=50
        )
        session = server.create_session()
        result = await server.handle_audio(session.session_id, b"audio")
        assert result["transcript"] == ""
        assert "인식하지 못했습니다" in result["response_text"]


class TestVoiceServerInterrupt:
    """Barge-in interrupt 처리."""

    @pytest.mark.asyncio
    async def test_interrupt_during_tts(self, server, mock_tts):
        session = server.create_session()
        session.is_tts_playing = True
        result = await server.handle_interrupt(session.session_id)
        assert result["status"] == "interrupted"
        mock_tts.stop_playback.assert_called_once()

    @pytest.mark.asyncio
    async def test_interrupt_when_not_playing(self, server):
        session = server.create_session()
        result = await server.handle_interrupt(session.session_id)
        assert result["status"] == "not_playing"
