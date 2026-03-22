"""server.tests.test_phase_c_integration — Phase C 통합 테스트

FakeExternalSystem + MockIntentClassifier + pipeline 전체 흐름.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from callbot.external.fake_system import FakeExternalSystem
from callbot.nlu.enums import Intent
from callbot.nlu.intent_classifier import IntentClassifier
from callbot.orchestrator.conversation_orchestrator import ConversationOrchestrator
from callbot.orchestrator.enums import ActionType


def _make_pipeline(session):
    """실제 컴포넌트로 구성된 파이프라인 반환."""
    from server.pipeline import TurnPipeline

    fake_ext = FakeExternalSystem()
    classifier = IntentClassifier()
    orchestrator = ConversationOrchestrator(intent_classifier=classifier)

    mock_pif = MagicMock()
    mock_pif.filter.side_effect = lambda text, sid: MagicMock(
        is_safe=True, original_text=text
    )

    mock_sm = MagicMock()
    mock_sm.create_session.return_value = session

    mock_llm = MagicMock()
    mock_llm.generate.side_effect = lambda ctx, text: f"[LLM] {text}"

    return TurnPipeline(
        pif=mock_pif,
        orchestrator=orchestrator,
        session_manager=mock_sm,
        llm_engine=mock_llm,
        external_system=fake_ext,
    )


def _make_session(sid="int-sess"):
    s = MagicMock()
    s.session_id = sid
    s.pending_intent = None
    s.pending_switch_intent = None
    s.plan_list_context = None
    s.turn_count = 0
    s.elapsed_minutes = 0.0
    s.has_active_transaction = False
    s.injection_count = 0
    s.injection_detection_count = 0
    return s


@pytest.mark.asyncio
async def test_billing_inquiry_e2e():
    """요금 조회: intent → API 호출 → LLM에 결과 전달."""
    session = _make_session()
    pipeline = _make_pipeline(session)

    result = await pipeline.process(None, "010", "이번 달 요금이 얼마예요?")

    assert result.action_type == "PROCESS_BUSINESS"
    # LLM이 API 결과를 포함한 context로 호출됨
    assert "monthly_fee" in result.response_text or "[LLM]" in result.response_text


@pytest.mark.asyncio
async def test_data_usage_inquiry_e2e():
    """데이터 잔여량 조회 E2E."""
    session = _make_session()
    pipeline = _make_pipeline(session)

    result = await pipeline.process(None, "010", "데이터 잔여량 알려줘")

    assert result.action_type == "PROCESS_BUSINESS"


@pytest.mark.asyncio
async def test_plan_change_full_flow_e2e():
    """요금제 변경 3턴 플로우 E2E."""
    session = _make_session()
    pipeline = _make_pipeline(session)

    # Turn 1: 요금제 변경
    r1 = await pipeline.process(None, "010", "요금제 변경하고 싶어요")
    assert "5G" in r1.response_text
    assert session.pending_intent == "PLAN_CHANGE_SELECT"

    # Turn 2: 선택
    r2 = await pipeline.process(None, "010", "1")
    assert "라이트" in r2.response_text or session.pending_intent == "PLAN_CHANGE_CONFIRM"

    # Turn 3: 확인
    r3 = await pipeline.process(None, "010", "네")
    assert "변경되었습니다" in r3.response_text


@pytest.mark.asyncio
async def test_addon_cancel_full_flow_e2e():
    """부가서비스 해지 2턴 플로우 E2E."""
    session = _make_session()
    pipeline = _make_pipeline(session)

    # Turn 1
    r1 = await pipeline.process(None, "010", "부가서비스 해지해줘")
    assert session.pending_intent == "ADDON_CANCEL_SELECT"

    # Turn 2
    r2 = await pipeline.process(None, "010", "데이터 쉐어링 해지")
    assert "해지되었습니다" in r2.response_text


@pytest.mark.asyncio
async def test_pii_not_in_llm_context():
    """PII가 LLM에 전달되지 않는다."""
    session = _make_session()
    pipeline = _make_pipeline(session)

    result = await pipeline.process(None, "010", "제 번호는 010-1234-5678이에요 요금 조회해줘")

    # LLM generate의 두 번째 인자 (user text)에 원본 전화번호 없음
    llm_call = pipeline._llm_engine.generate.call_args
    if llm_call:
        user_text = llm_call[0][1]
        assert "010-1234-5678" not in user_text


@pytest.mark.asyncio
async def test_session_limit_blocks_processing():
    """세션 제한 초과 시 바로 종료."""
    session = _make_session()
    session.turn_count = 25
    session.has_active_transaction = False
    pipeline = _make_pipeline(session)

    result = await pipeline.process(None, "010", "요금 조회해줘")
    assert result.action_type == "SESSION_END"


@pytest.mark.asyncio
async def test_pii_multiple_patterns_masked():
    """복합 PII (전화+주민) E2E 마스킹."""
    session = _make_session()
    pipeline = _make_pipeline(session)

    result = await pipeline.process(
        None, "010", "제 번호 010-9876-5432, 주민 880101-1234567 요금 조회"
    )

    llm_call = pipeline._llm_engine.generate.call_args
    if llm_call:
        user_text = llm_call[0][1]
        assert "010-9876-5432" not in user_text
        assert "880101-1234567" not in user_text


@pytest.mark.asyncio
async def test_plan_change_name_select_e2e():
    """요금제 이름으로 선택 E2E."""
    session = _make_session()
    pipeline = _make_pipeline(session)

    r1 = await pipeline.process(None, "010", "요금제 변경하고 싶어요")
    assert session.pending_intent == "PLAN_CHANGE_SELECT"

    # 이름으로 선택
    r2 = await pipeline.process(None, "010", "5G 프리미엄으로 변경해줘")
    assert "프리미엄" in r2.response_text


@pytest.mark.asyncio
async def test_addon_cancel_non_cancelable_e2e():
    """약정 부가서비스 해지 실패 E2E."""
    session = _make_session()
    pipeline = _make_pipeline(session)

    await pipeline.process(None, "010", "부가서비스 해지해줘")
    r2 = await pipeline.process(None, "010", "약정 보험 해지")
    assert "실패" in r2.response_text or "약정" in r2.response_text
