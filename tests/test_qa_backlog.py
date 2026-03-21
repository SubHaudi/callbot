"""QA 백로그 테스트 — #3 동일 요금제 변경 차단, #7 싱글톤 격리."""

import asyncio
import pytest
from unittest.mock import MagicMock
from datetime import datetime

from callbot.session.models import SessionContext, PlanListContext


class FakeLLMEngine:
    async def generate(self, *args, **kwargs):
        return "테스트 응답"


class FakeExternalSystem:
    def __init__(self, plans=None, current_plan=None):
        self._plans = plans or []
        self._current = current_plan or {}

    def call_billing_api(self, operation, params):
        result = MagicMock()
        result.is_success = True
        result.data = {"plans": self._plans, "current_plan": self._current}
        return result


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
        plan_list_context=None,
        pending_intent=None,
        pending_classification=None,
    )


class TestSamePlanBlock:
    """QA #3: 동일 요금제 변경 시도 시 차단."""

    def test_same_plan_blocked(self):
        from callbot.server.pipeline import TurnPipeline

        pipeline = TurnPipeline(
            pif=MagicMock(),
            orchestrator=MagicMock(),
            session_manager=MagicMock(),
            llm_engine=FakeLLMEngine(),
            external_system=FakeExternalSystem(),
        )

        session = _make_session()
        session.pending_intent = "PLAN_CHANGE_SELECT"
        session.plan_list_context = PlanListContext(
            available_plans=[
                {"name": "5G 스탠다드", "monthly_fee": 55000},
                {"name": "5G 프리미엄", "monthly_fee": 85000},
            ],
            current_page=0,
            page_size=2,
            is_exhausted=False,
            current_plan={"name": "5G 스탠다드", "monthly_fee": 55000},
        )

        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            pipeline._handle_plan_select(loop, session, "1")
        )

        assert "현재 이용 중인 요금제" in result
        assert "5G 스탠다드" in result
        # pending_intent should still be PLAN_CHANGE_SELECT (not advanced)
        assert session.pending_intent == "PLAN_CHANGE_SELECT"

    def test_different_plan_allowed(self):
        from callbot.server.pipeline import TurnPipeline

        pipeline = TurnPipeline(
            pif=MagicMock(),
            orchestrator=MagicMock(),
            session_manager=MagicMock(),
            llm_engine=FakeLLMEngine(),
            external_system=FakeExternalSystem(),
        )

        session = _make_session()
        session.pending_intent = "PLAN_CHANGE_SELECT"
        session.plan_list_context = PlanListContext(
            available_plans=[
                {"name": "5G 스탠다드", "monthly_fee": 55000},
                {"name": "5G 프리미엄", "monthly_fee": 85000},
            ],
            current_page=0,
            page_size=2,
            is_exhausted=False,
            current_plan={"name": "5G 스탠다드", "monthly_fee": 55000},
        )

        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            pipeline._handle_plan_select(loop, session, "2")
        )

        assert "5G 프리미엄" in result
        assert "변경하시겠습니까" in result
        assert session.pending_intent == "PLAN_CHANGE_CONFIRM"
