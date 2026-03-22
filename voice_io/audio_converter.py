"""callbot.voice_io.audio_converter — ffmpeg 기반 오디오 변환기 (FR-004)

WebSocket에서 수신한 opus/webm 오디오를 STT용 PCM 16kHz로 변환하고,
TTS 출력 PCM을 클라이언트용 opus로 변환.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class AudioConverterError(Exception):
    """오디오 변환 실패."""
    pass


class AudioConverter:
    """ffmpeg 기반 오디오 포맷 변환기.

    opus/webm → PCM 16kHz mono (STT 입력용)
    PCM 24kHz mono → opus (클라이언트 전송용)
    """

    def __init__(self, ffmpeg_path: Optional[str] = None) -> None:
        self._ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
        if self._ffmpeg is None:
            raise AudioConverterError(
                "ffmpeg not found. Install with: sudo yum install ffmpeg"
            )

    def opus_to_pcm(self, opus_data: bytes, sample_rate: int = 16000) -> bytes:
        """opus/webm 오디오를 PCM 16kHz mono로 변환.

        Args:
            opus_data: 입력 opus/webm 오디오 바이트
            sample_rate: 출력 샘플링 레이트 (기본 16000)

        Returns:
            PCM 16-bit signed LE mono 바이트
        """
        if not opus_data:
            return b""

        try:
            result = subprocess.run(
                [
                    self._ffmpeg,
                    "-i", "pipe:0",
                    "-f", "s16le",
                    "-acodec", "pcm_s16le",
                    "-ar", str(sample_rate),
                    "-ac", "1",
                    "pipe:1",
                ],
                input=opus_data,
                capture_output=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise AudioConverterError(
                    f"ffmpeg opus→PCM failed: {result.stderr.decode(errors='replace')[:200]}"
                )
            return result.stdout
        except subprocess.TimeoutExpired:
            raise AudioConverterError("ffmpeg opus→PCM timeout (10s)")

    def pcm_to_opus(self, pcm_data: bytes, input_sample_rate: int = 24000) -> bytes:
        """PCM 오디오를 opus로 변환.

        Args:
            pcm_data: 입력 PCM 16-bit signed LE mono 바이트
            input_sample_rate: 입력 샘플링 레이트 (기본 24000)

        Returns:
            opus 오디오 바이트 (ogg 컨테이너)
        """
        if not pcm_data:
            return b""

        try:
            result = subprocess.run(
                [
                    self._ffmpeg,
                    "-f", "s16le",
                    "-ar", str(input_sample_rate),
                    "-ac", "1",
                    "-i", "pipe:0",
                    "-c:a", "libopus",
                    "-b:a", "24k",
                    "-f", "ogg",
                    "pipe:1",
                ],
                input=pcm_data,
                capture_output=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise AudioConverterError(
                    f"ffmpeg PCM→opus failed: {result.stderr.decode(errors='replace')[:200]}"
                )
            return result.stdout
        except subprocess.TimeoutExpired:
            raise AudioConverterError("ffmpeg PCM→opus timeout (10s)")
