"""Phase F TASK-006: TranscribeSTTEngine mock boto3 테스트."""
from __future__ import annotations

import unittest.mock
import pytest
from unittest.mock import MagicMock, patch

from callbot.voice_io.transcribe_stt import TranscribeSTTEngine


@pytest.fixture
def mock_transcribe():
    """boto3 transcribe 클라이언트 mock."""
    client = MagicMock()
    client.transcribe.return_value = {
        "text": "요금 조회해주세요",
        "confidence": 0.92,
    }
    return client


class TestTranscribeSTTEngine:
    """FR-001: TranscribeSTTEngine mock boto3 테스트."""

    def test_start_stream_returns_handle(self, mock_transcribe):
        engine = TranscribeSTTEngine(transcribe_client=mock_transcribe)
        handle = engine.start_stream("sess-1")
        assert handle.session_id == "sess-1"
        assert handle.stream_id is not None

    def test_process_chunk_accumulates(self, mock_transcribe):
        """오디오 청크 누적 확인."""
        engine = TranscribeSTTEngine(transcribe_client=mock_transcribe)
        handle = engine.start_stream("sess-1")
        engine.process_audio_chunk(handle, b"chunk1")
        engine.process_audio_chunk(handle, b"chunk2")
        assert len(engine._buffers[handle.stream_id]) == len(b"chunk1") + len(b"chunk2")

    def test_get_final_result_korean(self, mock_transcribe):
        """(1) Mock boto3로 한국어 텍스트 반환 확인."""
        engine = TranscribeSTTEngine(transcribe_client=mock_transcribe)
        handle = engine.start_stream("sess-1")
        engine.process_audio_chunk(handle, b"fake_pcm_audio")
        result = engine.get_final_result(handle)
        assert result.text == "요금 조회해주세요"
        assert result.confidence == 0.92
        assert result.is_valid is True
        assert result.processing_time_ms >= 0
        mock_transcribe.transcribe.assert_called_once()

    def test_confidence_threshold(self, mock_transcribe):
        """(2) confidence 낮으면 is_valid=False."""
        mock_transcribe.transcribe.return_value = {"text": "뭐", "confidence": 0.2}
        engine = TranscribeSTTEngine(transcribe_client=mock_transcribe, confidence_threshold=0.5)
        handle = engine.start_stream("sess-1")
        engine.process_audio_chunk(handle, b"audio")
        result = engine.get_final_result(handle)
        assert result.is_valid is False
        assert result.confidence == 0.2

    def test_stop_stream_cleans_buffer(self, mock_transcribe):
        """(3) stop_stream으로 버퍼 정리."""
        engine = TranscribeSTTEngine(transcribe_client=mock_transcribe)
        handle = engine.start_stream("sess-1")
        engine.process_audio_chunk(handle, b"data")
        engine.stop_stream(handle)
        assert handle.stream_id not in engine._buffers
        assert handle.stream_id not in engine._partials

    def test_cancel_cleans_buffer(self, mock_transcribe):
        """(3) cancel로 버퍼 정리."""
        engine = TranscribeSTTEngine(transcribe_client=mock_transcribe)
        handle = engine.start_stream("sess-1")
        engine.process_audio_chunk(handle, b"data")
        engine.cancel(handle)
        assert handle.stream_id not in engine._buffers

    def test_empty_audio_returns_empty(self, mock_transcribe):
        """(4) 빈 오디오 → 빈 결과, API 호출 없음."""
        engine = TranscribeSTTEngine(transcribe_client=mock_transcribe)
        handle = engine.start_stream("sess-1")
        result = engine.get_final_result(handle)
        assert result.text == ""
        assert result.confidence == 0.0
        mock_transcribe.transcribe.assert_not_called()

    def test_no_mock_client_uses_streaming_path(self):
        """(5) mock_client 미주입 시 _transcribe_streaming 경로로 진입."""
        engine = TranscribeSTTEngine(transcribe_client=None)
        assert engine._mock_client is None
        handle = engine.start_stream("sess-1")
        engine.process_audio_chunk(handle, b"\x00" * 3200)
        # _transcribe_streaming이 호출되는지 확인 (실제 AWS 호출은 mock)
        with unittest.mock.patch.object(
            engine, "_transcribe_streaming",
            return_value={"text": "테스트", "confidence": 0.9},
        ) as mock_streaming:
            result = engine.get_final_result(handle)
            mock_streaming.assert_called_once()
            assert result.text == "테스트"

    def test_language_code_ko_kr(self, mock_transcribe):
        """(6) language_code=ko-KR 확인."""
        engine = TranscribeSTTEngine(transcribe_client=mock_transcribe)
        handle = engine.start_stream("sess-1")
        engine.process_audio_chunk(handle, b"audio")
        engine.get_final_result(handle)
        call_kwargs = mock_transcribe.transcribe.call_args
        assert call_kwargs.kwargs["language_code"] == "ko-KR"
        assert call_kwargs.kwargs["sample_rate"] == 16000
