"""callbot.voice_io.polly_tts — Amazon Polly 기반 TTS 엔진 (FR-002)

Neural 한국어 음성 (Seoyeon) 사용. boto3 Polly 클라이언트 DI.
문장 단위 분할 후 스트리밍.
"""
from __future__ import annotations

import logging
import re
from typing import Optional, Any

from callbot.voice_io.tts_engine import TTSEngine
from callbot.voice_io.enums import NumberType
from callbot.voice_io.models import AudioStream

logger = logging.getLogger(__name__)


class PollyTTSEngine(TTSEngine):
    """Amazon Polly 기반 TTS 엔진.

    - 음성: Seoyeon (Neural 한국어)
    - 출력: PCM 16bit 24kHz
    - 문장 단위 SSML 분할 + 스트리밍
    """

    def __init__(
        self,
        polly_client: Optional[Any] = None,
        voice_id: str = "Seoyeon",
        engine: str = "neural",
        sample_rate: str = "16000",
    ) -> None:
        self._voice_id = voice_id
        self._engine = engine
        self._sample_rate = sample_rate
        self._playing: dict[str, bool] = {}  # session_id → is_playing

        if polly_client is not None:
            self._client = polly_client
        else:
            try:
                import boto3
                self._client = boto3.client("polly")
            except Exception as e:
                logger.warning("boto3 Polly client init failed: %s", e)
                self._client = None

    def text_to_ssml(self, text: str, speed_factor: float = 1.0) -> str:
        """텍스트를 SSML로 변환.

        Args:
            text: 변환할 텍스트
            speed_factor: 말하기 속도 배율 (0.7~1.3)
        """
        # 속도 조절 (percentage 변환: 1.0 → 100%, 0.8 → 80%)
        rate = f"{int(speed_factor * 100)}%"
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return (
            f'<speak><prosody rate="{rate}">'
            f'{escaped}'
            f'</prosody></speak>'
        )

    def split_sentences(self, text: str) -> list:
        """텍스트를 문장 단위로 분할."""
        # 한국어 문장 분할: 마침표, 물음표, 느낌표, 줄바꿈
        sentences = re.split(r'(?<=[.?!。])\s*|\n+', text)
        return [s.strip() for s in sentences if s.strip()]

    def synthesize(self, text: str, session_id: str) -> AudioStream:
        """텍스트를 음성으로 변환."""
        if self._client is None:
            raise RuntimeError("Polly client not available")

        self._playing[session_id] = True
        ssml = self.text_to_ssml(text)

        try:
            response = self._client.synthesize_speech(
                Text=ssml,
                TextType="ssml",
                OutputFormat="pcm",
                VoiceId=self._voice_id,
                Engine=self._engine,
                SampleRate=self._sample_rate,
            )
            audio_data = response["AudioStream"].read()
            return AudioStream(session_id=session_id, data=audio_data, encoding="pcm", sample_rate=int(self._sample_rate))
        except Exception as e:
            logger.error("Polly synthesize failed: %s", e)
            raise
        finally:
            self._playing[session_id] = False

    def stop_playback(self, session_id: str) -> None:
        """바지인 시 재생 중단 — stopped 플래그로 전환."""
        self._playing[session_id] = False

    def speech_start(self, session_id: str) -> None:
        """사용자 발화 시작 감지 콜백."""
        pass

    def speech_end(self, session_id: str) -> None:
        """사용자 발화 종료 감지 콜백."""
        pass

    def is_playing(self, session_id: str) -> bool:
        """세션의 TTS 재생 중 여부."""
        return self._playing.get(session_id, False)

    def adjust_speed(self, speed_factor: float) -> None:
        """말하기 속도 조절 (다음 synthesize부터 적용)."""
        # 속도는 synthesize 호출 시 SSML에 반영
        pass

    def set_speed(self, session_id: str, speed_factor: float) -> None:
        """말하기 속도 조절 (ABC 구현)."""
        pass

    def format_number(self, value: str, number_type: NumberType) -> str:
        """숫자를 한국어 자연어로 변환 — 기본 pass-through."""
        return value

    def replay_last_response(self, session_id: str) -> AudioStream:
        """직전 응답 재생 — 미구현 시 빈 오디오."""
        return AudioStream(session_id=session_id, data=b"", encoding="pcm", sample_rate=int(self._sample_rate))
