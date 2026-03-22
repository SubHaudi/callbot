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
