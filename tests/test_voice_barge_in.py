"""Phase F TASK-017: VoiceServer barge-in 테스트 (Red → Green in TASK-018)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from dataclasses import dataclass

from callbot.voice_io.voice_server import VoiceServer, VoiceSession
from callbot.voice_io.models import STTResult, StreamHandle, AudioStream, PartialResult


@dataclass
class MockPipelineResult:
    response_text: str


@pytest.fixture
def barge_in_server():
    stt = MagicMock()
    stt.start_stream.return_value = StreamHandle(session_id="s1", stream_id="st1")
    stt.process_audio_chunk.return_value = PartialResult(text="", is_final=False)
    stt.get_final_result.return_value = STTResult.create(
        text="요금 조회", confidence=0.9, processing_time_ms=100
    )
    tts = MagicMock()
    tts.synthesize.return_value = AudioStream(session_id="s1", data=b"\x00" * 500)
    pipeline = MagicMock()
    pipeline.process.return_value = MockPipelineResult(response_text="응답입니다.")
    return VoiceServer(stt_engine=stt, tts_engine=tts, pipeline=pipeline), stt, tts, pipeline


class TestVoiceServerBargeIn:
    """FR-005: Barge-in 통합 테스트."""

    @pytest.mark.asyncio
    async def test_interrupt_stops_tts(self, barge_in_server):
        """TTS 재생 중 interrupt → TTS 중단."""
        server, stt, tts, pipeline = barge_in_server
        session = server.create_session()
        session.is_tts_playing = True
        result = await server.handle_interrupt(session.session_id)
        assert result["status"] == "interrupted"
        tts.stop_playback.assert_called_once_with(session.session_id)
        assert session.is_tts_playing is False

    @pytest.mark.asyncio
    async def test_new_audio_during_tts(self, barge_in_server):
        """TTS 재생 중 새 오디오 → TTS 중단 + 새 STT 시작."""
        server, stt, tts, pipeline = barge_in_server
        session = server.create_session()
        session.is_tts_playing = True

        # 먼저 interrupt
        await server.handle_interrupt(session.session_id)
        assert session.is_tts_playing is False

        # 새 오디오 처리
        result = await server.handle_audio(session.session_id, b"new_audio")
        assert result["transcript"] == "요금 조회"
        assert stt.start_stream.call_count >= 1

    @pytest.mark.asyncio
    async def test_stopped_state_new_utterance(self, barge_in_server):
        """stopped 상태에서 새 발화 정상 처리."""
        server, stt, tts, pipeline = barge_in_server
        session = server.create_session()

        # interrupt → stopped
        session.is_tts_playing = True
        await server.handle_interrupt(session.session_id)
        assert session.is_tts_playing is False

        # 새 발화 처리
        result = await server.handle_audio(session.session_id, b"audio2")
        assert result["transcript"] == "요금 조회"
        assert result["response_text"] == "응답입니다."
