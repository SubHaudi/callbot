"""Phase F TASK-002: STTEngine ABC 확장 테스트."""
from __future__ import annotations

from callbot.voice_io.stt_engine import STTEngineBase
from callbot.voice_io.models import StreamHandle


class TestSTTEngineABCExtension:
    """FR-008: stop_stream/cancel 메서드 동작 확인."""

    def _make_engine(self):
        return STTEngineBase()

    def test_stop_stream_cleans_buffer(self):
        engine = self._make_engine()
        handle = engine.start_stream("sess-1")
        engine.process_audio_chunk(handle, b"audio_data")
        assert handle.stream_id in engine._buffers
        engine.stop_stream(handle)
        assert handle.stream_id not in engine._buffers

    def test_cancel_cleans_buffer(self):
        engine = self._make_engine()
        handle = engine.start_stream("sess-1")
        engine.process_audio_chunk(handle, b"audio_data")
        engine.cancel(handle)
        assert handle.stream_id not in engine._buffers

    def test_stop_stream_missing_handle_no_error(self):
        engine = self._make_engine()
        handle = StreamHandle(session_id="sess-1", stream_id="nonexistent")
        engine.stop_stream(handle)  # should not raise

    def test_cancel_missing_handle_no_error(self):
        engine = self._make_engine()
        handle = StreamHandle(session_id="sess-1", stream_id="nonexistent")
        engine.cancel(handle)  # should not raise
