"""callbot.voice_io.whisper_stt — faster-whisper 기반 STT 엔진 (FR-001)

환경변수 WHISPER_MODEL로 모델 크기 전환 가능 (small|medium).
faster-whisper 미설치 시 ImportError를 명확히 보고.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Optional

from callbot.voice_io.stt_engine import STTEngine
from callbot.voice_io.models import PartialResult, STTResult, StreamHandle

logger = logging.getLogger(__name__)

# faster-whisper import guard
try:
    from faster_whisper import WhisperModel
    _WHISPER_AVAILABLE = True
except ImportError:
    _WHISPER_AVAILABLE = False
    WhisperModel = None  # type: ignore


class WhisperSTTEngine(STTEngine):
    """faster-whisper 기반 한국어 STT 엔진.

    - 모델: small (INT8 양자화, CPU)
    - 언어: ko 고정
    - 환경변수 WHISPER_MODEL=small|medium
    """

    def __init__(
        self,
        model_size: Optional[str] = None,
        confidence_threshold: float = 0.5,
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        if not _WHISPER_AVAILABLE:
            raise ImportError(
                "faster-whisper is not installed. "
                "Install with: pip install faster-whisper"
            )
        self._model_size = model_size or os.environ.get("WHISPER_MODEL", "small")
        self._confidence_threshold = confidence_threshold
        self._device = device
        self._compute_type = compute_type
        self._model: Optional[WhisperModel] = None
        self._buffers: dict[str, bytes] = {}

    def _ensure_model(self) -> WhisperModel:
        """모델 lazy loading."""
        if self._model is None:
            logger.info("Loading faster-whisper model: %s (%s)", self._model_size, self._compute_type)
            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
            )
        return self._model

    def start_stream(self, session_id: str) -> StreamHandle:
        stream_id = str(uuid.uuid4())
        self._buffers[stream_id] = b""
        return StreamHandle(session_id=session_id, stream_id=stream_id)

    def process_audio_chunk(self, handle: StreamHandle, audio: bytes) -> PartialResult:
        self._buffers[handle.stream_id] = self._buffers.get(handle.stream_id, b"") + audio
        return PartialResult(text="", is_final=False)

    def get_final_result(self, handle: StreamHandle) -> STTResult:
        audio_data = self._buffers.pop(handle.stream_id, b"")
        if not audio_data:
            return STTResult.create(
                text="", confidence=0.0, processing_time_ms=0,
                threshold=self._confidence_threshold,
            )

        model = self._ensure_model()
        t0 = time.perf_counter()

        # faster-whisper transcribe expects a file path or numpy array
        # For streaming, we write to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
            f.write(audio_data)
            f.flush()
            segments, info = model.transcribe(
                f.name,
                language="ko",
                beam_size=5,
            )
            text = " ".join(seg.text.strip() for seg in segments)

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        # faster-whisper doesn't provide per-segment confidence easily
        # Use language probability as proxy
        confidence = getattr(info, "language_probability", 0.8)

        return STTResult.create(
            text=text,
            confidence=confidence,
            processing_time_ms=elapsed_ms,
            threshold=self._confidence_threshold,
        )

    def activate_barge_in(self, session_id: str) -> None:
        pass  # Barge-in은 VoiceServer 레벨에서 처리

    def stop_stream(self, handle: StreamHandle) -> None:
        self._buffers.pop(handle.stream_id, None)

    def cancel(self, handle: StreamHandle) -> None:
        self._buffers.pop(handle.stream_id, None)
