"""callbot.server.pipeline — Turn 처리 파이프라인"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Optional

from callbot.orchestrator.enums import ActionType

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=20)


@dataclass
class TurnResult:
    """파이프라인 처리 결과."""
    session_id: str
    response_text: str
    action_type: str
    context: dict


class TurnPipeline:
    """PIF → Orchestrator → LLM/Business 파이프라인."""

    def __init__(
        self,
        pif: Any,
        orchestrator: Any,
        session_manager: Any,
        llm_engine: Any,
    ) -> None:
        self._pif = pif
        self._orchestrator = orchestrator
        self._session_manager = session_manager
        self._llm_engine = llm_engine

    async def process(
        self,
        session_id: Optional[str],
        caller_id: str,
        text: str,
    ) -> TurnResult:
        """턴을 처리하고 결과를 반환한다."""
        loop = asyncio.get_event_loop()

        # 세션 조회 또는 생성
        if session_id is None:
            session = await loop.run_in_executor(
                _executor, self._session_manager.create_session, caller_id
            )
        else:
            session = await loop.run_in_executor(
                _executor, self._session_manager._store.load, session_id
            )

        # PIF
        filter_result = await loop.run_in_executor(
            _executor, self._pif.filter, text, session.session_id
        )

        # Orchestrator
        action = await loop.run_in_executor(
            _executor, self._orchestrator.process_turn, session, filter_result
        )

        # 분기
        if action.action_type == ActionType.PROCESS_BUSINESS:
            response_text = await loop.run_in_executor(
                _executor, self._llm_engine.generate, text
            )
        elif action.action_type == ActionType.SYSTEM_CONTROL:
            response_text = action.context.get("message", "다시 한번 말씀해주시겠어요?")
        elif action.action_type == ActionType.ESCALATE:
            response_text = "상담원에게 전환합니다. 잠시만 기다려주세요."
        else:
            response_text = "처리할 수 없는 요청입니다."

        return TurnResult(
            session_id=session.session_id,
            response_text=response_text,
            action_type=action.action_type.name,
            context=action.context if isinstance(action.context, dict) else {},
        )
