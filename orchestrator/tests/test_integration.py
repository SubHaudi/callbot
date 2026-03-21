"""callbot.orchestrator.tests.test_integration — 모듈 통합 테스트 (Task 17.1)"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Task 17.1: 공개 API export 테스트 — __init__.py에서 직접 import 가능해야 함
# ---------------------------------------------------------------------------

class TestPublicAPIExports:
    def test_conversation_orchestrator_importable(self):
        """ConversationOrchestrator를 패키지 루트에서 import 가능"""
        from callbot.orchestrator import ConversationOrchestrator
        assert ConversationOrchestrator is not None

    def test_health_checker_importable(self):
        """HealthChecker를 패키지 루트에서 import 가능"""
        from callbot.orchestrator import HealthChecker
        assert HealthChecker is not None

    def test_models_importable(self):
        """핵심 모델들을 패키지 루트에서 import 가능"""
        from callbot.orchestrator import (
            OrchestratorAction,
            SurveyResult,
            SystemControlResult,
            EscalationAction,
            SessionLimitAction,
            NoResponseAction,
            AuthRequirement,
            HealthCheckStatus,
            TrafficObservationMetrics,
        )
        for cls in [
            OrchestratorAction, SurveyResult, SystemControlResult,
            EscalationAction, SessionLimitAction, NoResponseAction,
            AuthRequirement, HealthCheckStatus, TrafficObservationMetrics,
        ]:
            assert cls is not None

    def test_enums_importable(self):
        """열거형들을 패키지 루트에서 import 가능"""
        from callbot.orchestrator import ActionType, SwitchDecision
        assert ActionType is not None
        assert SwitchDecision is not None

    def test_orchestrator_config_importable(self):
        """OrchestratorConfig를 패키지 루트에서 import 가능"""
        from callbot.orchestrator import OrchestratorConfig
        assert OrchestratorConfig is not None


# ---------------------------------------------------------------------------
# Task 17.1: 기본 파이프라인 통합 테스트
# ---------------------------------------------------------------------------

class TestBasicPipelineIntegration:
    def test_pif_safe_to_process_business(self):
        """PIF 안전 입력 → PROCESS_BUSINESS 액션 반환"""
        from callbot.orchestrator import ConversationOrchestrator, ActionType

        class MockSession:
            injection_count = 0
            turn_count = 0
            elapsed_minutes = 0.0
            has_active_transaction = False

        class MockFilterResult:
            is_safe = True
            original_text = "요금 조회해주세요"

        orch = ConversationOrchestrator()
        action = orch.process_turn(MockSession(), MockFilterResult())

        assert action.action_type == ActionType.PROCESS_BUSINESS

    def test_end_call_to_survey_to_session_end(self):
        """END_CALL → 만족도 조사 수행 → 세션 종료 플래그"""
        from callbot.orchestrator import ConversationOrchestrator

        class MockSession:
            survey_conducted = False
            end_reason = None
            turn_count = 5

        class MockIntent:
            intent_type = "END_CALL"

        orch = ConversationOrchestrator()
        result = orch.handle_system_control(MockSession(), MockIntent())

        assert result.is_handled is True
        assert "end_session" in result.action_taken

    def test_prompt_injection_escalation(self):
        """PROMPT_INJECTION (injection_count=2) → ESCALATE 액션"""
        from callbot.orchestrator import ConversationOrchestrator, ActionType

        class MockSession:
            injection_count = 2
            turn_count = 0
            elapsed_minutes = 0.0
            has_active_transaction = False

        class MockFilterResult:
            is_safe = False
            original_text = ""

        orch = ConversationOrchestrator()
        action = orch.process_turn(MockSession(), MockFilterResult())

        assert action.action_type == ActionType.ESCALATE

    def test_no_response_timeout_flow(self):
        """30초 무응답 → prompt, 추가 30초 → end_session (TIMEOUT)"""
        from callbot.orchestrator import ConversationOrchestrator

        class MockSession:
            no_response_stage = 0
            end_reason = None
            survey_conducted = False

        orch = ConversationOrchestrator()
        session = MockSession()

        # 첫 번째 무응답
        result1 = orch.handle_no_response(session)
        assert result1.action == "prompt"

        # 두 번째 무응답
        result2 = orch.handle_no_response(session)
        assert result2.action == "end_session"
        assert session.end_reason == "TIMEOUT"
        # TIMEOUT → 만족도 조사 미수행
        assert orch.should_conduct_survey("TIMEOUT") is False


# ---------------------------------------------------------------------------
# Task 17.1: OrchestratorConfig 기본값 테스트
# ---------------------------------------------------------------------------

class TestOrchestratorConfig:
    def test_default_config_values(self):
        """OrchestratorConfig 기본값 확인"""
        from callbot.orchestrator import OrchestratorConfig

        config = OrchestratorConfig()

        assert config.no_response_timeout_sec == 30
        assert config.max_turns == 20
        assert config.max_minutes == 15
        assert config.health_check_interval_sec == 30

    def test_custom_config_values(self):
        """OrchestratorConfig 커스텀 값 설정"""
        from callbot.orchestrator import OrchestratorConfig

        config = OrchestratorConfig(max_turns=10, max_minutes=8)

        assert config.max_turns == 10
        assert config.max_minutes == 8
