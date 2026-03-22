"""Phase F: TranscribeSTTEngine mock 기반 테스트."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from callbot.voice_io.transcribe_stt import TranscribeSTTEngine


@pytest.fixture
def mock_transcribe():
    client = MagicMock()
    client.transcribe.return_value = {
        "text": "요금 조회해주세요",
        "confidence": 0.92,
    }
    return client


class TestTranscribeSTTEngine:

    def test_start_stream(self, mock_transcribe):
        engine = TranscribeSTTEngine(transcribe_client=mock_transcribe)
        handle = engine.start_stream("sess-1")
        assert handle.session_id == "sess-1"

    def test_process_chunk_accumulates(self, mock_transcribe):
        engine = TranscribeSTTEngine(transcribe_client=mock_transcribe)
        handle = engine.start_stream("sess-1")
        engine.process_audio_chunk(handle, b"chunk1")
        engine.process_audio_chunk(handle, b"chunk2")
        assert len(engine._buffers[handle.stream_id]) == 12

    def test_get_final_result(self, mock_transcribe):
        engine = TranscribeSTTEngine(transcribe_client=mock_transcribe)
        handle = engine.start_stream("sess-1")
        engine.process_audio_chunk(handle, b"fake_pcm_audio")
        result = engine.get_final_result(handle)
        assert result.text == "요금 조회해주세요"
        assert result.confidence == 0.92
        assert result.is_valid is True
        assert result.processing_time_ms >= 0
        mock_transcribe.transcribe.assert_called_once()

    def test_low_confidence(self, mock_transcribe):
        mock_transcribe.transcribe.return_value = {"text": "뭐", "confidence": 0.2}
        engine = TranscribeSTTEngine(transcribe_client=mock_transcribe, confidence_threshold=0.5)
        handle = engine.start_stream("sess-1")
        engine.process_audio_chunk(handle, b"audio")
        result = engine.get_final_result(handle)
        assert result.is_valid is False

    def test_empty_audio(self, mock_transcribe):
        engine = TranscribeSTTEngine(transcribe_client=mock_transcribe)
        handle = engine.start_stream("sess-1")
        result = engine.get_final_result(handle)
        assert result.text == ""
        assert result.confidence == 0.0
        mock_transcribe.transcribe.assert_not_called()

    def test_no_client_raises(self):
        engine = TranscribeSTTEngine(transcribe_client=None)
        engine._client = None
        handle = engine.start_stream("sess-1")
        engine.process_audio_chunk(handle, b"audio")
        with pytest.raises(RuntimeError, match="Transcribe client not available"):
            engine.get_final_result(handle)

    def test_stop_stream(self, mock_transcribe):
        engine = TranscribeSTTEngine(transcribe_client=mock_transcribe)
        handle = engine.start_stream("sess-1")
        engine.process_audio_chunk(handle, b"data")
        engine.stop_stream(handle)
        assert handle.stream_id not in engine._buffers

    def test_cancel(self, mock_transcribe):
        engine = TranscribeSTTEngine(transcribe_client=mock_transcribe)
        handle = engine.start_stream("sess-1")
        engine.process_audio_chunk(handle, b"data")
        engine.cancel(handle)
        assert handle.stream_id not in engine._buffers

    def test_korean_language_code(self, mock_transcribe):
        engine = TranscribeSTTEngine(transcribe_client=mock_transcribe)
        handle = engine.start_stream("sess-1")
        engine.process_audio_chunk(handle, b"audio")
        engine.get_final_result(handle)
        call_kwargs = mock_transcribe.transcribe.call_args
        assert call_kwargs.kwargs["language_code"] == "ko-KR"
