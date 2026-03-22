"""Phase F TASK-014: AudioConverter mock ffmpeg 테스트."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from callbot.voice_io.audio_converter import AudioConverter, AudioConverterError


class TestAudioConverter:
    """FR-004: AudioConverter ffmpeg 기반 변환."""

    def test_ffmpeg_not_found_raises(self):
        """ffmpeg 미설치 시 AudioConverterError."""
        with patch("callbot.voice_io.audio_converter.shutil.which", return_value=None):
            with pytest.raises(AudioConverterError, match="ffmpeg not found"):
                AudioConverter()

    def test_opus_to_pcm_success(self):
        """opus→PCM 변환 성공."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"\x00\x01" * 1000
        with patch("callbot.voice_io.audio_converter.subprocess.run", return_value=mock_result):
            conv = AudioConverter(ffmpeg_path="/usr/bin/ffmpeg")
            pcm = conv.opus_to_pcm(b"fake_opus_data")
            assert pcm == b"\x00\x01" * 1000

    def test_pcm_to_opus_success(self):
        """PCM→opus 변환 성공."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"OggS" + b"\x00" * 100
        with patch("callbot.voice_io.audio_converter.subprocess.run", return_value=mock_result):
            conv = AudioConverter(ffmpeg_path="/usr/bin/ffmpeg")
            opus = conv.pcm_to_opus(b"\x00\x01" * 500)
            assert opus.startswith(b"OggS")

    def test_opus_to_pcm_failure(self):
        """opus→PCM 변환 실패 → AudioConverterError."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = b"Invalid data"
        with patch("callbot.voice_io.audio_converter.subprocess.run", return_value=mock_result):
            conv = AudioConverter(ffmpeg_path="/usr/bin/ffmpeg")
            with pytest.raises(AudioConverterError, match="opus→PCM failed"):
                conv.opus_to_pcm(b"bad_data")

    def test_empty_audio_returns_empty(self):
        """빈 오디오 입력 → 빈 바이트."""
        conv = AudioConverter(ffmpeg_path="/usr/bin/ffmpeg")
        assert conv.opus_to_pcm(b"") == b""
        assert conv.pcm_to_opus(b"") == b""

    def test_timeout_raises(self):
        """ffmpeg 타임아웃 → AudioConverterError."""
        import subprocess
        with patch("callbot.voice_io.audio_converter.subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 10)):
            conv = AudioConverter(ffmpeg_path="/usr/bin/ffmpeg")
            with pytest.raises(AudioConverterError, match="timeout"):
                conv.opus_to_pcm(b"data")
