"""callbot.orchestrator.tests.test_conversation_orchestrator — PIF FilterResult 분기 단위 테스트"""
from __future__ import annotations

from typing import Optional

import pytest

from callbot.orchestrator.conversation_orchestrator import ConversationOrchestrator
from callbot.orchestrator.enums import ActionType
from callbot.orchestrator.models import NoResponseAction, SystemControlResult


# ---------------------------------------------------------------------------
# Mock 객체
# ---------------------------------------------------------------------------

class MockSession:
    def __init__(
        self,
        injection_count: int = 0,
        is_authenticated: bool = False,
        turn_count: int = 0,
        last_response: str = "이전 응답입니다",
        tts_speed_factor: float = 1.0,
        end_reason: Optional[str] = None,
        survey_conducted: bool = False,
        no_response_stage: int = 0,
        auth_module_called: bool = False,
        callback_scheduled: bool = False,
        csat_score: Optional[int] = None,
    ):
        self.injection_count = injection_count
        self.is_authenticated = is_authenticated
        self.turn_count = turn_count
        self.last_response = last_response
        self.tts_speed_factor = tts_speed_factor
        self.end_reason = end_reason
        self.survey_conducted = survey_conducted
        self.no_response_stage = no_response_stage
        self.auth_module_called = auth_module_called
        self.callback_scheduled = callback_scheduled
        self.csat_score = csat_score


class MockDTMFResult:
    def __init__(self, input_type: str, digits: str):
        self.input_type = input_type
        self.digits = digits


class MockIntent:
    def __init__(self, intent_type: str):
        self.intent_type = intent_type  # "END_CALL", "SPEED_CONTROL", "REPEAT_REQUEST", "WAIT_REQUEST"


class MockFilterResult:
    def __init__(self, is_safe: bool = True, filtered_text: str = "안녕하세요"):
        self.is_safe = is_safe
        self.original_text = filtered_text


class MockIntentClassifier:
    def __init__(self):
        self.called_with = None

    def classify(self, text, session):
        self.called_with = (text, session)
        return object()  # 더미 ClassificationResult


# ---------------------------------------------------------------------------
# 테스트: PIF 분기 단위 테스트 (Task 2.1)
# ---------------------------------------------------------------------------

