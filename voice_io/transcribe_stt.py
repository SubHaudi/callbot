"""callbot.voice_io.transcribe_stt — AWS Transcribe Streaming STT 엔진 (FR-001)

Phase 1: mock 클라이언트 주입 시 기존 mock 경로, 미주입 시 실제 AWS Transcribe Streaming API.
한국어 ko-KR. PCM 16kHz 16bit mono 입력.
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


class _ResultHandler:
    """Transcribe Streaming 이벤트 핸들러 — partial/final 결과 수집."""

    def __init__(self, output_stream: Any) -> None:
        self._output_stream = output_stream
        self.final_text = ""
        self.confidence_sum = 0.0
        self.confidence_count = 0

    async def handle_events(self) -> None:
        async for event in self._output_stream:
            # SDK model: TranscriptEvent.transcript.results[]
            transcript = getattr(event, "transcript", None)
            if transcript is None:
                continue
            results = getattr(transcript, "results", None) or []
            for result in results:
                is_partial = getattr(result, "is_partial", True)
                alternatives = getattr(result, "alternatives", None) or []
                for alt in alternatives:
                    if not is_partial:
                        text = getattr(alt, "transcript", "")
                        if text:
                            if self.final_text:
                                self.final_text += " " + text
                            else:
                                self.final_text = text
                        items = getattr(alt, "items", None) or []
                        for item in items:
                            conf = getattr(item, "confidence", None)
                            if conf is not None:
                                self.confidence_sum += float(conf)
                                self.confidence_count += 1

    @property
    def avg_confidence(self) -> float:
        if self.confidence_count == 0:
            return 0.0
        return self.confidence_sum / self.confidence_count


class TranscribeSTTEngine(STTEngine):
    """AWS Transcribe Streaming 기반 실시간 STT 엔진.

    - transcribe_client 주입 시: mock 모드 (기존 테스트 호환)
    - transcribe_client=None: 실제 AWS Transcribe Streaming API 사용
    """

    def __init__(
        self,
        transcribe_client: Optional[Any] = None,
        language_code: str = "ko-KR",
        sample_rate: int = 16000,
        confidence_threshold: float = 0.5,
        region: str = "ap-northeast-2",
        streaming_timeout: float = 10.0,
    ) -> None:
        self._language_code = language_code
        self._sample_rate = sample_rate
        self._confidence_threshold = confidence_threshold
        self._region = region
        self._streaming_timeout = streaming_timeout
        self._mock_client = transcribe_client  # None이면 실제 API

        # 세션별 오디오 버퍼 + partial results
        self._buffers: Dict[str, bytes] = {}
        self._partials: Dict[str, str] = {}

    def start_stream(self, session_id: str) -> StreamHandle:
        stream_id = str(uuid.uuid4())
        self._buffers[stream_id] = b""
        self._partials[stream_id] = ""
        return StreamHandle(session_id=session_id, stream_id=stream_id)

    def process_audio_chunk(self, handle: StreamHandle, audio: bytes) -> PartialResult:
        """오디오 청크 누적. partial result 반환."""
        self._buffers[handle.stream_id] = self._buffers.get(handle.stream_id, b"") + audio
        return PartialResult(text=self._partials.get(handle.stream_id, ""), is_final=False)

    def get_final_result(self, handle: StreamHandle) -> STTResult:
        """누적 오디오로 Transcribe 호출하여 최종 결과 반환."""
        audio_data = self._buffers.pop(handle.stream_id, b"")
        self._partials.pop(handle.stream_id, None)

        if not audio_data:
            return STTResult.create(
                text="", confidence=0.0, processing_time_ms=0,
                threshold=self._confidence_threshold,
            )

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
        """동기식 Transcribe 호출.

        - mock_client 주입 시: 기존 mock 경로 (테스트 호환)
        - mock_client=None: 실제 AWS Transcribe Streaming API
        """
        if self._mock_client is not None:
            response = self._mock_client.transcribe(
                audio_data,
                language_code=self._language_code,
                sample_rate=self._sample_rate,
            )
            return {
                "text": response.get("text", ""),
                "confidence": response.get("confidence", 0.0),
            }

        # 이미 실행 중인 이벤트 루프가 있으면 새 스레드에서 실행
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, self._transcribe_streaming(audio_data))
                return future.result(timeout=self._streaming_timeout)
        else:
            return asyncio.run(self._transcribe_streaming(audio_data))

    async def _transcribe_streaming(self, audio_data: bytes) -> Dict[str, Any]:
        """실제 AWS Transcribe Streaming API 호출."""
        from amazon_transcribe.client import TranscribeStreamingClient

        client = TranscribeStreamingClient(region=self._region)
        stream = await client.start_stream_transcription(
            language_code=self._language_code,
            media_sample_rate_hz=self._sample_rate,
            media_encoding="pcm",
        )

        # 청크 단위 전송 (100ms = 3200 bytes at 16kHz 16bit mono)
        CHUNK_SIZE = 3200
        for i in range(0, len(audio_data), CHUNK_SIZE):
            chunk = audio_data[i:i + CHUNK_SIZE]
            await stream.input_stream.send_audio_event(audio_chunk=chunk)
        await stream.input_stream.end_stream()

        # 결과 수신 — SDK의 TranscriptResultStream 사용 (타임아웃 적용)
        handler = _ResultHandler(stream.output_stream)
        try:
            await asyncio.wait_for(handler.handle_events(), timeout=self._streaming_timeout)
        except asyncio.TimeoutError:
            logger.warning("Transcribe streaming timed out after %.1fs", self._streaming_timeout)

        return {
            "text": handler.final_text.strip(),
            "confidence": handler.avg_confidence,
        }

    def activate_barge_in(self, session_id: str) -> None:
        pass  # Barge-in은 VoiceServer 레벨에서 처리

    def stop_stream(self, handle: StreamHandle) -> None:
        self._buffers.pop(handle.stream_id, None)
        self._partials.pop(handle.stream_id, None)

    def cancel(self, handle: StreamHandle) -> None:
        self._buffers.pop(handle.stream_id, None)
        self._partials.pop(handle.stream_id, None)

    def health_check(self) -> bool:
        return True

    def close(self) -> None:
        self._buffers.clear()
        self._partials.clear()
