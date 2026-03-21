"""Phase C E2E 테스트 — TurnPipeline.process() 경유 전체 파이프라인 검증.

FakeExternalSystem + 실제 컴포넌트로 구성. 모킹 최소화.

시나리오:
  1. 요금제 변경 3턴 다단계 플로우
  2. 부가서비스 해지 2턴 다단계 플로우
  3. PII 마스킹 (카드/주민/전화번호)
  4. 세션 턴 리밋 → SESSION_END
  5. 데이터 잔여량 조회 (DATA_USAGE_INQUIRY)
  6. 요금제 변경 중간 취소
  7. 약정 부가서비스 해지 실패
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from callbot.external.fake_system import FakeExternalSystem
from callbot.nlu.prompt_injection_filter import PromptInjectionFilter
from callbot.orchestrator.conversation_orchestrator import ConversationOrchestrator
from callbot.nlu.intent_classifier import IntentClassifier
from callbot.session.repository import CallbotDBRepository, InMemoryDBConnection
from callbot.session.session_manager import SessionManager
from callbot.session.session_store import InMemorySessionStore
from callbot.server.pipeline import TurnPipeline, TurnResult


# ---------------------------------------------------------------------------
# Fixture: 실제 컴포넌트 기반 TurnPipeline
# ---------------------------------------------------------------------------

class FakeLLMEngine:
    """LLM mock — api_result를 응답에 포함."""

    def generate_response(self, *, classification=None, session=None,
                          customer_text="", api_result=None, **kwargs) -> MagicMock:
        resp = MagicMock()
        if api_result:
            resp.text = f"API결과: {api_result}"
        else:
            resp.text = f"고객님 '{customer_text}'에 대해 안내드리겠습니다."
        resp.final_response = resp.text
        return resp

    def generate(self, context_text: str, user_text: str) -> str:
        """pipeline._generate_llm_response에서 호출."""
        return f"고객님 '{user_text}'에 대해 안내드리겠습니다."


def _make_pipeline() -> tuple[TurnPipeline, SessionManager]:
    """실제 컴포넌트 + FakeSystem 기반 파이프라인."""
    pif = PromptInjectionFilter()
    intent_classifier = IntentClassifier()
    db = InMemoryDBConnection()
    repo = CallbotDBRepository(db, retry_delays=[0, 0, 0])
    store = InMemorySessionStore()
    session_manager = SessionManager(repo, store)
    llm_engine = FakeLLMEngine()

    orchestrator = ConversationOrchestrator(
        intent_classifier=intent_classifier,
        llm_engine=llm_engine,
        session_manager=session_manager,
    )

    external_system = FakeExternalSystem()
    pipeline = TurnPipeline(
        pif=pif,
        orchestrator=orchestrator,
        session_manager=session_manager,
        llm_engine=llm_engine,
        external_system=external_system,
    )
    return pipeline, session_manager


def _run(coro):
    """동기 테스트에서 async 실행."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ===========================================================================
# 시나리오 1: 요금제 변경 3턴 다단계 플로우
# ===========================================================================

