"""Phase E E2E 파이프라인 통합 테스트 (TASK-016)."""

import asyncio
from callbot.server.pipeline import TurnPipeline
from tests.test_e2e_phase_c import _make_pipeline, _run


class TestPhaseEE2E:
    """TurnPipeline.process() 경유 E2E — 구어체 + 인텐트 전환 + 시스템 인텐트."""

    def test_colloquial_billing_via_pipeline(self):
        """구어체 "요금 좀 알려줘"가 파이프라인 경유로 정상 처리."""
        pipeline, sm = _make_pipeline()
        session = sm.create_session("01012345678")
        r = _run(pipeline.process(session.session_id, "01012345678", "요금 좀 알려줘"))
        # 요금 조회 응답이어야 함
        assert r.response_text is not None
        assert len(r.response_text) > 0

    def test_colloquial_addon_cancel_via_pipeline(self):
        """구어체 "부가 좀 빼줘"가 부가서비스 해지 플로우 시작."""
        pipeline, sm = _make_pipeline()
        session = sm.create_session("01012345678")
        r = _run(pipeline.process(session.session_id, "01012345678", "부가 좀 빼줘"))
        assert "부가서비스" in r.response_text or "해지" in r.response_text

    def test_intent_switch_during_plan_change(self):
        """요금제 변경 중 "요금 좀 알려줘" → 전환 확인."""
        pipeline, sm = _make_pipeline()
        session = sm.create_session("01012345678")

        # Turn 1: 요금제 변경 시작
        r1 = _run(pipeline.process(session.session_id, "01012345678", "요금제 변경해주세요"))
        assert "요금제" in r1.response_text

        # Turn 2: 다른 인텐트 발화 → 전환 확인
        r2 = _run(pipeline.process(session.session_id, "01012345678", "요금 좀 알려줘"))
        assert "전환" in r2.response_text or "취소" in r2.response_text

    def test_system_intent_during_plan_change(self):
        """요금제 변경 중 "종료해줘" → 전환 확인 없이 처리."""
        pipeline, sm = _make_pipeline()
        session = sm.create_session("01012345678")

        r1 = _run(pipeline.process(session.session_id, "01012345678", "요금제 변경해주세요"))
        assert "요금제" in r1.response_text

        # 시스템 인텐트 — 전환 확인 없이 즉시 처리
        r2 = _run(pipeline.process(session.session_id, "01012345678", "종료해줘"))
        # 전환 확인이 아닌 종료/기존 핸들링
        assert "전환" not in r2.response_text
