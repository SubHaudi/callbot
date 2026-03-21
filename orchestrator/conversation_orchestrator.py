"""callbot.orchestrator.conversation_orchestrator — 대화 흐름 조율 중앙 컴포넌트"""
from __future__ import annotations

from typing import Any, Optional

from callbot.orchestrator.enums import ActionType
from callbot.orchestrator.models import AuthRequirement, EscalationAction, NoResponseAction, OrchestratorAction, SessionLimitAction, SurveyResult, SystemControlResult


class ConversationOrchestrator:
    """전체 대화 흐름을 조율하는 중앙 컴포넌트.

    PIF FilterResult 수신 → 인젝션 분기 또는 정상 파이프라인 진행.
    """

    _AUTH_REQUIRED_INTENTS = frozenset(["요금_조회", "납부_확인", "요금제_변경", "요금제_조회"])

    def __init__(
        self,
        intent_classifier: Optional[Any] = None,
        llm_engine: Optional[Any] = None,
        session_manager: Optional[Any] = None,
    ) -> None:
        self._intent_classifier = intent_classifier
        self._llm_engine = llm_engine
        self._session_manager = session_manager

    def process_turn(self, session: Any, filter_result: Any) -> OrchestratorAction:
        """PIF FilterResult 기반 분기.

        - 세션 제한(턴/시간) 초과 시 → 즉시 ESCALATE 또는 END_SESSION
        - is_safe=False AND injection_count < 2  → SYSTEM_CONTROL(재질문)
        - is_safe=False AND injection_count >= 2 → ESCALATE
        - is_safe=True                           → 의도 분류기 호출 후 분기
        """
        # 세션 제한 확인 (M-34)
        limit_action = self.check_session_limits(session)
        if limit_action.action == "end_session":
            return OrchestratorAction(
                action_type=ActionType.SESSION_END,
                target_component="orchestrator",
                context={"reason": "SESSION_LIMIT"},
            )
        if limit_action.action == "escalate":
            return OrchestratorAction(
                action_type=ActionType.ESCALATE,
                target_component="routing_engine",
                context={"reason": "SESSION_LIMIT_EXCEEDED"},
            )

        if not filter_result.is_safe:
            return self._handle_injection(session)

        # 안전한 입력 → 의도 분류기 호출
        classification_result = None
        if self._intent_classifier is not None:
            classification_result = self._intent_classifier.classify(
                filter_result.original_text, session
            )

        return OrchestratorAction(
            action_type=ActionType.PROCESS_BUSINESS,
            target_component="llm_engine",
            context={"intent": classification_result},
        )

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _handle_injection(self, session: Any) -> OrchestratorAction:
        """프롬프트 인젝션 탐지 처리."""
        injection_count = getattr(session, "injection_count", None)
        if injection_count is None:
            injection_count = getattr(session, "injection_detection_count", 0)

        if injection_count < 2:
            return OrchestratorAction(
                action_type=ActionType.SYSTEM_CONTROL,
                target_component="orchestrator",
                context={
                    "action": "reask",
                    "message": "다시 한번 말씀해주시겠어요?",
                },
            )

        return OrchestratorAction(
            action_type=ActionType.ESCALATE,
            target_component="routing_engine",
            context={"reason": "PROMPT_INJECTION"},
        )

    def handle_system_control(self, session: Any, intent: Any) -> SystemControlResult:
        """시스템 제어 의도 직접 처리 (LLM_엔진 우회)
        - END_CALL: conduct_satisfaction_survey() 호출 후 세션 종료
        - SPEED_CONTROL: TTS 속도 조절
        - REPEAT_REQUEST: 직전 응답 재생
        - WAIT_REQUEST: 대기 안내
        시스템 제어 턴은 세션 턴 카운트에 포함하지 않는다.
        """
        intent_type = intent.intent_type

        if intent_type == "END_CALL":
            self.conduct_satisfaction_survey(session)
            session.end_reason = "NORMAL"
            return SystemControlResult(
                intent=intent,
                is_handled=True,
                action_taken="end_session",
            )

        if intent_type == "SPEED_CONTROL":
            session.tts_speed_factor = 1.5
            return SystemControlResult(
                intent=intent,
                is_handled=True,
                action_taken="speed_adjusted",
            )

        if intent_type == "REPEAT_REQUEST":
            return SystemControlResult(
                intent=intent,
                is_handled=True,
                action_taken=f"repeat:{session.last_response}",
            )

        if intent_type == "WAIT_REQUEST":
            return SystemControlResult(
                intent=intent,
                is_handled=True,
                action_taken="wait:잠시 기다리겠습니다",
            )

        # 알 수 없는 시스템 제어 의도 — 처리 불가
        return SystemControlResult(
            intent=intent,
            is_handled=False,
            action_taken="unknown",
        )

    _SURVEY_END_REASONS = frozenset(["NORMAL", "TURN_LIMIT", "TIME_LIMIT"])

    def should_conduct_survey(self, end_reason: str) -> bool:
        """만족도 조사 수행 여부 판단.

        - NORMAL, TURN_LIMIT, TIME_LIMIT → True
        - TIMEOUT, DISCONNECTED → False
        """
        return end_reason in self._SURVEY_END_REASONS

    def conduct_satisfaction_survey(self, session: Any, input_provider=None) -> SurveyResult:
        """만족도 조사 수행.

        input_provider: 사용자 입력을 시뮬레이션하는 callable.
          - {"type": "score", "value": int, "method": str} — 점수 입력
          - {"type": "skip", "reason": str} — 거부/무응답

        input_provider가 None이면 하위 호환 스텁 동작 (is_skipped=True).
        """
        session.survey_conducted = True

        if input_provider is None:
            return SurveyResult(score=None, input_method=None, is_skipped=True)

        # 첫 번째 시도
        response = input_provider()

        if response["type"] == "skip":
            return SurveyResult(score=None, input_method=None, is_skipped=True)

        score = response["value"]
        method = response["method"]

        if 1 <= score <= 5:
            return SurveyResult(score=score, input_method=method, is_skipped=False)

        # 범위 외 응답 — 1회 재요청
        response2 = input_provider()

        if response2["type"] == "skip":
            return SurveyResult(score=None, input_method=None, is_skipped=True)

        score2 = response2["value"]
        method2 = response2["method"]

        if 1 <= score2 <= 5:
            return SurveyResult(score=score2, input_method=method2, is_skipped=False)

        # 재시도 후에도 유효하지 않으면 건너뜀
        return SurveyResult(score=None, input_method=None, is_skipped=True)

    def check_session_limits(self, session: Any) -> SessionLimitAction:
        """턴/시간 제한 확인.

        - 22턴 이상 AND has_active_transaction=True AND extra_turns_used >= 2 → escalate
        - 20턴 또는 15분 AND has_active_transaction=True → allow_extra_turns
        - 20턴 또는 15분 AND has_active_transaction=False → end_session
        - 18턴 또는 13분 → warn
        - 그 외 → continue
        """
        turn_count = session.turn_count
        elapsed_minutes = session.elapsed_minutes
        has_active_transaction = session.has_active_transaction
        extra_turns_used = getattr(session, "extra_turns_used", 0)

        if turn_count >= 20 or elapsed_minutes >= 15:
            if has_active_transaction and extra_turns_used >= 2:
                return SessionLimitAction(limit_status=None, action="escalate")
            if has_active_transaction:
                return SessionLimitAction(limit_status=None, action="allow_extra_turns", extra_turns_allowed=2)
            return SessionLimitAction(limit_status=None, action="end_session")

        if turn_count >= 18 or elapsed_minutes >= 13:
            return SessionLimitAction(limit_status=None, action="warn")

        return SessionLimitAction(limit_status=None, action="continue")

    def handle_no_response(self, session: Any) -> NoResponseAction:
        """무응답 처리.
        - no_response_stage=0 (첫 30초) → prompt, stage=1로 업데이트
        - no_response_stage=1 (추가 30초) → end_session (TIMEOUT), 만족도 조사 미수행
        """
        if session.no_response_stage == 0:
            session.no_response_stage = 1
            return NoResponseAction(timeout_stage=1, action="prompt")

        session.end_reason = "TIMEOUT"
        return NoResponseAction(timeout_stage=2, action="end_session")

    def process_dtmf_input(self, session: Any, dtmf_result: Any) -> OrchestratorAction:
        """DTMF 입력 처리 — STT/PIF 파이프라인 우회.
        input_type에 따라 분기:
        - "birth_date" / "password": 본인_인증_모듈로 전달
        - "satisfaction": 1~5 유효성 검증 후 저장
        - "callback_time": 콜백 예약 시간 선택
        """
        input_type = dtmf_result.input_type

        if input_type in ("birth_date", "password"):
            session.auth_module_called = True
            return OrchestratorAction(
                action_type=ActionType.AUTH_REQUIRED,
                target_component="orchestrator",
                context={"dtmf_digits": dtmf_result.digits},
            )

        if input_type == "satisfaction":
            try:
                score = int(dtmf_result.digits)
            except (ValueError, TypeError):
                score = None

            if score is not None and 1 <= score <= 5:
                session.csat_score = score
                return OrchestratorAction(
                    action_type=ActionType.SURVEY,
                    target_component="orchestrator",
                    context={"score": score},
                )
            return OrchestratorAction(
                action_type=ActionType.SYSTEM_CONTROL,
                target_component="orchestrator",
                context={"action": "reask", "reason": "invalid_satisfaction_score"},
            )

        if input_type == "callback_time":
            session.callback_scheduled = True
            return OrchestratorAction(
                action_type=ActionType.PROCESS_BUSINESS,
                target_component="llm_engine",
                context={"callback_slot": dtmf_result.digits},
            )

        return OrchestratorAction(
            action_type=ActionType.SYSTEM_CONTROL,
            target_component="orchestrator",
            context={"action": "reask", "reason": "unknown_dtmf_input_type"},
        )

    def trigger_escalation(self, session: Any, reason: str, context: dict) -> EscalationAction:
        """상담사 연결 폴백 트리거.
        SM에서 턴 데이터/세션 상태 조회 후 ConversationSummary 구성하여 라우팅_엔진 호출.
        """
        summary = {
            "session_id": getattr(session, "session_id", None),
            "turn_count": getattr(session, "turn_count", 0),
            "reason": reason,
        }
        routing_result = {"agent_group": "general", "reason": reason}
        return EscalationAction(reason=reason, summary=summary, routing_result=routing_result)

    def log_pif_bypass(self, session: Any, bypass_reason: str) -> None:
        """PIF 우회 감사 로그 기록.
        session_id, 우회 시각, 우회 사유를 session.audit_log에 기록.
        """
        from datetime import datetime
        entry = {
            "session_id": getattr(session, "session_id", None),
            "bypass_time": datetime.utcnow().isoformat(),
            "bypass_reason": bypass_reason,
        }
        if not hasattr(session, "audit_log"):
            session.audit_log = []
        session.audit_log.append(entry)

    def determine_auth_requirement(self, session: Any, intent: Any) -> AuthRequirement:
        """인증 필요 여부 판단.

        - session.is_authenticated=True → requires_auth=False, is_already_authenticated=True
        - AUTH_REQUIRED_INTENTS AND not authenticated → requires_auth=True, auth_type_hint="BIRTHDATE"
        - 시스템 제어 의도 또는 일반_문의 → requires_auth=False
        """
        if session.is_authenticated:
            return AuthRequirement(
                requires_auth=False,
                is_already_authenticated=True,
                auth_type_hint=None,
            )

        if intent.intent_type in self._AUTH_REQUIRED_INTENTS:
            return AuthRequirement(
                requires_auth=True,
                is_already_authenticated=False,
                auth_type_hint="BIRTHDATE",
            )

        return AuthRequirement(
            requires_auth=False,
            is_already_authenticated=False,
            auth_type_hint=None,
        )
