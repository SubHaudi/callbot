"""Phase F TASK-004: FallbackSTTEngine 동작 테스트."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from callbot.voice_io.fallback_stt import FallbackSTTEngine, STTFallbackError
from callbot.voice_io.models import StreamHandle, STTResult, PartialResult


class TestFallbackSTTEngine:
    """FR-003: FallbackSTTEngine 래퍼 동작 테스트."""

    def _make_mock_primary(self):
        primary = MagicMock()
        primary.start_stream.return_value = StreamHandle(session_id="s1", stream_id="st1")
        primary.process_audio_chunk.return_value = PartialResult(text="부분", is_final=False)
        primary.get_final_result.return_value = STTResult.create(
            text="요금 조회", confidence=0.9, processing_time_ms=100
        )
        return primary

    def test_primary_success_delegates(self):
        """주 엔진 정상 → 주 엔진 결과 반환."""
        primary = self._make_mock_primary()
        engine = FallbackSTTEngine(primary)

        handle = engine.start_stream("s1")
        assert handle.session_id == "s1"
        primary.start_stream.assert_called_once_with("s1")

        partial = engine.process_audio_chunk(handle, b"audio")
        assert partial.text == "부분"

        result = engine.get_final_result(handle)
        assert result.text == "요금 조회"

    def test_primary_failure_raises_fallback_error(self):
        """주 엔진 실패 → STTFallbackError 발생."""
        primary = self._make_mock_primary()
        primary.start_stream.side_effect = RuntimeError("connection failed")
        engine = FallbackSTTEngine(primary)

        with pytest.raises(STTFallbackError, match="STT 서비스 시작 실패"):
            engine.start_stream("s1")

    def test_process_chunk_failure_raises_fallback_error(self):
        primary = self._make_mock_primary()
        primary.process_audio_chunk.side_effect = RuntimeError("decode error")
        engine = FallbackSTTEngine(primary)

        handle = engine.start_stream("s1")
        with pytest.raises(STTFallbackError, match="오디오 처리 실패"):
            engine.process_audio_chunk(handle, b"bad")

    def test_get_final_result_failure_raises_fallback_error(self):
        primary = self._make_mock_primary()
        primary.get_final_result.side_effect = RuntimeError("timeout")
        engine = FallbackSTTEngine(primary)

        handle = engine.start_stream("s1")
        with pytest.raises(STTFallbackError, match="최종 결과 실패"):
            engine.get_final_result(handle)

    def test_health_check_delegates(self):
        primary = self._make_mock_primary()
        primary.health_check.return_value = True
        engine = FallbackSTTEngine(primary)
        assert engine.health_check() is True

    def test_close_delegates(self):
        primary = self._make_mock_primary()
        engine = FallbackSTTEngine(primary)
        engine.close()
        primary.close.assert_called_once()

    def test_stop_stream_failure_silenced(self):
        """stop_stream 실패는 무시."""
        primary = self._make_mock_primary()
        primary.stop_stream.side_effect = RuntimeError("cleanup failed")
        engine = FallbackSTTEngine(primary)
        handle = StreamHandle(session_id="s1", stream_id="st1")
        engine.stop_stream(handle)  # should not raise

    def test_cancel_failure_silenced(self):
        """cancel 실패는 무시."""
        primary = self._make_mock_primary()
        primary.cancel.side_effect = RuntimeError("cancel failed")
        engine = FallbackSTTEngine(primary)
        handle = StreamHandle(session_id="s1", stream_id="st1")
        engine.cancel(handle)  # should not raise
