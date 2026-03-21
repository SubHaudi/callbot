"""callbot.server.pipeline — Turn 처리 파이프라인

Phase C 재설계: PIF → Orchestrator → (intent 기반 분기) → Business API → LLM → 응답.
모든 컴포넌트는 DI로 주입한다.
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from callbot.orchestrator.enums import ActionType

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=20)


@dataclass
class TurnResult:
    """파이프라인 처리 결과."""
    session_id: str
    response_text: str
    action_type: str
    context: dict = field(default_factory=dict)


class ExternalSystemProtocol(Protocol):
    """외부 시스템 프로토콜 (DI용)."""
    def call_billing_api(self, operation: Any, params: dict, timeout_sec: float = 5.0) -> Any: ...
    def call_customer_db(self, operation: Any, params: dict, timeout_sec: float = 1.0) -> Any: ...


class TurnPipeline:
    """PIF → Orchestrator → Business API → LLM 파이프라인.

    Phase C: intent 기반 비즈니스 로직 분기, API 결과를 LLM에 전달.
    """

    def __init__(
        self,
        pif: Any,
        orchestrator: Any,
        session_manager: Any,
        llm_engine: Any,
        external_system: Optional[ExternalSystemProtocol] = None,
        pii_masker: Optional[Any] = None,
    ) -> None:
        self._pif = pif
        self._orchestrator = orchestrator
        self._session_manager = session_manager
        self._llm_engine = llm_engine
        self._external_system = external_system
        self._pii_masker = pii_masker

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

        # PII 마스킹 (M-37)
        masked_text = text
        if self._pii_masker is not None:
            mask_result = await loop.run_in_executor(
                _executor, self._pii_masker.mask, text
            )
            masked_text = mask_result if isinstance(mask_result, str) else mask_result.masked_text

        # PIF (마스킹된 텍스트 사용)
        filter_result = await loop.run_in_executor(
            _executor, self._pif.filter, masked_text, session.session_id
        )

        # Orchestrator — intent 분류 포함
        action = await loop.run_in_executor(
            _executor, self._orchestrator.process_turn, session, filter_result
        )

        # 분기
        if action.action_type == ActionType.PROCESS_BUSINESS:
            response_text = await self._handle_business(
                loop, session, action, masked_text
            )
        elif action.action_type == ActionType.SESSION_END:
            response_text = "이용해 주셔서 감사합니다. 좋은 하루 보내세요."
        elif action.action_type == ActionType.SYSTEM_CONTROL:
            response_text = action.context.get("message", "다시 한번 말씀해주시겠어요?")
        elif action.action_type == ActionType.ESCALATE:
            response_text = "상담원에게 전환합니다. 잠시만 기다려주세요."
        elif action.action_type == ActionType.AUTH_REQUIRED:
            response_text = "본인 확인이 필요합니다. 생년월일 6자리를 말씀해주세요."
        else:
            response_text = "처리할 수 없는 요청입니다."

        return TurnResult(
            session_id=session.session_id,
            response_text=response_text,
            action_type=action.action_type.name,
            context=action.context if isinstance(action.context, dict) else {},
        )

    async def _handle_business(
        self,
        loop: asyncio.AbstractEventLoop,
        session: Any,
        action: Any,
        masked_text: str,
    ) -> str:
        """비즈니스 로직: intent → API 호출 → LLM 응답 생성."""
        intent_result = action.context.get("intent")
        api_result_data: Optional[dict] = None

        # intent 기반 API 호출 (C-03: api_result를 LLM에 전달)
        if intent_result is not None and self._external_system is not None:
            api_result_data = await self._dispatch_business_api(
                loop, intent_result
            )

        # LLM에 system_prompt + api_result + masked_text 전달
        system_prompt = (
            "당신은 AnyTelecom 고객센터 AI 상담사입니다. "
            "고객의 요청에 친절하고 정확하게 답변하세요."
        )

        # api_result가 있으면 LLM context에 포함
        if api_result_data is not None:
            context_text = f"{system_prompt}\n\n[API 조회 결과]\n{api_result_data}"
        else:
            context_text = system_prompt

        response_text = await loop.run_in_executor(
            _executor, self._llm_engine.generate, context_text, masked_text
        )

        return response_text

    async def _dispatch_business_api(
        self,
        loop: asyncio.AbstractEventLoop,
        intent_result: Any,
    ) -> Optional[dict]:
        """intent에 따라 적절한 비즈니스 API를 호출한다."""
        from callbot.business.enums import BillingOperation
        from callbot.nlu.enums import Intent

        intent = getattr(intent_result, "primary_intent", None)
        if intent is None:
            return None

        op_map = {
            Intent.BILLING_INQUIRY: BillingOperation.QUERY_BILLING,
            Intent.PAYMENT_CHECK: BillingOperation.QUERY_PAYMENT,
            Intent.PLAN_INQUIRY: BillingOperation.QUERY_PLANS,
            Intent.PLAN_CHANGE: BillingOperation.CHANGE_PLAN,
            Intent.DATA_USAGE_INQUIRY: BillingOperation.QUERY_DATA_USAGE,
            Intent.ADDON_CANCEL: BillingOperation.CANCEL_ADDON,
        }

        operation = op_map.get(intent)
        if operation is None:
            return None

        try:
            result = await loop.run_in_executor(
                _executor,
                self._external_system.call_billing_api,
                operation,
                {},
            )
            return result.data if result.is_success else {"error": str(result.error)}
        except Exception as e:
            logger.error("Business API call failed: %s", e)
            return {"error": str(e)}
