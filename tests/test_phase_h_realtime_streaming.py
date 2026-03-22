"""Phase H: 실시간 음성 스트리밍 테스트."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from callbot.voice_io.voice_server import VoiceServer


# ---- Fixtures ----

def _make_mock_stt():
    stt = MagicMock()
    stt.start_stream.return_value = MagicMock(session_id="s1")
    stt.process_audio_chunk.return_value = MagicMock(text="partial", is_final=False)
    stt.get_final_result.return_value = MagicMock(text="final text", confidence=0.95)
    stt.stop_stream.return_value = None
    stt.health_check.return_value = True
    return stt


def _make_mock_tts():
    tts = MagicMock()
    tts.synthesize.return_value = MagicMock(data=b"\x00\x01\x02")
    return tts


def _make_mock_pipeline():
    pipeline = MagicMock()
    result = MagicMock()
    result.response_text = "안녕하세요"
    pipeline.process.return_value = result
    return pipeline


# ---- TASK-002: STT/TTS 엔진 주입 검증 ----

class TestEngineInjection:
    def test_voice_server_has_stt_and_tts_engines(self):
        stt = _make_mock_stt()
        tts = _make_mock_tts()
        pipeline = _make_mock_pipeline()
        vs = VoiceServer(stt_engine=stt, tts_engine=tts, pipeline=pipeline)
        assert vs._stt is stt
        assert vs._tts is tts
        assert vs._pipeline is pipeline

    def test_graceful_degradation_without_aws(self):
        pipeline = _make_mock_pipeline()
        vs = VoiceServer(pipeline=pipeline)
        assert vs._stt is None
        assert vs._tts is None
        assert vs._pipeline is pipeline


# ---- TASK-005: handle_audio_chunk ----

class TestHandleAudioChunk:
    @pytest.fixture
    def vs_with_engines(self):
        vs = VoiceServer(
            stt_engine=_make_mock_stt(),
            tts_engine=_make_mock_tts(),
            pipeline=_make_mock_pipeline(),
        )
        return vs

    def test_first_chunk_creates_stt_stream(self, vs_with_engines):
        vs = vs_with_engines
        session = vs.create_session()
        assert not session.stt_stream_active
        result = asyncio.get_event_loop().run_until_complete(
            vs.handle_audio_chunk(session.session_id, b"\x00" * 3200)
        )
        assert result["status"] == "ok"
        assert session.stt_stream_active
        assert session.stt_handle is not None
        vs._stt.start_stream.assert_called_once_with(session.session_id)

    def test_subsequent_chunks_reuse_stream(self, vs_with_engines):
        vs = vs_with_engines
        session = vs.create_session()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(vs.handle_audio_chunk(session.session_id, b"\x00" * 3200))
        loop.run_until_complete(vs.handle_audio_chunk(session.session_id, b"\x00" * 3200))
        # start_stream should only be called once
        vs._stt.start_stream.assert_called_once()
        assert vs._stt.process_audio_chunk.call_count == 2

    def test_chunk_without_stt_returns_error(self):
        vs = VoiceServer(pipeline=_make_mock_pipeline())
        session = vs.create_session()
        result = asyncio.get_event_loop().run_until_complete(
            vs.handle_audio_chunk(session.session_id, b"\x00" * 3200)
        )
        assert result["error"] == "stt_not_configured"


# ---- TASK-007: partial transcript via Queue ----

class TestPartialTranscript:
    def test_partial_result_enqueued(self):
        stt = _make_mock_stt()
        # partial result with text
        stt.process_audio_chunk.return_value = MagicMock(text="안녕", is_final=False)
        vs = VoiceServer(stt_engine=stt, pipeline=_make_mock_pipeline())
        session = vs.create_session()
        asyncio.get_event_loop().run_until_complete(
            vs.handle_audio_chunk(session.session_id, b"\x00" * 3200)
        )
        assert not session.partial_queue.empty()
        item = session.partial_queue.get_nowait()
        assert item["text"] == "안녕"
        assert item["is_final"] is False

    def test_partial_queue_empty_when_no_partial(self):
        stt = _make_mock_stt()
        stt.process_audio_chunk.return_value = MagicMock(text="", is_final=False)
        vs = VoiceServer(stt_engine=stt, pipeline=_make_mock_pipeline())
        session = vs.create_session()
        asyncio.get_event_loop().run_until_complete(
            vs.handle_audio_chunk(session.session_id, b"\x00" * 3200)
        )
        assert session.partial_queue.empty()


# ---- TASK-009: handle_end ----

class TestHandleEnd:
    def test_handle_end_returns_full_response(self):
        stt = _make_mock_stt()
        tts = _make_mock_tts()
        pipeline = _make_mock_pipeline()
        vs = VoiceServer(stt_engine=stt, tts_engine=tts, pipeline=pipeline)
        session = vs.create_session()
        loop = asyncio.get_event_loop()
        # First send a chunk to activate stream
        loop.run_until_complete(vs.handle_audio_chunk(session.session_id, b"\x00" * 3200))
        # Then end
        result = loop.run_until_complete(vs.handle_end(session.session_id))
        assert "transcript" in result
        assert result["transcript"] == "final text"
        assert result["response_text"] == "안녕하세요"
        assert "processing_ms" in result
        assert "audio_b64" in result
        # stream should be closed
        assert not session.stt_stream_active
        assert session.stt_handle is None

    def test_handle_end_without_active_stream(self):
        vs = VoiceServer(stt_engine=_make_mock_stt(), pipeline=_make_mock_pipeline())
        session = vs.create_session()
        result = asyncio.get_event_loop().run_until_complete(
            vs.handle_end(session.session_id)
        )
        assert result["error"] == "no_active_stt_stream"


# ---- TASK-011: disconnect cleanup ----

class TestDisconnectCleanup:
    def test_disconnect_cleans_active_stt_stream(self):
        stt = _make_mock_stt()
        vs = VoiceServer(stt_engine=stt, pipeline=_make_mock_pipeline())
        session = vs.create_session()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(vs.handle_audio_chunk(session.session_id, b"\x00" * 3200))
        assert session.stt_stream_active
        # end_session should clean up
        vs.end_session(session.session_id)
        stt.stop_stream.assert_called_once()

    def test_disconnect_without_stream_no_error(self):
        vs = VoiceServer(pipeline=_make_mock_pipeline())
        session = vs.create_session()
        # should not raise
        vs.end_session(session.session_id)


# ---- TASK-011B: barge-in STT cleanup ----

class TestBargeInSTTCleanup:
    def test_interrupt_stops_active_stt_stream(self):
        stt = _make_mock_stt()
        vs = VoiceServer(stt_engine=stt, tts_engine=_make_mock_tts(), pipeline=_make_mock_pipeline())
        session = vs.create_session()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(vs.handle_audio_chunk(session.session_id, b"\x00" * 3200))
        assert session.stt_stream_active
        session.is_tts_playing = True  # simulate TTS playing
        result = loop.run_until_complete(vs.handle_interrupt(session.session_id))
        assert result["status"] == "interrupted"
        assert not session.stt_stream_active
        assert session.stt_handle is None
        stt.stop_stream.assert_called_once()

    def test_interrupt_without_stream_no_error(self):
        vs = VoiceServer(pipeline=_make_mock_pipeline())
        session = vs.create_session()
        result = asyncio.get_event_loop().run_until_complete(
            vs.handle_interrupt(session.session_id)
        )
        assert result["status"] == "not_playing"
