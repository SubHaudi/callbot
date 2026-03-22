"""callbot.voice_io.fallback_stt — FallbackSTTEngine 래퍼 (FR-003)

주 STT 엔진 실패 시 STTFallbackError를 발생시켜 텍스트 폴백을 트리거한다.
별도 폴백 STT 엔진 없음 — VoiceServer가 이 에러를 catch하여 FR-009 텍스트 모드로 전환.
"""
from __future__ import annotations

import logging
from typing import Optional

from callbot.voice_io.stt_engine import STTEngine
from callbot.voice_io.models import AudioStream, PartialResult, STTResult, StreamHandle

logger = logging.getLogger(__name__)


class STTFallbackError(Exception):
    """주 STT 엔진 실패 시 발생. VoiceServer가 텍스트 폴백을 트리거하는 신호."""
    pass


class FallbackSTTEngine(STTEngine):
    """주 STT 엔진을 래핑하여 항상 STTEngine을 반환하는 래퍼.

    주 엔진 실패 시 STTFallbackError를 발생시킨다.
    vendor_factory.create_stt_engine()의 Union 반환타입을 제거하기 위한 래퍼 (C-05).
    """

    def __init__(self, primary: STTEngine) -> None:
        self._primary = primary

    def start_stream(self, session_id: str) -> StreamHandle:
        try:
            return self._primary.start_stream(session_id)
        except Exception as e:
            logger.error("STT start_stream failed: %s", e)
            raise STTFallbackError(f"STT 서비스 시작 실패: {e}") from e

    def process_audio_chunk(self, handle: StreamHandle, audio: bytes) -> PartialResult:
        try:
            return self._primary.process_audio_chunk(handle, audio)
        except Exception as e:
            logger.error("STT process_audio_chunk failed: %s", e)
            raise STTFallbackError(f"STT 오디오 처리 실패: {e}") from e

    def get_final_result(self, handle: StreamHandle) -> STTResult:
        try:
            return self._primary.get_final_result(handle)
        except Exception as e:
            logger.error("STT get_final_result failed: %s", e)
            raise STTFallbackError(f"STT 최종 결과 실패: {e}") from e

    def activate_barge_in(self, session_id: str) -> None:
        try:
            self._primary.activate_barge_in(session_id)
        except Exception as e:
            logger.warning("STT activate_barge_in failed: %s", e)

    def stop_stream(self, handle: StreamHandle) -> None:
        try:
            self._primary.stop_stream(handle)
        except Exception:
            pass  # 정리 실패는 무시

    def cancel(self, handle: StreamHandle) -> None:
        try:
            self._primary.cancel(handle)
        except Exception:
            pass  # 취소 실패는 무시

    def health_check(self) -> bool:
        """주 엔진 헬스체크 위임."""
        if hasattr(self._primary, "health_check"):
            return self._primary.health_check()
        return True

    def close(self) -> None:
        """주 엔진 리소스 해제 위임."""
        if hasattr(self._primary, "close"):
            self._primary.close()
