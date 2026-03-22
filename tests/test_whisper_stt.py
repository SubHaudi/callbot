"""Phase F TASK-006: WhisperSTTEngine mock 기반 테스트."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from collections import namedtuple

from callbot.voice_io.whisper_stt import WhisperSTTEngine, _WHISPER_AVAILABLE


# Mock segment and info for faster-whisper
MockSegment = namedtuple("MockSegment", ["text"])
MockInfo = namedtuple("MockInfo", ["language_probability"])


@pytest.fixture
def mock_whisper():
    """faster-whisper를 mock으로 패치."""
    with patch("callbot.voice_io.whisper_stt._WHISPER_AVAILABLE", True), \
         patch("callbot.voice_io.whisper_stt.WhisperModel") as MockModel:
        model_instance = MagicMock()
        MockModel.return_value = model_instance
        model_instance.transcribe.return_value = (
            [MockSegment(text="요금 조회해줘")],
            MockInfo(language_probability=0.95),
        )
        yield model_instance


class TestWhisperSTTEngine:
    """FR-001: WhisperSTTEngine mock 기반 테스트."""

    def test_import_error_without_whisper(self):
        """faster-whisper 미설치 시 ImportError."""
        with patch("callbot.voice_io.whisper_stt._WHISPER_AVAILABLE", False):
            with pytest.raises(ImportError, match="faster-whisper is not installed"):
                WhisperSTTEngine()

    def test_start_stream_returns_handle(self, mock_whisper):
        engine = WhisperSTTEngine()
        handle = engine.start_stream("sess-1")
        assert handle.session_id == "sess-1"
        assert handle.stream_id is not None

    def test_process_chunk_accumulates(self, mock_whisper):
        engine = WhisperSTTEngine()
        handle = engine.start_stream("sess-1")
        partial = engine.process_audio_chunk(handle, b"chunk1")
        assert partial.is_final is False
        engine.process_audio_chunk(handle, b"chunk2")
        assert len(engine._buffers[handle.stream_id]) == len(b"chunk1") + len(b"chunk2")

    def test_get_final_result_korean(self, mock_whisper):
        """Mock whisper로 한국어 텍스트 반환."""
        engine = WhisperSTTEngine()
        handle = engine.start_stream("sess-1")
        engine.process_audio_chunk(handle, b"fake_audio_data")
        result = engine.get_final_result(handle)
        assert result.text == "요금 조회해줘"
        assert result.confidence == 0.95
        assert result.is_valid is True
        assert result.processing_time_ms >= 0

    def test_confidence_threshold(self, mock_whisper):
        """낮은 confidence → is_valid=False."""
        mock_whisper.transcribe.return_value = (
            [MockSegment(text="뭐라고")],
            MockInfo(language_probability=0.3),
        )
        engine = WhisperSTTEngine(confidence_threshold=0.5)
        handle = engine.start_stream("sess-1")
        engine.process_audio_chunk(handle, b"audio")
        result = engine.get_final_result(handle)
        assert result.is_valid is False
        assert result.confidence == 0.3

    def test_stop_stream(self, mock_whisper):
        engine = WhisperSTTEngine()
        handle = engine.start_stream("sess-1")
        engine.process_audio_chunk(handle, b"data")
        engine.stop_stream(handle)
        assert handle.stream_id not in engine._buffers

    def test_cancel(self, mock_whisper):
        engine = WhisperSTTEngine()
        handle = engine.start_stream("sess-1")
        engine.process_audio_chunk(handle, b"data")
        engine.cancel(handle)
        assert handle.stream_id not in engine._buffers

    def test_env_model_size(self, mock_whisper):
        """환경변수로 모델 크기 전환."""
        import os
        with patch.dict(os.environ, {"WHISPER_MODEL": "medium"}):
            engine = WhisperSTTEngine()
            assert engine._model_size == "medium"

    def test_empty_audio_returns_empty(self, mock_whisper):
        """빈 오디오 → 빈 결과."""
        engine = WhisperSTTEngine()
        handle = engine.start_stream("sess-1")
        # process_audio_chunk 없이 바로 get_final_result
        result = engine.get_final_result(handle)
        assert result.text == ""
        assert result.confidence == 0.0
