"""Phase F TASK-008: PollyTTSEngine mock 기반 테스트."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from io import BytesIO

from callbot.voice_io.polly_tts import PollyTTSEngine


class TestPollyTTSEngine:
    """FR-002: PollyTTSEngine mock boto3 테스트."""

    def _make_engine(self):
        mock_client = MagicMock()
        mock_client.synthesize_speech.return_value = {
            "AudioStream": BytesIO(b"\x00" * 1000),
        }
        return PollyTTSEngine(polly_client=mock_client), mock_client

    def test_synthesize_returns_audio(self):
        engine, client = self._make_engine()
        result = engine.synthesize("안녕하세요", "sess-1")
        assert result.data == b"\x00" * 1000
        assert result.sample_rate == 24000
        assert result.encoding == "pcm"
        client.synthesize_speech.assert_called_once()

    def test_synthesize_uses_ssml(self):
        engine, client = self._make_engine()
        engine.synthesize("요금 조회", "sess-1")
        call_args = client.synthesize_speech.call_args
        assert call_args.kwargs["TextType"] == "ssml"
        assert "<speak>" in call_args.kwargs["Text"]

    def test_synthesize_uses_seoyeon(self):
        engine, client = self._make_engine()
        engine.synthesize("테스트", "sess-1")
        call_args = client.synthesize_speech.call_args
        assert call_args.kwargs["VoiceId"] == "Seoyeon"
        assert call_args.kwargs["Engine"] == "neural"

    def test_ssml_conversion(self):
        engine, _ = self._make_engine()
        ssml = engine.text_to_ssml("요금은 55,000원입니다.", speed_factor=1.0)
        assert '<prosody rate="100%">' in ssml
        assert "요금은 55,000원입니다." in ssml
        assert "<speak>" in ssml

    def test_ssml_speed_factor(self):
        engine, _ = self._make_engine()
        ssml = engine.text_to_ssml("빠르게", speed_factor=1.3)
        assert '<prosody rate="130%">' in ssml

    def test_ssml_escapes_special_chars(self):
        engine, _ = self._make_engine()
        ssml = engine.text_to_ssml("A & B < C > D")
        assert "&amp;" in ssml
        assert "&lt;" in ssml
        assert "&gt;" in ssml

    def test_split_sentences(self):
        engine, _ = self._make_engine()
        result = engine.split_sentences("안녕하세요. 요금은 55,000원입니다. 감사합니다!")
        assert len(result) == 3
        assert result[0] == "안녕하세요."
        assert result[2] == "감사합니다!"

    def test_stop_playback_sets_flag(self):
        engine, _ = self._make_engine()
        engine._playing["sess-1"] = True
        engine.stop_playback("sess-1")
        assert engine.is_playing("sess-1") is False

    def test_synthesize_failure_raises(self):
        engine, client = self._make_engine()
        client.synthesize_speech.side_effect = RuntimeError("Polly down")
        with pytest.raises(RuntimeError, match="Polly down"):
            engine.synthesize("테스트", "sess-1")

    def test_no_client_raises(self):
        engine = PollyTTSEngine(polly_client=None)
        engine._client = None
        with pytest.raises(RuntimeError, match="Polly client not available"):
            engine.synthesize("테스트", "sess-1")
