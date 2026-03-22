"""callbot.server.bootstrap — 서버 컴포넌트 조립 (테스트 가능한 단위)."""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def assemble_pipeline(
    pg_connection: Any,
    redis_store: Any,
    bedrock_service: Any,
) -> Any:
    """Pipeline + 관련 컴포넌트를 조립한다.

    Args:
        pg_connection: PostgreSQL 커넥션 풀 (None이면 RuntimeError)
        redis_store: Redis 세션 스토어 (optional)
        bedrock_service: Bedrock LLM 서비스

    Returns:
        조립된 TurnPipeline 인스턴스

    Raises:
        RuntimeError: 필수 의존성(pg_connection)이 None인 경우
    """
    if pg_connection is None:
        raise RuntimeError("PostgreSQL connection required for Pipeline assembly")

    from callbot.nlu.prompt_injection_filter import PromptInjectionFilter
    from callbot.orchestrator.conversation_orchestrator import ConversationOrchestrator
    from callbot.session.session_manager import SessionManager
    from callbot.session.session_store import InMemorySessionStore
    from callbot.session.repository import CallbotDBRepository
    from server.pipeline import TurnPipeline

    pif = PromptInjectionFilter()
    repository = CallbotDBRepository(db=pg_connection)
    session_store = InMemorySessionStore()
    session_manager = SessionManager(
        repository=repository,
        session_store=session_store,
    )
    orchestrator = ConversationOrchestrator()

    return TurnPipeline(
        pif=pif,
        orchestrator=orchestrator,
        session_manager=session_manager,
        llm_engine=bedrock_service,
    )


def assemble_voice_server(
    pipeline: Any = None,
    stt_engine: Any = None,
    tts_engine: Any = None,
) -> Any:
    """VoiceServer를 조립한다. STT/TTS 없으면 텍스트 전용 모드."""
    from callbot.voice_io.voice_server import VoiceServer

    vs = VoiceServer(
        pipeline=pipeline,
        stt_engine=stt_engine,
        tts_engine=tts_engine,
    )
    return vs


def init_stt_engine() -> Optional[Any]:
    """TranscribeSTTEngine 초기화. 실패 시 None."""
    try:
        from callbot.voice_io.transcribe_stt import TranscribeSTTEngine
        engine = TranscribeSTTEngine()
        logger.info("TranscribeSTTEngine 초기화 성공")
        return engine
    except Exception as e:
        logger.warning("STT 엔진 초기화 실패 (텍스트 전용 모드): %s", e)
        return None


def init_tts_engine() -> Optional[Any]:
    """PollyTTSEngine 초기화. 실패 시 None."""
    try:
        from callbot.voice_io.polly_tts import PollyTTSEngine
        engine = PollyTTSEngine()
        logger.info("PollyTTSEngine 초기화 성공")
        return engine
    except Exception as e:
        logger.warning("TTS 엔진 초기화 실패 (텍스트 전용 모드): %s", e)
        return None