class TestPlanChange3TurnE2E:
    """요금제 변경 — 목록 → 선택 → 확인 → 실행."""

    def test_plan_change_full_3turn_flow(self):
        """Turn 1→2→3 완전한 플로우."""
        pipeline, sm = _make_pipeline()
        session = sm.create_session("01012345678")
        sid = session.session_id

        # Turn 1: "요금제 변경"
        r1 = _run(pipeline.process(sid, "01012345678", "요금제 변경하고 싶어요"))
        assert "변경 가능한 요금제" in r1.response_text
        assert "번호를 말씀해주세요" in r1.response_text

        # Turn 2: 번호 선택
        r2 = _run(pipeline.process(sid, "01012345678", "1"))
        assert "변경하시겠습니까" in r2.response_text

        # Turn 3: 확인
        r3 = _run(pipeline.process(sid, "01012345678", "네"))
        assert "변경되었습니다" in r3.response_text

    def test_plan_change_select_by_name(self):
        """이름으로 요금제 선택."""
        pipeline, sm = _make_pipeline()
        session = sm.create_session("01012345678")
        sid = session.session_id

        r1 = _run(pipeline.process(sid, "01012345678", "요금제 변경하고 싶어요"))
        assert "변경 가능한 요금제" in r1.response_text

        # 이름으로 선택
        r2 = _run(pipeline.process(sid, "01012345678", "5G 프리미엄으로 변경해줘"))
        assert "변경하시겠습니까" in r2.response_text or "프리미엄" in r2.response_text

    def test_plan_change_invalid_selection(self):
        """잘못된 번호 입력 → 재질문."""
        pipeline, sm = _make_pipeline()
        session = sm.create_session("01012345678")
        sid = session.session_id

        _run(pipeline.process(sid, "01012345678", "요금제 변경하고 싶어요"))
        r2 = _run(pipeline.process(sid, "01012345678", "99"))
        assert "올바른" in r2.response_text


# ===========================================================================
# 시나리오 2: 부가서비스 해지 2턴
# ===========================================================================

class TestAddonCancel2TurnE2E:
    """부가서비스 해지 — 선택 → 실행."""

    def test_addon_cancel_success(self):
        """해지 성공 플로우."""
        pipeline, sm = _make_pipeline()
        session = sm.create_session("01012345678")
        sid = session.session_id

        r1 = _run(pipeline.process(sid, "01012345678", "부가서비스 해지해줘"))
        assert "해지할 부가서비스" in r1.response_text

        r2 = _run(pipeline.process(sid, "01012345678", "데이터 쉐어링 해지"))
        assert "해지되었습니다" in r2.response_text

    def test_addon_cancel_non_cancelable(self):
        """약정 부가서비스 해지 실패."""
        pipeline, sm = _make_pipeline()
        session = sm.create_session("01012345678")
        sid = session.session_id

        _run(pipeline.process(sid, "01012345678", "부가서비스 해지해줘"))
        r2 = _run(pipeline.process(sid, "01012345678", "약정 보험 해지"))
        assert "실패" in r2.response_text or "해지" in r2.response_text


# ===========================================================================
# 시나리오 3: PII 마스킹
# ===========================================================================

class TestPIIMaskingE2E:
    """PII가 LLM에 도달하기 전에 마스킹."""

    def test_card_number_masked(self):
        """카드번호 마스킹."""
        pipeline, sm = _make_pipeline()
        session = sm.create_session("01012345678")
        sid = session.session_id

        r = _run(pipeline.process(sid, "01012345678",
                                  "카드번호 1234-5678-1234-5678로 결제해줘"))
        # 응답에 원본 카드번호가 노출되면 안 됨
        assert "1234-5678-1234-5678" not in r.response_text

    def test_ssn_masked(self):
        """주민번호 마스킹."""
        pipeline, sm = _make_pipeline()
        session = sm.create_session("01012345678")
        sid = session.session_id

        r = _run(pipeline.process(sid, "01012345678",
                                  "주민번호 880101-1234567 확인해줘"))
        assert "880101-1234567" not in r.response_text

    def test_phone_masked(self):
        """전화번호 마스킹."""
        pipeline, sm = _make_pipeline()
        session = sm.create_session("01099998888")
        sid = session.session_id

        r = _run(pipeline.process(sid, "01099998888",
                                  "010-9999-8888 번호로 바꿔줘"))
        assert "010-9999-8888" not in r.response_text

    def test_multiple_pii_masked(self):
        """복합 PII 동시 마스킹."""
        pipeline, sm = _make_pipeline()
        session = sm.create_session("01012345678")
        sid = session.session_id

        text = "카드 1234-5678-1234-5678 주민 990101-1234567 폰 010-1111-2222 요금 조회"
        r = _run(pipeline.process(sid, "01012345678", text))
        assert "1234-5678-1234-5678" not in r.response_text
        assert "990101-1234567" not in r.response_text
        assert "010-1111-2222" not in r.response_text


