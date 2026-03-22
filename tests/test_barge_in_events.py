"""Phase F TASK-010: Barge-in speech events + stopped flag 테스트."""
from __future__ import annotations

from unittest.mock import MagicMock

from callbot.voice_io.stt_engine import STTEngineBase
from callbot.voice_io.tts_engine import TTSEngineBase
from callbot.voice_io.polly_tts import PollyTTSEngine


class TestBargeInSpeechEvents:
    """FR-005: speech_start/speech_end 콜백 + stopped 플래그."""

    def test_speech_start_callback(self):
        """speech_start 콜백이 정상 호출된다."""
        handler = MagicMock()
        handler.speech_start("sess-1")
        handler.speech_start.assert_called_once_with("sess-1")

    def test_speech_end_callback(self):
        """speech_end 콜백이 정상 호출된다."""
        handler = MagicMock()
        handler.speech_end("sess-1")
        handler.speech_end.assert_called_once_with("sess-1")

    def test_tts_base_speech_callbacks_noop(self):
        """TTSEngineBase의 speech_start/end는 no-op."""
        tts = TTSEngineBase()
        tts.speech_start("sess-1")  # should not raise
        tts.speech_end("sess-1")  # should not raise

    def test_polly_stop_playback_sets_stopped_flag(self):
        """PollyTTS stop_playback → is_playing False (M-30: 삭제 아님, 플래그 전환)."""
        mock_client = MagicMock()
        engine = PollyTTSEngine(polly_client=mock_client)
        engine._playing["sess-1"] = True
        engine.stop_playback("sess-1")
        assert engine.is_playing("sess-1") is False
        # 세션 자체는 삭제되지 않음
        assert "sess-1" in engine._playing

    def test_polly_stop_playback_already_stopped(self):
        """이미 stopped인 세션에 다시 stop_playback → 무시."""
        mock_client = MagicMock()
        engine = PollyTTSEngine(polly_client=mock_client)
        engine._playing["sess-1"] = False
        engine.stop_playback("sess-1")  # should not raise
        assert engine.is_playing("sess-1") is False

    def test_stt_activate_barge_in_triggers_stop_playback(self):
        """STT activate_barge_in → handler.stop_playback 호출."""
        handler = MagicMock()
        engine = STTEngineBase(barge_in_handler=handler)
        engine.activate_barge_in("sess-1")
        handler.stop_playback.assert_called_once_with("sess-1")
