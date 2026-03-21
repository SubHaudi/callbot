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
