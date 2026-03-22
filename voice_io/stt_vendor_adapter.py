"""callbot.voice_io.stt_vendor_adapter — Amazon Transcribe Streaming 기반 STT 벤더 어댑터

STTEngine 추상 클래스를 상속하고 VendorAdapter 프로토콜을 구현한다.
모든 메서드는 동기 시그니처를 유지하며, 벤더 SDK의 HTTP/2 스트리밍은 내부에서 처리한다.

client 파라미터로 SDK 클라이언트를 주입받아 테스트 시 Mock 객체를 사용할 수 있다.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from callbot.voice_io.barge_in import BargeInHandler
from callbot.voice_io.exceptions import VendorConnectionError
from callbot.voice_io.models import PartialResult, STTResult, StreamHandle
from callbot.voice_io.stt_engine import (
    STT_CONFIDENCE_THRESHOLD_DEFAULT,
    STT_CONFIDENCE_THRESHOLD_MAX,
    STT_CONFIDENCE_THRESHOLD_MIN,
    STTEngine,
    VAD_SILENCE_SEC_DEFAULT,
    VAD_SILENCE_SEC_MAX,
    VAD_SILENCE_SEC_MIN,
)
from callbot.voice_io.vendor_adapter import VendorAdapter
from callbot.voice_io.vendor_config import VendorConfig

logger = logging.getLogger(__name__)

_VENDOR_ID = "aws-transcribe"


class STTVendorAdapter(STTEngine):
    """Amazon Transcribe Streaming 기반 STT 엔진 구현체.

    STTEngine 추상 클래스를 상속하고 VendorAdapter 프로토콜을 구현한다.
    모든 메서드는 동기 시그니처를 유지한다.

    client 파라미터(duck typing)로 SDK 클라이언트를 주입받는다.
    프로덕션에서는 TranscribeStreamingClient, 테스트에서는 Mock 객체를 사용한다.
    """

    def __init__(
        self,
        config: VendorConfig,
        stt_confidence_threshold: float = STT_CONFIDENCE_THRESHOLD_DEFAULT,
        vad_silence_sec: float = VAD_SILENCE_SEC_DEFAULT,
        barge_in_handler: BargeInHandler | None = None,
        client: Any = None,
    ) -> None:
        """AWS Transcribe Streaming 클라이언트를 초기화한다.

        Args:
            config: 벤더 연결 설정 (aws_region, stt_language_code, stt_sample_rate 등)
            stt_confidence_threshold: STT 확신도 임계값 (0.3~0.7)
            vad_silence_sec: VAD 침묵 감지 시간 (1.0~3.0)
            barge_in_handler: 바지인 핸들러 (선택)
            client: SDK 클라이언트 주입 (테스트용). None이면 boto3로 생성 시도.

        Raises:
            ValueError: 파라미터 범위 위반 시
            VendorConnectionError: SDK 클라이언트 생성 실패 시
        """
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

        self._config = config
        self.stt_confidence_threshold = stt_confidence_threshold
        self.vad_silence_sec = vad_silence_sec
        self._barge_in_handler = barge_in_handler
        self._vendor = _VENDOR_ID

        # SDK client — 주입 또는 boto3로 생성
        if client is not None:
            self._client = client
        else:
            try:
                import boto3

                self._client = boto3.client(
                    "transcribe",
                    region_name=config.aws_region,
                )
            except Exception as exc:
                raise VendorConnectionError(
                    vendor=self._vendor,
                    original_message=str(exc),
                ) from exc

        # 내부 상태
        self._streams: dict[str, Any] = {}  # stream_id → SDK 스트리밍 객체
        self._buffers: dict[str, bytes] = {}  # stream_id → 누적 오디오 버퍼
        self._cached_finals: dict[str, Any] = {}  # stream_id → 캐시된 최종 결과
        self._start_times: dict[str, float] = {}  # stream_id → 시작 시각

    # ------------------------------------------------------------------
    # STTEngine 추상 메서드 구현
    # ------------------------------------------------------------------

    def start_stream(self, session_id: str) -> StreamHandle:
        """Amazon Transcribe StartStreamTranscription HTTP/2 스트리밍 연결을 수립한다.

        Returns:
            StreamHandle: 스트리밍 세션 핸들

        Raises:
            VendorConnectionError: SDK 스트리밍 연결 실패 시
        """
        stream_id = str(uuid.uuid4())
        start = time.monotonic()
        try:
            stream = self._client.start_stream(
                language_code=self._config.stt_language_code,
                media_encoding=self._config.stt_media_encoding,
                sample_rate=self._config.stt_sample_rate,
            )
            self._streams[stream_id] = stream
            self._buffers[stream_id] = b""
            self._cached_finals[stream_id] = None
            self._start_times[stream_id] = time.monotonic()
            return StreamHandle(session_id=session_id, stream_id=stream_id)
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "STT vendor '%s' start_stream failed: %s (type: %s, elapsed: %dms)",
                self._vendor,
                exc,
                type(exc).__name__,
                elapsed_ms,
            )
            raise VendorConnectionError(
                vendor=self._vendor,
                original_message=str(exc),
            ) from exc

    def process_audio_chunk(self, handle: StreamHandle, audio: bytes) -> PartialResult:
        """오디오 청크를 SDK 스트리밍 채널로 전송하고 중간 결과를 반환한다.

        is_final=True 결과는 내부에 캐시하여 get_final_result에서 즉시 반환한다.

        Returns:
            PartialResult: 중간 인식 결과

        Raises:
            VendorConnectionError: SDK 전송 실패 또는 활성 스트림 없음
        """
        stream = self._streams.get(handle.stream_id)
        if stream is None:
            raise VendorConnectionError(
                vendor=self._vendor,
                original_message=f"No active stream for stream_id={handle.stream_id}",
            )

        try:
            # 오디오 버퍼 누적
            self._buffers[handle.stream_id] = (
                self._buffers.get(handle.stream_id, b"") + audio
            )

            # SDK로 오디오 전송 및 중간 결과 수신
            result = stream.send_audio(audio)

            text = getattr(result, "text", "")
            is_final = getattr(result, "is_final", False)

            # is_final=True 결과 캐시
            if is_final:
                self._cached_finals[handle.stream_id] = result

            return PartialResult(text=text, is_final=is_final)
        except VendorConnectionError:
            raise
        except Exception as exc:
            elapsed_ms = int(
                (time.monotonic() - self._start_times.get(handle.stream_id, time.monotonic()))
                * 1000
            )
            logger.error(
                "STT vendor '%s' process_audio_chunk failed: %s (type: %s, elapsed: %dms)",
                self._vendor,
                exc,
                type(exc).__name__,
                elapsed_ms,
            )
            raise VendorConnectionError(
                vendor=self._vendor,
                original_message=str(exc),
            ) from exc

    def get_final_result(self, handle: StreamHandle) -> STTResult:
        """캐시된 최종 결과 또는 SDK 최종 결과를 수신하여 STTResult를 반환한다.

        스트리밍 채널과 내부 버퍼를 해제하고 processing_time_ms를 기록한다.

        Returns:
            STTResult: 최종 인식 결과

        Raises:
            VendorConnectionError: SDK 결과 수신 실패 시
        """
        try:
            start = self._start_times.get(handle.stream_id, time.monotonic())

            # 캐시된 최종 결과 우선 사용
            cached = self._cached_finals.get(handle.stream_id)
            if cached is not None:
                text = getattr(cached, "text", "")
                confidence = getattr(cached, "confidence", 0.0)
            else:
                # SDK에서 최종 결과 수신
                stream = self._streams.get(handle.stream_id)
                if stream is not None:
                    result = stream.get_result()
                    text = getattr(result, "text", "")
                    confidence = getattr(result, "confidence", 0.0)
                else:
                    text = ""
                    confidence = 0.0

            processing_time_ms = int((time.monotonic() - start) * 1000)

            # 리소스 해제
            self._streams.pop(handle.stream_id, None)
            self._buffers.pop(handle.stream_id, None)
            self._cached_finals.pop(handle.stream_id, None)
            self._start_times.pop(handle.stream_id, None)

            return STTResult.create(
                text=text,
                confidence=confidence,
                processing_time_ms=processing_time_ms,
                threshold=self.stt_confidence_threshold,
            )
        except VendorConnectionError:
            raise
        except Exception as exc:
            elapsed_ms = int(
                (time.monotonic() - self._start_times.get(handle.stream_id, time.monotonic()))
                * 1000
            )
            logger.error(
                "STT vendor '%s' get_final_result failed: %s (type: %s, elapsed: %dms)",
                self._vendor,
                exc,
                type(exc).__name__,
                elapsed_ms,
            )
            raise VendorConnectionError(
                vendor=self._vendor,
                original_message=str(exc),
            ) from exc

    def activate_barge_in(self, session_id: str) -> None:
        """바지인 감지 시 BargeInHandler.stop_playback()을 호출하고 STT를 즉시 활성화한다."""
        if self._barge_in_handler is not None:
            self._barge_in_handler.stop_playback(session_id)

    # ------------------------------------------------------------------
    # VendorAdapter 프로토콜 구현
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """SDK 테스트 요청으로 연결 상태를 확인한다.

        Returns:
            True: 연결 정상, False: 연결 실패
        """
        try:
            self._client.health_check()
            return True
        except Exception:
            return False

    def close(self) -> None:
        """모든 활성 스트리밍 채널을 종료하고 SDK 클라이언트를 정리한다."""
        for stream_id in list(self._streams.keys()):
            try:
                stream = self._streams[stream_id]
                if hasattr(stream, "close"):
                    stream.close()
            except Exception as exc:
                logger.warning(
                    "Failed to close stream %s: %s", stream_id, exc
                )

        self._streams.clear()
        self._buffers.clear()
        self._cached_finals.clear()
        self._start_times.clear()

        if hasattr(self._client, "close"):
            try:
                self._client.close()
            except Exception as exc:
                logger.warning("Failed to close SDK client: %s", exc)

    def stop_stream(self, handle: StreamHandle) -> None:
        """스트리밍 세션을 정상 종료하고 리소스를 해제한다."""
        stream = self._streams.pop(handle.stream_id, None)
        if stream is not None and hasattr(stream, "close"):
            try:
                stream.close()
            except Exception as exc:
                logger.warning("Failed to stop stream %s: %s", handle.stream_id, exc)
        self._buffers.pop(handle.stream_id, None)
        self._cached_finals.pop(handle.stream_id, None)
        self._start_times.pop(handle.stream_id, None)

    def cancel(self, handle: StreamHandle) -> None:
        """스트리밍 세션을 즉시 취소하고 리소스를 해제한다."""
        self._streams.pop(handle.stream_id, None)
        self._buffers.pop(handle.stream_id, None)
        self._cached_finals.pop(handle.stream_id, None)
        self._start_times.pop(handle.stream_id, None)


# 벤더 팩토리에 AWS Transcribe 어댑터 등록
from callbot.voice_io.vendor_factory import register_stt_vendor
register_stt_vendor("aws-transcribe", STTVendorAdapter)