class TestPIFBranching:
    def test_pif_unsafe_injection_count_0_returns_requestion(self):
        """is_safe=False, injection_count=0 → SYSTEM_CONTROL(재질문) OrchestratorAction 반환"""
        orchestrator = ConversationOrchestrator()
        session = MockSession(injection_count=0)
        filter_result = MockFilterResult(is_safe=False)

        action = orchestrator.process_turn(session, filter_result)

        assert action.action_type == ActionType.SYSTEM_CONTROL
        assert action.target_component == "orchestrator"
        assert "reask" in action.context.get("action", "")

    def test_pif_unsafe_injection_count_1_returns_requestion(self):
        """is_safe=False, injection_count=1 → SYSTEM_CONTROL(재질문) OrchestratorAction 반환"""
        orchestrator = ConversationOrchestrator()
        session = MockSession(injection_count=1)
        filter_result = MockFilterResult(is_safe=False)

        action = orchestrator.process_turn(session, filter_result)

        assert action.action_type == ActionType.SYSTEM_CONTROL
        assert action.target_component == "orchestrator"
        assert "reask" in action.context.get("action", "")

    def test_pif_unsafe_injection_count_2_returns_escalate(self):
        """is_safe=False, injection_count=2 → ESCALATE OrchestratorAction 반환"""
        orchestrator = ConversationOrchestrator()
        session = MockSession(injection_count=2)
        filter_result = MockFilterResult(is_safe=False)

        action = orchestrator.process_turn(session, filter_result)

        assert action.action_type == ActionType.ESCALATE
        assert action.target_component == "routing_engine"
        assert action.context.get("reason") == "PROMPT_INJECTION"

    def test_pif_unsafe_injection_count_3_returns_escalate(self):
        """is_safe=False, injection_count=3 (>=2) → ESCALATE OrchestratorAction 반환"""
        orchestrator = ConversationOrchestrator()
        session = MockSession(injection_count=3)
        filter_result = MockFilterResult(is_safe=False)

        action = orchestrator.process_turn(session, filter_result)

        assert action.action_type == ActionType.ESCALATE
        assert action.target_component == "routing_engine"

    def test_pif_safe_calls_intent_classifier(self):
        """is_safe=True → 의도 분류기 호출 후 분기 진행"""
        classifier = MockIntentClassifier()
        orchestrator = ConversationOrchestrator(intent_classifier=classifier)
        session = MockSession()
        filter_result = MockFilterResult(is_safe=True, filtered_text="요금 조회해주세요")

        action = orchestrator.process_turn(session, filter_result)

        # 분류기가 호출되었는지 확인
        assert classifier.called_with is not None
        assert classifier.called_with[0] == "요금 조회해주세요"
        assert classifier.called_with[1] is session
        # 안전한 입력 → PROCESS_BUSINESS 반환
        assert action.action_type == ActionType.PROCESS_BUSINESS
        assert action.target_component == "llm_engine"

    def test_pif_safe_no_classifier_returns_process_business(self):
        """is_safe=True, 분류기 없음 → PROCESS_BUSINESS 반환"""
        orchestrator = ConversationOrchestrator()
        session = MockSession()
        filter_result = MockFilterResult(is_safe=True)

        action = orchestrator.process_turn(session, filter_result)

        assert action.action_type == ActionType.PROCESS_BUSINESS
        assert action.target_component == "llm_engine"
        assert action.context["intent"] is None

    def test_pif_safe_with_classifier_returns_intent_in_context(self):
        """is_safe=True, 분류기 있음 → context['intent']에 분류 결과 포함 (C-02)"""
        from unittest.mock import MagicMock
        mock_classifier = MagicMock()
        mock_result = MagicMock()
        mock_classifier.classify.return_value = mock_result

        orchestrator = ConversationOrchestrator(intent_classifier=mock_classifier)
        session = MockSession()
        filter_result = MockFilterResult(is_safe=True)

        action = orchestrator.process_turn(session, filter_result)

        assert action.context["intent"] is mock_result
        mock_classifier.classify.assert_called_once_with(filter_result.original_text, session)


# ---------------------------------------------------------------------------
# 테스트: 시스템 제어 의도 단위 테스트 (Task 3.1)
# ---------------------------------------------------------------------------

class TestSystemControlHandling:
    def test_end_call_conducts_survey_and_ends_session(self):
        """END_CALL → conduct_satisfaction_survey 호출 후 세션 종료, is_handled=True, action_taken contains 'end_session'"""
        orchestrator = ConversationOrchestrator()
        session = MockSession()
        intent = MockIntent("END_CALL")

        result = orchestrator.handle_system_control(session, intent)

        assert isinstance(result, SystemControlResult)
        assert result.is_handled is True
        assert "end_session" in result.action_taken
        assert session.survey_conducted is True

    def test_speed_control_adjusts_tts_speed(self):
        """SPEED_CONTROL → TTS 속도 조절, is_handled=True, action_taken contains 'speed'"""
        orchestrator = ConversationOrchestrator()
        session = MockSession()
        intent = MockIntent("SPEED_CONTROL")

        result = orchestrator.handle_system_control(session, intent)

        assert isinstance(result, SystemControlResult)
        assert result.is_handled is True
        assert "speed" in result.action_taken

    def test_repeat_request_replays_last_response(self):
        """REPEAT_REQUEST → 직전 응답 재생, is_handled=True, action_taken contains 'repeat'"""
        orchestrator = ConversationOrchestrator()
        session = MockSession(last_response="이전 응답입니다")
        intent = MockIntent("REPEAT_REQUEST")

        result = orchestrator.handle_system_control(session, intent)

        assert isinstance(result, SystemControlResult)
        assert result.is_handled is True
        assert "repeat" in result.action_taken

    def test_wait_request_returns_wait_message(self):
        """WAIT_REQUEST → 대기 안내, is_handled=True, action_taken contains 'wait'"""
        orchestrator = ConversationOrchestrator()
        session = MockSession()
        intent = MockIntent("WAIT_REQUEST")

        result = orchestrator.handle_system_control(session, intent)

        assert isinstance(result, SystemControlResult)
        assert result.is_handled is True
        assert "wait" in result.action_taken

    def test_system_control_turn_not_counted(self):
        """handle_system_control() 호출 후 session.turn_count는 증가하지 않아야 한다"""
        orchestrator = ConversationOrchestrator()
        session = MockSession(turn_count=5)
        intent = MockIntent("WAIT_REQUEST")

        orchestrator.handle_system_control(session, intent)

        assert session.turn_count == 5


