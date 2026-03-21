"""callbot.server.pipeline — Turn 처리 파이프라인

Phase C 재설계: PIF → Orchestrator → (intent 기반 분기) → Business API → LLM → 응답.
모든 컴포넌트는 DI로 주입한다.
"""
from __future__ import annotations

import asyncio
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from callbot.orchestrator.enums import ActionType

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=20)

# C-06: 정규식 기반 PII 패턴 (순서 중요: 긴 패턴 먼저)
_PII_PATTERNS: list[tuple[re.Pattern, str]] = [
    # 카드번호: 하이픈/공백/점 구분 (긴 패턴 먼저)
    (re.compile(r"\d{4}[-\s.]\d{4}[-\s.]\d{4}[-\s.]\d{4}"), "[카드번호]"),
    (re.compile(r"\b\d{16}\b"), "[카드번호]"),                    # 연속 16자리
    # 주민번호: 하이픈/공백/점 구분
    (re.compile(r"\d{6}[-\s.][1-4]\d{6}"), "[주민번호]"),
    # 전화번호: 하이픈/공백/점 구분
    (re.compile(r"\d{2,3}[-\s.]\d{3,4}[-\s.]\d{4}"), "[전화번호]"),
    (re.compile(r"01[016789]\d{7,8}"), "[전화번호]"),            # 01012345678
]


def _get_retry_count(session) -> int:
    """세션에서 재시도 카운트를 안전하게 조회."""
    val = getattr(session, "_multi_step_retry_count", 0)
    return val if isinstance(val, int) else 0


