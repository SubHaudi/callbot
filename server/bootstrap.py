"""callbot.server.bootstrap — 서버 컴포넌트 조립 (테스트 가능한 단위).

_lifespan의 조립 로직을 분리하여 개별 테스트가 가능하도록 한다.
필수 의존성(DB, Pipeline) 실패 시 즉시 예외, 선택 의존성(STT, TTS) 실패 시 None.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


def assemble_pipeline(
    pg_connection: Any,
    redis_store: Any,
    bedrock_service: Any,
) -> Any:
    """Pipeline + 관련 컴포넌트를 조립한다.

    Args:
        pg_connection: PostgreSQL 커넥션 (None이면 RuntimeError)
        redis_store: Redis 세션 스토어 (optional, 현재 미사용)
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

    pipeline = TurnPipeline(
        pif=pif,
        orchestrator=orchestrator,
        session_manager=session_manager,
        llm_engine=bedrock_service,
    )
    logger.info("Pipeline 조립 완료")
    return pipeline


def assemble_voice_server(
    pipeline: Any = None,
    stt_engine: Any = None,
    tts_engine: Any = None,
) -> Any:
    """VoiceServer를 조립한다. STT/TTS 없으면 텍스트 전용 모드.

    Note: background cleanup은 호출자가 start_background_cleanup()으로 시작해야 함.

    Returns:
        조립된 VoiceServer 인스턴스
    """
    from callbot.voice_io.voice_server import VoiceServer

    vs = VoiceServer(
        pipeline=pipeline,
        stt_engine=stt_engine,
        tts_engine=tts_engine,
    )
    return vs


def init_stt_engine() -> Optional[Any]:
    """TranscribeSTTEngine 초기화. 실패 시 None (선택 의존성)."""
    try:
        from callbot.voice_io.transcribe_stt import TranscribeSTTEngine
        engine = TranscribeSTTEngine()
        logger.info("TranscribeSTTEngine 초기화 성공")
        return engine
    except Exception as e:
        logger.warning("STT 엔진 초기화 실패 (텍스트 전용 모드): %s", e)
        return None


def init_tts_engine() -> Optional[Any]:
    """PollyTTSEngine 초기화. 실패 시 None (선택 의존성)."""
    try:
        from callbot.voice_io.polly_tts import PollyTTSEngine
        import boto3
        polly_client = boto3.client("polly", region_name=os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-2"))
        engine = PollyTTSEngine(polly_client=polly_client)
        logger.info("PollyTTSEngine 초기화 성공")
        return engine
    except Exception as e:
        logger.warning("TTS 엔진 초기화 실패 (텍스트 전용 모드): %s", e)
        return None
