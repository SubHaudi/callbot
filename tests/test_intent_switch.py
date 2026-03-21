"""Phase E 인텐트 전환 테스트."""

import asyncio
from unittest.mock import MagicMock
from datetime import datetime

from callbot.session.models import SessionContext, PlanListContext
from callbot.nlu.enums import Intent


class FakeLLMEngine:
    async def generate(self, *args, **kwargs):
        return "테스트 응답"


def _make_session():
    return SessionContext(
        session_id="test-1",
        caller_id="010-0000-0000",
        is_authenticated=True,
        customer_info=None,
        auth_status=None,
        turns=[],
        business_turn_count=0,
        start_time=datetime.now(),
        tts_speed_factor=1.0,
        cached_billing_data=None,
        injection_detection_count=0,
        masking_restore_failure_count=0,
        plan_list_context=PlanListContext(
            available_plans=[{"name": "5G 스탠다드", "monthly_fee": 55000}],
            current_page=0, page_size=1, is_exhausted=False,
            current_plan={"name": "LTE 베이직", "monthly_fee": 35000},
        ),
        pending_intent="PLAN_CHANGE_SELECT",
        pending_classification=None,
        pending_switch_intent=None,
    )


class TestIntentSwitchDetection:
    """FR-004: pending_intent 상태에서 새 인텐트 감지 → 전환 확인."""

    def test_switch_detected_returns_confirmation(self):
        from callbot.server.pipeline import TurnPipeline

        pipeline = TurnPipeline(
            pif=MagicMock(),
            orchestrator=MagicMock(),
            session_manager=MagicMock(),
            llm_engine=FakeLLMEngine(),
            external_system=MagicMock(),
        )

        session = _make_session()
        loop = asyncio.get_event_loop()

        # "부가서비스 해지해줘" — 새 인텐트 감지
        result = loop.run_until_complete(
            pipeline._handle_intent_switch(loop, session, "부가서비스 해지해줘")
        )

        assert "취소" in result or "전환" in result
        assert "부가서비스" in result or "해지" in result
        assert session.pending_switch_intent is not None


class TestIntentSwitchConfirmation:
    """FR-005/006: 전환 확인 Yes/No 응답 처리."""

    def _make_pipeline(self):
        from callbot.server.pipeline import TurnPipeline
        return TurnPipeline(
            pif=MagicMock(),
            orchestrator=MagicMock(),
            session_manager=MagicMock(),
            llm_engine=FakeLLMEngine(),
            external_system=MagicMock(),
        )

    def test_confirm_yes_clears_state(self):
        """'네' 응답 → 기존 플로우 취소 + 상태 정리."""
        pipeline = self._make_pipeline()
        session = _make_session()
        session.pending_switch_intent = Intent.BILLING_INQUIRY

        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            pipeline._handle_switch_confirm(loop, session, "네")
        )

        # 기존 상태 정리 확인
        assert session.pending_intent is None
        assert session.pending_switch_intent is None
        assert getattr(session, "_multi_step_retry_count", 0) == 0

    def test_confirm_yes_synonym(self):
        """'맞아' 동의어도 동작."""
        pipeline = self._make_pipeline()
        session = _make_session()
        session.pending_switch_intent = Intent.BILLING_INQUIRY

        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            pipeline._handle_switch_confirm(loop, session, "맞아")
        )
        assert session.pending_intent is None

    def test_confirm_no_keeps_flow(self):
        """'아니' 응답 → 기존 플로우 유지."""
        pipeline = self._make_pipeline()
        session = _make_session()
        session.pending_switch_intent = Intent.BILLING_INQUIRY

        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            pipeline._handle_switch_confirm(loop, session, "아니")
        )

        assert "계속" in result or "기존" in result
        assert session.pending_switch_intent is None
        assert session.pending_intent == "PLAN_CHANGE_SELECT"  # 기존 유지

    def test_confirm_no_synonym(self):
        """'계속' 동의어도 동작."""
        pipeline = self._make_pipeline()
        session = _make_session()
        session.pending_switch_intent = Intent.BILLING_INQUIRY

        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            pipeline._handle_switch_confirm(loop, session, "계속")
        )
        assert session.pending_intent == "PLAN_CHANGE_SELECT"


class TestSystemIntentBypass:
    """FR-007: 시스템 인텐트는 전환 확인 없이 즉시 처리."""

    def test_end_call_no_confirmation(self):
        from callbot.server.pipeline import TurnPipeline
        pipeline = TurnPipeline(
            pif=MagicMock(),
            orchestrator=MagicMock(),
            session_manager=MagicMock(),
            llm_engine=FakeLLMEngine(),
            external_system=MagicMock(),
        )

        session = _make_session()
        loop = asyncio.get_event_loop()

        # "종료" — 시스템 인텐트, 전환 확인 없이 None 반환
        result = loop.run_until_complete(
            pipeline._handle_intent_switch(loop, session, "종료해줘")
        )
        assert result is None
        assert session.pending_switch_intent is None