def _mask_pii_regex(text: str) -> str:
    """정규식 기반 PII 마스킹. CustomerInfo 없이도 작동."""
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


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
        prompt_loader: Optional[Any] = None,
        metrics_collector: Optional[Any] = None,
    ) -> None:
        self._pif = pif
        self._orchestrator = orchestrator
        self._session_manager = session_manager
        self._llm_engine = llm_engine
        self._external_system = external_system
        self._pii_masker = pii_masker
        self._prompt_loader = prompt_loader
        self._metrics = metrics_collector

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

        # PII 마스킹 (M-37 + C-06: DI masker + regex fallback)
        masked_text = text
        if self._pii_masker is not None:
            mask_result = await loop.run_in_executor(
                _executor, self._pii_masker.mask, text
            )
            masked_text = mask_result if isinstance(mask_result, str) else mask_result.masked_text
        # 정규식 PII 패턴 (DI masker와 무관하게 항상 적용)
        masked_text = _mask_pii_regex(masked_text)

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
        """비즈니스 로직: intent → API 호출 → LLM 응답 생성.

        다단계 플로우:
        - PLAN_CHANGE: Turn 1(목록) → Turn 2(선택) → Turn 3(확인/실행)
        - ADDON_CANCEL: Turn 1(목록) → Turn 2(확인/실행)
        """
        from callbot.nlu.enums import Intent

        intent_result = action.context.get("intent")

        # 다단계 플로우: pending_intent가 있으면 이전 턴의 연속
        pending = getattr(session, "pending_intent", None)
        if pending is not None:
            return await self._handle_multi_step_continuation(
                loop, session, masked_text, pending
            )

        intent = getattr(intent_result, "primary_intent", None) if intent_result else None

        # 다단계 플로우 시작
        if intent == Intent.PLAN_CHANGE:
            return await self._start_plan_change(loop, session)
        if intent == Intent.ADDON_CANCEL:
            return await self._start_addon_cancel(loop, session)

        # 일반 1회성 조회
        api_result_data: Optional[dict] = None
        if intent_result is not None and self._external_system is not None:
            api_result_data = await self._dispatch_business_api(
                loop, intent_result
            )

        intent_name = intent.name if intent else None
        return await self._generate_llm_response(
            loop, masked_text, api_result_data, intent_name=intent_name
        )

    async def _start_plan_change(
        self, loop: asyncio.AbstractEventLoop, session: Any
    ) -> str:
        """요금제 변경 Turn 1: 현재 요금제 목록을 조회하여 제시."""
        from callbot.business.enums import BillingOperation

        if self._external_system is None:
            return "시스템 점검 중입니다. 잠시 후 다시 시도해주세요."

        result = await loop.run_in_executor(
            _executor,
            self._external_system.call_billing_api,
            BillingOperation.QUERY_PLANS,
            {},
        )

        if not result.is_success:
            return "요금제 정보를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."

        plans = result.data.get("plans", [])
        current = result.data.get("current_plan", {})

        # 세션에 pending 상태 저장
        session.pending_intent = "PLAN_CHANGE_SELECT"
        if hasattr(session, "plan_list_context"):
            from callbot.session.models import PlanListContext
            session.plan_list_context = PlanListContext(
                available_plans=plans,
                current_page=0,
                page_size=len(plans),
                is_exhausted=False,
                current_plan=current if isinstance(current, dict) else {},
            )

        plan_lines = "\n".join(
            f"  {i+1}. {p['name']} — 월 {p['monthly_fee']:,}원"
            for i, p in enumerate(plans)
        )
        current_name = current.get("name", "알 수 없음") if isinstance(current, dict) else str(current)
        return (
            f"현재 요금제는 '{current_name}'입니다.\n"
            f"변경 가능한 요금제:\n{plan_lines}\n"
            "변경하실 요금제 번호를 말씀해주세요. (취소하려면 '취소')"
        )

    async def _start_addon_cancel(
        self, loop: asyncio.AbstractEventLoop, session: Any
    ) -> str:
        """부가서비스 해지 Turn 1: 부가서비스 목록 제시 (FakeSystem은 addons 리스트 보유)."""
        # pending 상태 저장
        session.pending_intent = "ADDON_CANCEL_SELECT"
        return (
            "해지할 부가서비스를 말씀해주세요.\n"
            "예: '데이터 쉐어링 해지' (취소하려면 '취소')"
        )

    async def _handle_multi_step_continuation(
        self,
        loop: asyncio.AbstractEventLoop,
        session: Any,
        masked_text: str,
        pending: str,
    ) -> str:
        """다단계 플로우 연속 턴 처리."""
        # 취소 처리
        if "취소" in masked_text:
            session.pending_intent = None
            if hasattr(session, "plan_list_context"):
                session.plan_list_context = None
            return "요청이 취소되었습니다. 다른 도움이 필요하시면 말씀해주세요."

        if pending == "PLAN_CHANGE_SELECT":
            return await self._handle_plan_select(loop, session, masked_text)
        if pending == "PLAN_CHANGE_CONFIRM":
            return await self._handle_plan_confirm(loop, session, masked_text)
        if pending == "ADDON_CANCEL_SELECT":
            return await self._handle_addon_select(loop, session, masked_text)

        # 알 수 없는 pending 상태 초기화
        session.pending_intent = None
        return "처리할 수 없는 요청입니다. 다시 말씀해주세요."

    async def _handle_plan_select(
        self, loop: asyncio.AbstractEventLoop, session: Any, text: str
    ) -> str:
        """요금제 변경 Turn 2: 사용자 선택 → 확인 요청."""
        plc = getattr(session, "plan_list_context", None)
        plans = plc.available_plans if plc else []

        # 번호 또는 이름으로 선택
        selected = None
        try:
            idx = int(text.strip()) - 1
            if 0 <= idx < len(plans):
                selected = plans[idx]
        except (ValueError, TypeError):
            # 이름 매칭
            for p in plans:
                if p["name"] in text:
                    selected = p
                    break

        if selected is None:
            retry_count = _get_retry_count(session) + 1
            session._multi_step_retry_count = retry_count
            if retry_count >= 3:
                session.pending_intent = None
                session.plan_list_context = None
                session._multi_step_retry_count = 0
                return "입력 오류가 반복되어 요금제 변경을 취소합니다. 다시 시도하시려면 말씀해주세요."
            return f"올바른 번호 또는 요금제명을 말씀해주세요. ({retry_count}/3회 시도)"

        session.pending_intent = "PLAN_CHANGE_CONFIRM"
        session._selected_plan = selected  # 임시 저장
        session._multi_step_retry_count = 0  # 성공 시 리셋
        return (
            f"'{selected['name']}' (월 {selected['monthly_fee']:,}원)으로 변경하시겠습니까?\n"
            "'네' 또는 '아니오'로 답변해주세요."
        )

    async def _handle_plan_confirm(
        self, loop: asyncio.AbstractEventLoop, session: Any, text: str
    ) -> str:
        """요금제 변경 Turn 3: 확인 → 실행."""
        from callbot.business.enums import BillingOperation

        if "아니" in text or "취소" in text:
            session.pending_intent = None
            session.plan_list_context = None
            return "요금제 변경이 취소되었습니다."

        selected = getattr(session, "_selected_plan", None)
        if selected is None or self._external_system is None:
            session.pending_intent = None
            return "처리 중 오류가 발생했습니다. 다시 시도해주세요."

        result = await loop.run_in_executor(
            _executor,
            self._external_system.call_billing_api,
            BillingOperation.CHANGE_PLAN,
            {"plan_name": selected["name"]},
        )

        # 상태 초기화
        session.pending_intent = None
        session.plan_list_context = None
        if hasattr(session, "_selected_plan"):
            del session._selected_plan

        if result.is_success:
            return f"요금제가 '{selected['name']}'으로 변경되었습니다."
        return "요금제 변경에 실패했습니다. 잠시 후 다시 시도해주세요."

    async def _handle_addon_select(
        self, loop: asyncio.AbstractEventLoop, session: Any, text: str
    ) -> str:
        """부가서비스 해지: 사용자 선택 → 즉시 실행."""
        from callbot.business.enums import BillingOperation

        if self._external_system is None:
            session.pending_intent = None
            return "시스템 점검 중입니다."

        # TODO: 실제 운영 시 외부 API 조회로 대체 (현재는 FakeSystem 전용 하드코딩)
        addon_map = {
            "데이터 쉐어링": "ADD-001",
            "안심 데이터": "ADD-002",
            "약정 보험": "ADD-003",
        }

        addon_id = None
        addon_name = None
        for name, aid in addon_map.items():
            if name in text:
                addon_id = aid
                addon_name = name
                break

        if addon_id is None:
            retry_count = _get_retry_count(session) + 1
            session._multi_step_retry_count = retry_count
            if retry_count >= 3:
                session.pending_intent = None
                session._multi_step_retry_count = 0
                return "입력 오류가 반복되어 부가서비스 해지를 취소합니다. 다시 시도하시려면 말씀해주세요."
            return f"해지할 부가서비스 이름을 정확히 말씀해주세요. ({retry_count}/3회 시도)"

        result = await loop.run_in_executor(
            _executor,
            self._external_system.call_billing_api,
            BillingOperation.CANCEL_ADDON,
            {"addon_id": addon_id},
        )

        session.pending_intent = None
        session._multi_step_retry_count = 0  # 성공 시 리셋

        if result.is_success:
            return f"'{addon_name}' 부가서비스가 해지되었습니다."
        error_reason = result.data.get("reason", "알 수 없는 오류") if result.data else "알 수 없는 오류"
        return f"해지 실패: {error_reason}"

    async def _generate_llm_response(
        self,
        loop: asyncio.AbstractEventLoop,
        masked_text: str,
        api_result_data: Optional[dict],
        intent_name: Optional[str] = None,
    ) -> str:
        """LLM 응답 생성 (공통)."""
        if self._prompt_loader is not None:
            context_text = self._prompt_loader.get_prompt(
                intent_name=intent_name,
                api_result=api_result_data,
            )
        else:
            system_prompt = (
                "당신은 AnyTelecom 고객센터 AI 상담사입니다. "
                "고객의 요청에 친절하고 정확하게 답변하세요."
            )
            if api_result_data is not None:
                context_text = f"{system_prompt}\n\n[API 조회 결과]\n{api_result_data}"
            else:
                context_text = system_prompt

        return await loop.run_in_executor(
            _executor, self._llm_engine.generate, context_text, masked_text
        )

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
