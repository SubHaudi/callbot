"""callbot.voice_io.transcribe_stt — AWS Transcribe Streaming STT 엔진

실시간 스트리밍 STT. boto3 transcribe-streaming 클라이언트 사용.
한국어(ko-KR) 고정. PCM 16kHz 16bit mono 입력.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Optional, Any, Dict

from callbot.voice_io.stt_engine import STTEngine
from callbot.voice_io.models import PartialResult, STTResult, StreamHandle

logger = logging.getLogger(__name__)


class TranscribeSTTEngine(STTEngine):
    """AWS Transcribe Streaming 기반 실시간 STT 엔진.

    - 언어: ko-KR
    - 입력: PCM 16kHz 16bit mono
    - 스트리밍: start_stream → process_audio_chunk(반복) → get_final_result
    - partial result 지원
    """

    def __init__(
        self,
        transcribe_client: Optional[Any] = None,
        language_code: str = "ko-KR",
        sample_rate: int = 16000,
        confidence_threshold: float = 0.5,
        region: str = "ap-northeast-2",
    ) -> None:
        self._language_code = language_code
        self._sample_rate = sample_rate
        self._confidence_threshold = confidence_threshold
        self._region = region

        if transcribe_client is not None:
            self._client = transcribe_client
        else:
            try:
                import boto3
                self._client = boto3.client(
                    "transcribe",
                    region_name=region,
                )
            except Exception as e:
                logger.warning("boto3 transcribe client init failed: %s", e)
                self._client = None

        # 세션별 오디오 버퍼 + partial results
        self._buffers: Dict[str, bytes] = {}
        self._partials: Dict[str, str] = {}

    def start_stream(self, session_id: str) -> StreamHandle:
        stream_id = str(uuid.uuid4())
        self._buffers[stream_id] = b""
        self._partials[stream_id] = ""
        return StreamHandle(session_id=session_id, stream_id=stream_id)

    def process_audio_chunk(self, handle: StreamHandle, audio: bytes) -> PartialResult:
        """오디오 청크 누적. 실제 스트리밍은 get_final_result에서 일괄 처리.

        TODO: 실제 프로덕션에서는 async 스트리밍으로 청크 단위 전송 + partial result 수신.
        현재는 MVP로 일괄 처리.
        """
        self._buffers[handle.stream_id] = self._buffers.get(handle.stream_id, b"") + audio
        return PartialResult(text=self._partials.get(handle.stream_id, ""), is_final=False)

    def get_final_result(self, handle: StreamHandle) -> STTResult:
        """누적 오디오를 Transcribe로 전송하여 최종 결과 반환.

        MVP: start_transcription_job 대신 동기식 일괄 처리.
        프로덕션: start_stream_transcription (WebSocket) 사용.
        """
        audio_data = self._buffers.pop(handle.stream_id, b"")
        self._partials.pop(handle.stream_id, None)

        if not audio_data:
            return STTResult.create(
                text="", confidence=0.0, processing_time_ms=0,
                threshold=self._confidence_threshold,
            )

        if self._client is None:
            raise RuntimeError("Transcribe client not available")

        t0 = time.perf_counter()

        try:
            result = self._transcribe_sync(audio_data)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)

            return STTResult.create(
                text=result["text"],
                confidence=result["confidence"],
                processing_time_ms=elapsed_ms,
                threshold=self._confidence_threshold,
            )
        except Exception as e:
            logger.error("Transcribe failed: %s", e)
            raise

    def _transcribe_sync(self, audio_data: bytes) -> Dict[str, Any]:
        """동기식 Transcribe 호출 (MVP).

        실제로는 start_stream_transcription을 사용해야 하지만,
        MVP에서는 S3 업로드 없이 직접 바이트를 보내는 방식 사용.
        """
        import tempfile
        import json
        import os

        # Transcribe는 S3 URI 또는 MediaFileUri를 요구하므로
        # MVP에서는 임시 파일 → S3 업로드 → transcription job 사용
        # 또는 boto3 transcribe streaming client 사용

        # 실제 구현: amazon-transcribe-streaming-sdk 사용
        # pip install amazon-transcribe
        # 여기서는 boto3 start_transcription_job 대신
        # 직접 streaming SDK를 쓰는 게 맞지만, 현재는 mock 대상

        # Mock-friendly interface: _client.transcribe(audio_data) 호출
        # 실제 SDK 연동은 별도 어댑터로 분리 예정
        response = self._client.transcribe(
            audio_data,
            language_code=self._language_code,
            sample_rate=self._sample_rate,
        )
        return {
            "text": response.get("text", ""),
            "confidence": response.get("confidence", 0.0),
        }

    def activate_barge_in(self, session_id: str) -> None:
        pass  # Barge-in은 VoiceServer 레벨에서 처리

    def stop_stream(self, handle: StreamHandle) -> None:
        self._buffers.pop(handle.stream_id, None)
        self._partials.pop(handle.stream_id, None)

    def cancel(self, handle: StreamHandle) -> None:
        self._buffers.pop(handle.stream_id, None)
        self._partials.pop(handle.stream_id, None)
