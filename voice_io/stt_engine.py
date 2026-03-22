"""callbot.voice_io.stt_engine — STT 엔진 인터페이스 및 기본 구현"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from callbot.voice_io.barge_in import BargeInHandler
from callbot.voice_io.models import (
    AudioStream,
    PartialResult,
    STTResult,
    StreamHandle,
)

# ---------------------------------------------------------------------------
# 설정 상수
# ---------------------------------------------------------------------------

STT_CONFIDENCE_THRESHOLD_DEFAULT: float = 0.5
STT_CONFIDENCE_THRESHOLD_MIN: float = 0.3
STT_CONFIDENCE_THRESHOLD_MAX: float = 0.7

VAD_SILENCE_SEC_DEFAULT: float = 1.5
VAD_SILENCE_SEC_MIN: float = 1.0
VAD_SILENCE_SEC_MAX: float = 3.0


# ---------------------------------------------------------------------------
# 추상 기반 클래스
# ---------------------------------------------------------------------------

class STTEngine(ABC):
    """STT 엔진 추상 기반 클래스."""

    @abstractmethod
    def start_stream(self, session_id: str) -> StreamHandle:
        """실시간 스트리밍 음성 인식 시작."""
        ...

    @abstractmethod
    def process_audio_chunk(self, handle: StreamHandle, audio: bytes) -> PartialResult:
        """오디오 청크 처리, 중간 결과 반환."""
        ...

    @abstractmethod
    def get_final_result(self, handle: StreamHandle) -> STTResult:
        """VAD 발화 종료 감지 후 최종 텍스트 반환 (P95 1초)."""
        ...

    @abstractmethod
    def activate_barge_in(self, session_id: str) -> None:
        """바지인 감지 시 STT 즉시 활성화 (P95 200ms)."""
        ...

    @abstractmethod
    def stop_stream(self, handle: StreamHandle) -> None:
        """스트리밍 세션을 정상 종료하고 리소스를 해제한다."""
        ...

    @abstractmethod
    def cancel(self, handle: StreamHandle) -> None:
        """스트리밍 세션을 즉시 취소하고 리소스를 해제한다."""
        ...


# ---------------------------------------------------------------------------
# 기본 구현체 (벤더 SDK 없이 동작, 테스트용)
# ---------------------------------------------------------------------------

class STTEngineBase(STTEngine):
    """벤더 SDK 없이 동작하는 STT 엔진 기본 구현체.

    실제 음성 인식은 수행하지 않으며, 테스트 및 개발 환경에서 사용한다.
    """

    def __init__(
        self,
        stt_confidence_threshold: float = STT_CONFIDENCE_THRESHOLD_DEFAULT,
        vad_silence_sec: float = VAD_SILENCE_SEC_DEFAULT,
        barge_in_handler: BargeInHandler | None = None,
    ) -> None:
        if not (STT_CONFIDENCE_THRESHOLD_MIN <= stt_confidence_threshold <= STT_CONFIDENCE_THRESHOLD_MAX):
            raise ValueError(
                f"stt_confidence_threshold must be in "
                f"[{STT_CONFIDENCE_THRESHOLD_MIN}, {STT_CONFIDENCE_THRESHOLD_MAX}], "
                f"got {stt_confidence_threshold}"
            )
        if not (VAD_SILENCE_SEC_MIN <= vad_silence_sec <= VAD_SILENCE_SEC_MAX):
            raise ValueError(
                f"vad_silence_sec must be in "
                f"[{VAD_SILENCE_SEC_MIN}, {VAD_SILENCE_SEC_MAX}], "
                f"got {vad_silence_sec}"
            )

        self.stt_confidence_threshold = stt_confidence_threshold
        self.vad_silence_sec = vad_silence_sec
        self._barge_in_handler: BargeInHandler | None = barge_in_handler

        # 세션별 누적 오디오 버퍼 (stream_id → bytes)
        self._buffers: dict[str, bytes] = {}

    def start_stream(self, session_id: str) -> StreamHandle:
        """스트리밍 세션을 시작하고 StreamHandle을 반환한다."""
        stream_id = str(uuid.uuid4())
        self._buffers[stream_id] = b""
        return StreamHandle(session_id=session_id, stream_id=stream_id)

    def process_audio_chunk(self, handle: StreamHandle, audio: bytes) -> PartialResult:
        """오디오 청크를 버퍼에 누적하고 중간 결과를 반환한다."""
        self._buffers[handle.stream_id] = self._buffers.get(handle.stream_id, b"") + audio
        return PartialResult(text="", is_final=False)

    def get_final_result(self, handle: StreamHandle) -> STTResult:
        """누적된 오디오로 최종 STTResult를 반환한다.

        STTEngineBase는 실제 인식을 수행하지 않으므로 빈 텍스트와
        confidence=0.0을 반환한다. is_valid 및 failure_type은
        STTResult.create() 팩토리가 threshold 기준으로 자동 결정한다.
        """
        # 버퍼 정리
        self._buffers.pop(handle.stream_id, None)

        return STTResult.create(
            text="",
            confidence=0.0,
            processing_time_ms=0,
            threshold=self.stt_confidence_threshold,
        )

    def activate_barge_in(self, session_id: str) -> None:
        """바지인 활성화 — handler가 등록된 경우 TTS stop_playback()을 호출한다."""
        if self._barge_in_handler is not None:
            self._barge_in_handler.stop_playback(session_id)

    def stop_stream(self, handle: StreamHandle) -> None:
        """스트리밍 세션을 정상 종료하고 버퍼를 정리한다."""
        self._buffers.pop(handle.stream_id, None)

    def cancel(self, handle: StreamHandle) -> None:
        """스트리밍 세션을 즉시 취소하고 버퍼를 정리한다."""
        self._buffers.pop(handle.stream_id, None)