# ---------------------------------------------------------------------------
# 테스트: 인증 필요 여부 판단 (Task 5.1)
# ---------------------------------------------------------------------------

class TestAuthRequirement:
    def test_billing_inquiry_unauthenticated_requires_auth(self):
        """요금_조회, 미인증 → requires_auth=True, auth_type_hint is not None (BIRTHDATE)"""
        orchestrator = ConversationOrchestrator()
        session = MockSession(is_authenticated=False)
        intent = MockIntent("요금_조회")

        result = orchestrator.determine_auth_requirement(session, intent)

        assert result.requires_auth is True
        assert result.auth_type_hint is not None
        assert result.auth_type_hint == "BIRTHDATE"

    def test_billing_inquiry_authenticated_no_reauth(self):
        """요금_조회, 인증됨 → requires_auth=False, is_already_authenticated=True"""
        orchestrator = ConversationOrchestrator()
        session = MockSession(is_authenticated=True)
        intent = MockIntent("요금_조회")

        result = orchestrator.determine_auth_requirement(session, intent)

        assert result.requires_auth is False
        assert result.is_already_authenticated is True

    def test_general_inquiry_no_auth_required(self):
        """일반_문의, 미인증 → requires_auth=False"""
        orchestrator = ConversationOrchestrator()
        session = MockSession(is_authenticated=False)
        intent = MockIntent("일반_문의")

        result = orchestrator.determine_auth_requirement(session, intent)

        assert result.requires_auth is False

    def test_end_call_no_auth_required(self):
        """END_CALL, 미인증 → requires_auth=False"""
        orchestrator = ConversationOrchestrator()
        session = MockSession(is_authenticated=False)
        intent = MockIntent("END_CALL")

        result = orchestrator.determine_auth_requirement(session, intent)

        assert result.requires_auth is False

    def test_all_auth_required_intents_unauthenticated(self):
        """인증 필요 의도 전체, 미인증 → 모두 requires_auth=True"""
        orchestrator = ConversationOrchestrator()
        auth_required_intents = ["요금_조회", "납부_확인", "요금제_변경", "요금제_조회"]

        for intent_type in auth_required_intents:
            session = MockSession(is_authenticated=False)
            intent = MockIntent(intent_type)

            result = orchestrator.determine_auth_requirement(session, intent)

            assert result.requires_auth is True, f"{intent_type} should require auth"


# ---------------------------------------------------------------------------
# 테스트: 만족도 조사 (Task 6.1)
# ---------------------------------------------------------------------------

