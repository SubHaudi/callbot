"""callbot.voice_io.voice_server — WebSocket 음성 파이프라인 서버

STT → TurnPipeline → TTS 파이프라인을 WebSocket으로 연결.
STT 실패 시 텍스트 폴백 모드로 전환 (FR-005).
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Any, Dict

from callbot.voice_io.fallback_stt import STTFallbackError

logger = logging.getLogger(__name__)


@dataclass
class VoiceSession:
    """음성 WebSocket 세션."""
    session_id: str
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    is_text_fallback: bool = False
    is_tts_playing: bool = False
    vad_silence_sec: float = 1.0
    turn_count: int = 0
    stt_handle: Any = None  # STT 스트리밍 핸들
    stt_stream_active: bool = False
    partial_queue: Any = None  # asyncio.Queue — initialized in __post_init__
    pipeline_session_id: Optional[str] = None  # Pipeline(Redis) 세션 ID — 첫 턴에서 생성

    def __post_init__(self) -> None:
        self._validate_vad_silence(self.vad_silence_sec)
        if self.partial_queue is None:
            self.partial_queue = asyncio.Queue()

    @staticmethod
    def _validate_vad_silence(value: float) -> None:
        """VAD 침묵 감지 시간 검증 (0.5~2.0초)."""
        if not (0.5 <= value <= 2.0):
            raise ValueError(f"vad_silence_sec must be in [0.5, 2.0], got {value}")

    def touch(self) -> None:
        """활동 시간 갱신."""
        self.last_activity = time.time()


class VoiceServer:
    """WebSocket 음성 파이프라인 서버."""

    def __init__(
        self,
        stt_engine: Any = None,
        tts_engine: Any = None,
        pipeline: Any = None,
        audio_converter: Any = None,
        max_sessions: int = 10,
        session_timeout_sec: float = 300.0,
    ) -> None:
        self._stt = stt_engine
        self._tts = tts_engine
        self._pipeline = pipeline
        self._converter = audio_converter
        self._max_sessions = max_sessions
        self._session_timeout_sec = session_timeout_sec
        self._sessions: Dict[str, VoiceSession] = {}
        self._cleanup_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

    # ---- Session lifecycle ----

    def create_session(self, vad_silence_sec: float = 1.0) -> VoiceSession:
        """새 음성 세션 생성."""
        if len(self._sessions) >= self._max_sessions:
            raise RuntimeError(f"max sessions ({self._max_sessions}) reached")
        session_id = str(uuid.uuid4())
        session = VoiceSession(session_id=session_id, vad_silence_sec=vad_silence_sec)
        self._sessions[session_id] = session
        return session

    def end_session(self, session_id: str) -> None:
        """세션 종료. 음성 데이터 디스크 저장 안 함 (NFR-003)."""
        session = self._sessions.pop(session_id, None)
        if session and session.stt_handle and self._stt:
            try:
                self._stt.stop_stream(session.stt_handle)
            except Exception as e:
                logger.warning("Failed to stop STT stream on session end: %s", e)
            session.stt_handle = None
            session.stt_stream_active = False

    def get_session(self, session_id: str) -> Optional[VoiceSession]:
        return self._sessions.get(session_id)

    # ---- Timeout cleanup ----

    def cleanup_expired_sessions(self) -> None:
        """타임아웃된 세션 정리."""
        now = time.time()
        expired = [
            sid for sid, s in self._sessions.items()
            if (now - s.last_activity) > self._session_timeout_sec
        ]
        for sid in expired:
            logger.info("Session %s expired (timeout %.0fs)", sid, self._session_timeout_sec)
            self.end_session(sid)

    async def start_cleanup_loop(self, interval: float = 30.0) -> None:
        """백그라운드 세션 정리 루프 (FR-007)."""
        while True:
            await asyncio.sleep(interval)
            self.cleanup_expired_sessions()

    def start_background_cleanup(self) -> None:
        """cleanup 루프를 asyncio 태스크로 시작."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self.start_cleanup_loop())

    def stop_background_cleanup(self) -> None:
        """cleanup 루프 정지."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()

    # ---- Audio handling ----

    async def handle_audio_chunk(self, session_id: str, chunk: bytes) -> Dict[str, Any]:
        """오디오 청크를 STT 스트림에 전달. 첫 청크 시 스트림 자동 생성."""
        session = self._sessions.get(session_id)
        if session is None:
            return {"error": "session_not_found"}
        session.touch()

        if session.is_text_fallback:
            return {"error": "text_fallback_mode", "message": "음성 인식 불가 — 텍스트로 입력해주세요"}

        if self._stt is None:
            return {"error": "stt_not_configured"}

        # 첫 청크: STT 스트림 자동 생성
        if not session.stt_stream_active:
            try:
                handle = await asyncio.to_thread(
                    self._stt.start_stream, session_id
                )
                session.stt_handle = handle
                session.stt_stream_active = True
            except Exception as e:
                logger.warning("STT start_stream failed: %s", e)
                return {"error": "stt_start_failed", "detail": str(e)}

        # 청크 전달 + partial result
        try:
            partial = await asyncio.to_thread(
                self._stt.process_audio_chunk, session.stt_handle, chunk
            )
            if partial and partial.text:
                await session.partial_queue.put({
                    "text": partial.text,
                    "is_final": getattr(partial, "is_final", False),
                })
            return {"status": "ok"}
        except Exception as e:
            logger.warning("STT process_audio_chunk failed: %s", e)
            return {"error": "stt_chunk_failed", "detail": str(e)}

    async def handle_end(self, session_id: str) -> Dict[str, Any]:
        """발화 종료 — STT 최종 결과 → Pipeline → TTS → 응답."""
        t0 = time.perf_counter()

        session = self._sessions.get(session_id)
        if session is None:
            return {"error": "session_not_found"}
        session.touch()

        # STT final result
        if not session.stt_stream_active or session.stt_handle is None:
            return {"error": "no_active_stt_stream"}

        try:
            stt_result = await asyncio.to_thread(
                self._stt.get_final_result, session.stt_handle
            )
        except STTFallbackError:
            session.is_text_fallback = True
            logger.warning("STT failed for session %s, switching to text fallback", session_id)
            return {"error": "stt_failed", "message": "음성 인식 실패 — 텍스트 모드로 전환합니다"}
        except Exception as e:
            logger.warning("STT get_final_result failed: %s", e)
            return {"error": "stt_final_failed", "detail": str(e)}
        finally:
            # 스트림 종료
            try:
                await asyncio.to_thread(self._stt.stop_stream, session.stt_handle)
            except Exception:
                pass
            session.stt_stream_active = False
            session.stt_handle = None

        transcript = stt_result.text if stt_result else ""
        if not transcript:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            return {"transcript": "", "response_text": "", "processing_ms": elapsed_ms}

        # Pipeline
        if self._pipeline is None:
            return {"error": "pipeline_not_configured"}

        try:
            pipeline_session_id = session.pipeline_session_id
            pipeline_result = await self._pipeline.process(
                session_id=pipeline_session_id, caller_id=session_id, text=transcript
            )
            if pipeline_session_id is None:
                session.pipeline_session_id = pipeline_result.session_id
        except Exception as e:
            logger.warning("Pipeline failed: %s", e)
            return {"error": "pipeline_failed", "detail": str(e)}

        # TTS
        tts_audio = None
        if self._tts:
            try:
                session.is_tts_playing = True
                tts_result = await asyncio.to_thread(
                    self._tts.synthesize, pipeline_result.response_text, session_id
                )
                tts_audio = tts_result.data
            except Exception as e:
                logger.warning("TTS failed: %s", e)
            finally:
                session.is_tts_playing = False

        session.turn_count += 1
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        result: Dict[str, Any] = {
            "transcript": transcript,
            "response_text": pipeline_result.response_text,
            "processing_ms": elapsed_ms,
        }
        if tts_audio is not None:
            result["audio"] = tts_audio
            result["audio_b64"] = base64.b64encode(tts_audio).decode("ascii")
        return result

    async def handle_audio(self, session_id: str, audio_data: bytes) -> Dict[str, Any]:
        """레거시 하위 호환: 전체 오디오를 chunk+end로 위임."""
        chunk_result = await self.handle_audio_chunk(session_id, audio_data)
        if "error" in chunk_result:
            return chunk_result
        return await self.handle_end(session_id)

    # ---- Text handling (fallback) ----

    async def handle_text(self, session_id: str, text: str) -> Dict[str, Any]:
        """텍스트 입력 처리. Pipeline 없으면 에러 반환."""
        session = self._sessions.get(session_id)
        if session is None:
            return {"error": "session_not_found"}

        session.touch()

        if not self._pipeline:
            return {"error": "pipeline_not_configured", "message": "Pipeline이 설정되지 않았습니다"}

        t0 = time.perf_counter()

        try:
            # 첫 턴: pipeline_session_id가 없으면 None → 세션 자동 생성
            pipeline_session_id = session.pipeline_session_id
            pipeline_result = await self._pipeline.process(
                session_id=pipeline_session_id, caller_id=session_id, text=text
            )
            # 첫 턴 후 pipeline session_id 저장
            if pipeline_session_id is None:
                session.pipeline_session_id = pipeline_result.session_id
        except Exception as e:
            logger.warning("Pipeline failed: %s", e)
            return {"error": "pipeline_failed", "detail": str(e)}

        tts_audio = None
        if self._tts:
            try:
                session.is_tts_playing = True
                tts_result = await asyncio.to_thread(
                    self._tts.synthesize, pipeline_result.response_text, session_id
                )
                tts_audio = tts_result.data
            except Exception as e:
                logger.warning("TTS failed: %s", e)
            finally:
                session.is_tts_playing = False

        session.turn_count += 1
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        result: Dict[str, Any] = {
            "response_text": pipeline_result.response_text,
            "processing_ms": elapsed_ms,
        }
        if tts_audio is not None:
            result["audio"] = tts_audio
            result["audio_b64"] = base64.b64encode(tts_audio).decode("ascii")
        return result

    # ---- Barge-in ----

    async def handle_interrupt(self, session_id: str) -> Dict[str, Any]:
        """Barge-in: TTS 재생 중단 + STT 재시작 (FR-004)."""
        session = self._sessions.get(session_id)
        if session is None:
            return {"error": "session_not_found"}

        if not session.is_tts_playing and not session.stt_handle:
            return {"status": "not_playing"}

        # TTS 중단
        if session.is_tts_playing and self._tts:
            await asyncio.to_thread(self._tts.stop_playback, session_id)
            session.is_tts_playing = False

        # STT 핸들 정리 + 재시작 (FR-004)
        if session.stt_handle and self._stt:
            try:
                await asyncio.to_thread(self._stt.stop_stream, session.stt_handle)
            except Exception as e:
                logger.warning("Failed to stop STT stream on interrupt: %s", e)
            session.stt_handle = None
            session.stt_stream_active = False

        return {"status": "interrupted"}

    @property
    def active_session_count(self) -> int:
        return len(self._sessions)