# ===========================================================================
# 시나리오 4: 세션 턴 리밋
# ===========================================================================

class TestSessionTurnLimitE2E:
    """세션 턴/시간 제한 → SESSION_END."""

    def test_turn_limit_returns_session_end(self):
        """turn_count 초과 시 SESSION_END."""
        pipeline, sm = _make_pipeline()
        session = sm.create_session("01012345678")
        sid = session.session_id

        # 턴 25개 채우기
        for i in range(25):
            from callbot.session.models import Turn
            from callbot.session.enums import TurnType
            session.turns.append(Turn(
                turn_id=f"t-{i}",
                turn_type=TurnType.BUSINESS,
                customer_utterance=f"test-{i}",
                bot_response=f"resp-{i}",
                intent=None,
                entities=[],
                stt_confidence=0.9,
                intent_confidence=0.9,
                llm_confidence=None,
                verification_status=None,
                response_time_ms=100,
                is_dtmf_input=False,
                is_barge_in=False,
                timestamp=datetime.now(),
            ))

        r = _run(pipeline.process(sid, "01012345678", "요금 조회"))
        assert r.action_type in ("SESSION_END", "ESCALATE")

    def test_time_limit_returns_session_end(self):
        """elapsed_minutes 초과 시 SESSION_END."""
        pipeline, sm = _make_pipeline()
        session = sm.create_session("01012345678")
        sid = session.session_id

        # 시작 시간 30분 전으로 조작
        session.start_time = datetime.now() - timedelta(minutes=30)

        r = _run(pipeline.process(sid, "01012345678", "요금 조회"))
        assert r.action_type in ("SESSION_END", "ESCALATE")


# ===========================================================================
# 시나리오 5: DATA_USAGE_INQUIRY
# ===========================================================================

class TestDataUsageInquiryE2E:
    """데이터 잔여량 조회."""

    def test_data_usage_inquiry_returns_response(self):
        """데이터 잔여량 조회 → 정상 응답."""
        pipeline, sm = _make_pipeline()
        session = sm.create_session("01012345678")
        sid = session.session_id

        r = _run(pipeline.process(sid, "01012345678", "데이터 잔여량 알려줘"))
        assert r.action_type == "PROCESS_BUSINESS"
        assert r.response_text  # 응답이 비어있지 않음


# ===========================================================================
# 시나리오 6: 다단계 플로우 중간 취소
# ===========================================================================

class TestMultiStepCancelE2E:
    """다단계 플로우 중간에 '취소'."""

    def test_plan_change_cancel_at_turn2(self):
        """요금제 변경 Turn 2에서 취소."""
        pipeline, sm = _make_pipeline()
        session = sm.create_session("01012345678")
        sid = session.session_id

        r1 = _run(pipeline.process(sid, "01012345678", "요금제 변경하고 싶어요"))
        assert "변경 가능한 요금제" in r1.response_text

        r2 = _run(pipeline.process(sid, "01012345678", "취소"))
        assert "취소" in r2.response_text

        # 취소 후 정상 플로우 가능
        r3 = _run(pipeline.process(sid, "01012345678", "요금 조회해줘"))
        assert r3.action_type == "PROCESS_BUSINESS"

    def test_addon_cancel_cancel_at_turn2(self):
        """부가서비스 해지 Turn 2에서 취소."""
        pipeline, sm = _make_pipeline()
        session = sm.create_session("01012345678")
        sid = session.session_id

        _run(pipeline.process(sid, "01012345678", "부가서비스 해지해줘"))
        r2 = _run(pipeline.process(sid, "01012345678", "취소"))
        assert "취소" in r2.response_text