class TestSatisfactionSurvey:
    def test_valid_score_3_returns_score_3(self):
        """점수 3 입력 → score=3, is_skipped=False, input_method='voice'"""
        orchestrator = ConversationOrchestrator()
        session = MockSession()

        def input_provider():
            return {"type": "score", "value": 3, "method": "voice"}

        result = orchestrator.conduct_satisfaction_survey(session, input_provider=input_provider)

        assert result.score == 3
        assert result.is_skipped is False
        assert result.input_method == "voice"

    def test_invalid_score_then_valid_score_returns_valid(self):
        """점수 6 입력 후 점수 2 입력 → 재요청 후 score=2, is_skipped=False"""
        orchestrator = ConversationOrchestrator()
        session = MockSession()
        calls = iter([
            {"type": "score", "value": 6, "method": "dtmf"},
            {"type": "score", "value": 2, "method": "dtmf"},
        ])

        def input_provider():
            return next(calls)

        result = orchestrator.conduct_satisfaction_survey(session, input_provider=input_provider)

        assert result.score == 2
        assert result.is_skipped is False

    def test_timeout_returns_skipped(self):
        """5초 무응답 → is_skipped=True, score=None"""
        orchestrator = ConversationOrchestrator()
        session = MockSession()

        def input_provider():
            return {"type": "skip", "reason": "timeout"}

        result = orchestrator.conduct_satisfaction_survey(session, input_provider=input_provider)

        assert result.is_skipped is True
        assert result.score is None

    def test_refused_returns_skipped(self):
        """거부 발화 → is_skipped=True, score=None"""
        orchestrator = ConversationOrchestrator()
        session = MockSession()

        def input_provider():
            return {"type": "skip", "reason": "refused"}

        result = orchestrator.conduct_satisfaction_survey(session, input_provider=input_provider)

        assert result.is_skipped is True
        assert result.score is None


# ---------------------------------------------------------------------------
# 테스트: 만족도 조사 수행 조건 (Task 6.2)
# ---------------------------------------------------------------------------

class TestSurveyCondition:
    def test_normal_end_reason_conducts_survey(self):
        """NORMAL → should_conduct_survey=True"""
        orchestrator = ConversationOrchestrator()
        assert orchestrator.should_conduct_survey("NORMAL") is True

    def test_turn_limit_end_reason_conducts_survey(self):
        """TURN_LIMIT → should_conduct_survey=True"""
        orchestrator = ConversationOrchestrator()
        assert orchestrator.should_conduct_survey("TURN_LIMIT") is True

    def test_time_limit_end_reason_conducts_survey(self):
        """TIME_LIMIT → should_conduct_survey=True"""
        orchestrator = ConversationOrchestrator()
        assert orchestrator.should_conduct_survey("TIME_LIMIT") is True

    def test_timeout_end_reason_skips_survey(self):
        """TIMEOUT → should_conduct_survey=False"""
        orchestrator = ConversationOrchestrator()
        assert orchestrator.should_conduct_survey("TIMEOUT") is False

    def test_disconnected_end_reason_skips_survey(self):
        """DISCONNECTED → should_conduct_survey=False"""
        orchestrator = ConversationOrchestrator()
        assert orchestrator.should_conduct_survey("DISCONNECTED") is False


# ---------------------------------------------------------------------------
# Mock 객체: 세션 제한 테스트용
# ---------------------------------------------------------------------------

class MockSessionWithLimits:
    def __init__(
        self,
        turn_count: int = 0,
        elapsed_minutes: float = 0.0,
        has_active_transaction: bool = False,
        extra_turns_used: int = 0,
    ):
        self.turn_count = turn_count
        self.elapsed_minutes = elapsed_minutes
        self.has_active_transaction = has_active_transaction
        self.extra_turns_used = extra_turns_used


# ---------------------------------------------------------------------------
# 테스트: 세션 제한 관리 (Task 8.1)
# ---------------------------------------------------------------------------

