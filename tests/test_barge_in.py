"""
Unit tests for Barge-in integration — Sub-task 6.1

Validates barge-in callback interface between STT and TTS engines.
Validates: Requirements 4.1
"""
import pytest
from unittest.mock import MagicMock

from callbot.voice_io.barge_in import BargeInHandler
from callbot.voice_io.stt_engine import STTEngineBase
from callbot.voice_io.tts_engine import TTSEngineBase


# ---------------------------------------------------------------------------
# Sub-task 6.1 — 바지인 연동 단위 테스트
# Validates: Requirements 4.1
# ---------------------------------------------------------------------------

class TestBargeInHandlerProtocol:
    """BargeInHandler 프로토콜 검증"""

    def test_tts_engine_base_satisfies_barge_in_handler_protocol(self):
        """TTSEngineBase는 BargeInHandler 프로토콜을 만족한다 (isinstance 검사)"""
        tts = TTSEngineBase()
        assert isinstance(tts, BargeInHandler)

    def test_mock_with_stop_playback_satisfies_protocol(self):
        """stop_playback() 메서드를 가진 객체는 BargeInHandler 프로토콜을 만족한다"""
        mock_tts = MagicMock(spec=["stop_playback", "speech_start", "speech_end"])
        assert isinstance(mock_tts, BargeInHandler)


class TestBargeInHandlerRegistration:
    """STTEngineBase barge_in_handler 등록 테스트"""

    def test_stt_engine_default_no_barge_in_handler(self):
        """기본 생성 시 barge_in_handler는 None이다"""
        engine = STTEngineBase()
        assert engine._barge_in_handler is None

    def test_stt_engine_accepts_barge_in_handler(self):
        """barge_in_handler를 생성자에서 주입할 수 있다"""
        mock_tts = MagicMock()
        engine = STTEngineBase(barge_in_handler=mock_tts)
        assert engine._barge_in_handler is mock_tts

    def test_stt_engine_backward_compatible_constructor(self):
        """기존 생성자 파라미터(threshold, vad)와 함께 barge_in_handler를 사용할 수 있다"""
        mock_tts = MagicMock()
        engine = STTEngineBase(
            stt_confidence_threshold=0.6,
            vad_silence_sec=2.0,
            barge_in_handler=mock_tts,
        )
        assert engine.stt_confidence_threshold == 0.6
        assert engine.vad_silence_sec == 2.0
        assert engine._barge_in_handler is mock_tts


class TestActivateBargeIn:
    """activate_barge_in() 호출 시 TTS stop_playback() 트리거 테스트"""

    def test_activate_barge_in_calls_stop_playback_with_session_id(self):
        """바지인 감지 시 stop_playback()이 올바른 session_id로 정확히 1회 호출된다"""
        mock_tts = MagicMock()
        engine = STTEngineBase(barge_in_handler=mock_tts)

        engine.activate_barge_in("session-001")

        mock_tts.stop_playback.assert_called_once_with("session-001")

    def test_activate_barge_in_calls_stop_playback_with_correct_session_id(self):
        """다른 session_id로 호출해도 올바른 session_id가 전달된다"""
        mock_tts = MagicMock()
        engine = STTEngineBase(barge_in_handler=mock_tts)

        engine.activate_barge_in("session-xyz")

        mock_tts.stop_playback.assert_called_once_with("session-xyz")

    def test_activate_barge_in_no_handler_does_not_raise(self):
        """handler가 없을 때 activate_barge_in()은 예외 없이 실행된다"""
        engine = STTEngineBase()  # no barge_in_handler
        engine.activate_barge_in("session-001")  # should not raise

    def test_activate_barge_in_no_handler_stop_playback_not_called(self):
        """handler가 없을 때 stop_playback()은 호출되지 않는다"""
        mock_tts = MagicMock()
        engine = STTEngineBase()  # no barge_in_handler — mock_tts not registered

        engine.activate_barge_in("session-001")

        mock_tts.stop_playback.assert_not_called()

    def test_activate_barge_in_multiple_calls(self):
        """activate_barge_in()을 여러 번 호출하면 stop_playback()도 동일 횟수 호출된다"""
        mock_tts = MagicMock()
        engine = STTEngineBase(barge_in_handler=mock_tts)

        engine.activate_barge_in("session-001")
        engine.activate_barge_in("session-001")
        engine.activate_barge_in("session-001")

        assert mock_tts.stop_playback.call_count == 3

    def test_activate_barge_in_with_real_tts_engine(self):
        """실제 TTSEngineBase를 handler로 사용해도 예외 없이 동작한다"""
        tts = TTSEngineBase()
        engine = STTEngineBase(barge_in_handler=tts)

        engine.activate_barge_in("session-001")  # should not raise