class TestSessionLimits:
    def test_18th_turn_returns_warn(self):
        """18번째 턴 → action=warn"""
        orchestrator = ConversationOrchestrator()
        session = MockSessionWithLimits(turn_count=18, elapsed_minutes=5.0)

        result = orchestrator.check_session_limits(session)

        assert result.action == "warn"

    def test_20th_turn_no_transaction_returns_end_session(self):
        """20번째 턴 + 트랜잭션 없음 → action=end_session"""
        orchestrator = ConversationOrchestrator()
        session = MockSessionWithLimits(turn_count=20, elapsed_minutes=5.0, has_active_transaction=False)

        result = orchestrator.check_session_limits(session)

        assert result.action == "end_session"

    def test_20th_turn_with_transaction_returns_allow_extra_turns(self):
        """20번째 턴 + 트랜잭션 진행 중 → action="allow_extra_turns", extra_turns_allowed=2"""
        orchestrator = ConversationOrchestrator()
        session = MockSessionWithLimits(turn_count=20, elapsed_minutes=5.0, has_active_transaction=True)

        result = orchestrator.check_session_limits(session)

        assert result.action == "allow_extra_turns"
        assert result.extra_turns_allowed == 2

    def test_13_minutes_returns_warn(self):
        """13분 경과 → action=warn"""
        orchestrator = ConversationOrchestrator()
        session = MockSessionWithLimits(turn_count=5, elapsed_minutes=13.0)

        result = orchestrator.check_session_limits(session)

        assert result.action == "warn"

    def test_15_minutes_no_transaction_returns_end_session(self):
        """15분 경과 + 트랜잭션 없음 → action=end_session"""
        orchestrator = ConversationOrchestrator()
        session = MockSessionWithLimits(turn_count=5, elapsed_minutes=15.0, has_active_transaction=False)

        result = orchestrator.check_session_limits(session)

        assert result.action == "end_session"

    def test_normal_turn_returns_continue(self):
        """정상 범위 턴 → action=continue"""
        orchestrator = ConversationOrchestrator()
        session = MockSessionWithLimits(turn_count=5, elapsed_minutes=5.0)

        result = orchestrator.check_session_limits(session)

        assert result.action == "continue"

    def test_extra_turns_exceeded_returns_escalate(self):
        """추가 2턴 초과 + 트랜잭션 진행 중 → action=escalate"""
        orchestrator = ConversationOrchestrator()
        session = MockSessionWithLimits(
            turn_count=22, elapsed_minutes=5.0, has_active_transaction=True, extra_turns_used=2
        )

        result = orchestrator.check_session_limits(session)

        assert result.action == "escalate"


# ---------------------------------------------------------------------------
# 테스트: 무응답 처리 (Task 9.1)
# ---------------------------------------------------------------------------

class TestNoResponseHandling:
    def test_first_30s_no_response_returns_prompt(self):
        """no_response_stage=0 (첫 30초) → NoResponseAction(timeout_stage=1, action="prompt")"""
        orchestrator = ConversationOrchestrator()
        session = MockSession(no_response_stage=0)

        result = orchestrator.handle_no_response(session)

        assert isinstance(result, NoResponseAction)
        assert result.timeout_stage == 1
        assert result.action == "prompt"
        assert session.no_response_stage == 1

    def test_second_30s_no_response_returns_end_session(self):
        """no_response_stage=1 (추가 30초) → NoResponseAction(timeout_stage=2, action="end_session")"""
        orchestrator = ConversationOrchestrator()
        session = MockSession(no_response_stage=1)

        result = orchestrator.handle_no_response(session)

        assert isinstance(result, NoResponseAction)
        assert result.timeout_stage == 2
        assert result.action == "end_session"
        assert session.end_reason == "TIMEOUT"

    def test_timeout_end_does_not_conduct_survey(self):
        """TIMEOUT 종료 → 만족도 조사 미수행 (survey_conducted=False 유지)"""
        orchestrator = ConversationOrchestrator()
        session = MockSession(no_response_stage=1)

        result = orchestrator.handle_no_response(session)

        assert result.action == "end_session"
        assert orchestrator.should_conduct_survey("TIMEOUT") is False
        assert session.survey_conducted is False


# ---------------------------------------------------------------------------
# 테스트: DTMF 입력 처리 (Task 10.1)
# ---------------------------------------------------------------------------

class TestDTMFInputProcessing:
    def test_dtmf_birth_date_calls_auth_module(self):
        """input_type="birth_date" → AUTH_REQUIRED 반환, session.auth_module_called=True"""
        orchestrator = ConversationOrchestrator()
        session = MockSession()
        dtmf_result = MockDTMFResult(input_type="birth_date", digits="19901231")

        action = orchestrator.process_dtmf_input(session, dtmf_result)

        assert action.action_type in (ActionType.AUTH_REQUIRED, ActionType.PROCESS_BUSINESS)
        assert session.auth_module_called is True

    def test_dtmf_satisfaction_valid_digit_stores_score(self):
        """input_type="satisfaction", digits="3" → SURVEY 반환, session.csat_score=3"""
        orchestrator = ConversationOrchestrator()
        session = MockSession()
        dtmf_result = MockDTMFResult(input_type="satisfaction", digits="3")

        action = orchestrator.process_dtmf_input(session, dtmf_result)

        assert action.action_type == ActionType.SURVEY
        assert session.csat_score == 3

    def test_dtmf_satisfaction_invalid_digit_returns_error(self):
        """input_type="satisfaction", digits="6" → SYSTEM_CONTROL 반환, session.csat_score=None"""
        orchestrator = ConversationOrchestrator()
        session = MockSession()
        dtmf_result = MockDTMFResult(input_type="satisfaction", digits="6")

        action = orchestrator.process_dtmf_input(session, dtmf_result)

        assert action.action_type == ActionType.SYSTEM_CONTROL
        assert session.csat_score is None

    def test_dtmf_callback_time_schedules_callback(self):
        """input_type="callback_time", digits="2" → PROCESS_BUSINESS 반환, session.callback_scheduled=True"""
        orchestrator = ConversationOrchestrator()
        session = MockSession()
        dtmf_result = MockDTMFResult(input_type="callback_time", digits="2")

        action = orchestrator.process_dtmf_input(session, dtmf_result)

        assert action.action_type == ActionType.PROCESS_BUSINESS
        assert session.callback_scheduled is True


# ---------------------------------------------------------------------------
# Mock 객체: 상담사 연결 폴백 테스트용
# ---------------------------------------------------------------------------

class MockSessionWithId:
    def __init__(self, session_id: str = "sess-001", turn_count: int = 5):
        self.session_id = session_id
        self.turn_count = turn_count
        self.audit_log: list = []


# ---------------------------------------------------------------------------
# 테스트: 상담사 연결 폴백 (Task 12.1)
# ---------------------------------------------------------------------------

class TestEscalationFallback:
    def test_prompt_injection_reason_returns_escalation_action(self):
        """reason="PROMPT_INJECTION" → EscalationAction with reason, summary, routing_result"""
        from callbot.orchestrator.models import EscalationAction
        orchestrator = ConversationOrchestrator()
        session = MockSessionWithId(session_id="sess-001", turn_count=5)

        result = orchestrator.trigger_escalation(session, reason="PROMPT_INJECTION", context={})

        assert isinstance(result, EscalationAction)
        assert result.reason == "PROMPT_INJECTION"
        assert result.summary is not None
        assert result.routing_result is not None

    def test_turn_limit_reason_returns_escalation_action(self):
        """reason="TURN_LIMIT" → EscalationAction with reason="TURN_LIMIT" """
        from callbot.orchestrator.models import EscalationAction
        orchestrator = ConversationOrchestrator()
        session = MockSessionWithId(session_id="sess-002", turn_count=20)

        result = orchestrator.trigger_escalation(session, reason="TURN_LIMIT", context={})

        assert isinstance(result, EscalationAction)
        assert result.reason == "TURN_LIMIT"


# ---------------------------------------------------------------------------
# 테스트: PIF 장애 감사 로그 (Task 12.2)
# ---------------------------------------------------------------------------

class TestPIFBypassAuditLog:
    def test_pif_bypass_logs_session_id_and_reason(self):
        """log_pif_bypass() → session.audit_log에 session_id, bypass_time, bypass_reason 포함"""
        orchestrator = ConversationOrchestrator()
        session = MockSessionWithId(session_id="sess-003")

        orchestrator.log_pif_bypass(session, bypass_reason="PIF_UNAVAILABLE")

        assert len(session.audit_log) == 1
        entry = session.audit_log[0]
        assert entry["session_id"] == "sess-003"
        assert "bypass_time" in entry
        assert entry["bypass_reason"] == "PIF_UNAVAILABLE"
