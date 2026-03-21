"""callbot.session.session_manager — 세션_관리자"""
from __future__ import annotations

import uuid
from datetime import datetime

from typing import Any, Optional

from callbot.session.enums import AuthStatus, EndReason, TurnType
from callbot.session.exceptions import SessionNotFoundError
from callbot.session.models import ConversationSession, ConversationTurn, PlanListContext, SessionContext, SessionLimitStatus, Turn
from callbot.session.repository import CallbotDBRepository
from callbot.session.session_store import SessionStoreBase


class SessionManager:
    """대화 세션 생명주기(생성/업데이트/종료)를 관리한다.

    SessionStoreBase를 통해 런타임 SessionContext를 저장/조회하며,
    세션 간 완전한 데이터 격리를 보장한다.
    콜봇_DB_저장소를 통해 영속 저장을 수행한다.
    """

    MAX_BUSINESS_TURNS = 20
    MAX_MINUTES = 15.0
    WARNING_TURNS = 18
    WARNING_MINUTES = 13.0

    def __init__(self, repository: CallbotDBRepository, session_store: SessionStoreBase,
                 metrics_collector=None) -> None:
        self._repository = repository
        self._store = session_store
        self._metrics = metrics_collector

    def _get_context(self, session_id: str) -> SessionContext:
        """SessionStoreBase.load()로 세션 조회. 없으면 SessionNotFoundError."""
        ctx = self._store.load(session_id)
        if ctx is None:
            raise SessionNotFoundError(session_id)
        return ctx

    def get_session(self, session_id: str) -> Optional[SessionContext]:
        """Public 세션 조회. 없으면 None 반환 (예외 없음)."""
        return self._store.load(session_id)

    def _save_context(self, context: SessionContext) -> None:
        """상태 변경 후 저장소에 반영."""
        self._store.save(context)

    def create_session(self, caller_id: str) -> SessionContext:
        """새 대화 세션 생성.

        - SessionContext 생성 (session_id UUID v4 부여)
        - SessionStoreBase에 저장
        - ConversationSession INSERT (end_time=NULL, end_reason=NULL)
        - 세션 간 격리 보장

        Args:
            caller_id: 발신번호 (비어있지 않은 문자열)

        Returns:
            생성된 SessionContext
        """
        session_id = str(uuid.uuid4())
        now = datetime.now()

        context = SessionContext(
            session_id=session_id,
            caller_id=caller_id,
            is_authenticated=False,
            customer_info=None,
            auth_status=AuthStatus.NOT_ATTEMPTED,
            turns=[],
            business_turn_count=0,
            start_time=now,
            tts_speed_factor=1.0,
            cached_billing_data=None,
            injection_detection_count=0,
            masking_restore_failure_count=0,
            plan_list_context=None,
            pending_intent=None,
            pending_classification=None,
        )

        self._save_context(context)

        # 영속 저장 위임
        db_session = ConversationSession(
            session_id=session_id,
            caller_id=caller_id,
            customer_id=None,
            start_time=now,
            end_time=None,
            end_reason=None,
            is_authenticated=False,
            auth_method=None,
            business_turn_count=0,
            total_turn_count=0,
            tts_speed_factor=1.0,
            csat_score=None,
            escalation_reason=None,
            escalation_reasons=[],
            auth_attempts=[],
            created_at=now,
            updated_at=now,
            expires_at=now.replace(year=now.year + 1),
        )
        self._repository.insert_session(db_session)

        # 세션 메트릭
        if self._metrics is not None:
            self._metrics.increment("session_created_total")
            self._metrics.set_gauge("active_sessions", self._store.count())

        return context

    def update_turn(self, session_id: str, turn: Turn) -> SessionContext:
        """턴 업데이트 (업무 턴/시스템 턴 구분).

        - 업무 턴: business_turn_count 1 증가
        - 시스템 턴: business_turn_count 불변
        - ConversationTurn INSERT (RPO 1분 보장)

        Args:
            session_id: 활성 세션 ID
            turn: 업데이트할 Turn 객체

        Returns:
            업데이트된 SessionContext

        Raises:
            SessionNotFoundError: session_id가 존재하지 않을 때
        """
        context = self._get_context(session_id)

        # turn_number는 append 전 현재 길이 + 1 (1-based)
        turn_number = len(context.turns) + 1

        # 업무 턴만 카운트 증가
        if turn.turn_type == TurnType.BUSINESS:
            context.business_turn_count += 1

        # 턴 목록에 추가
        context.turns.append(turn)

        # 저장소에 반영
        self._save_context(context)

        # 영속 저장 위임
        db_turn = ConversationTurn(
            turn_id=turn.turn_id,
            session_id=session_id,
            turn_number=turn_number,
            turn_type=turn.turn_type,
            customer_utterance=turn.customer_utterance,
            stt_confidence=turn.stt_confidence,
            intent=turn.intent,
            intent_confidence=turn.intent_confidence,
            entities=turn.entities,
            bot_response=turn.bot_response,
            llm_confidence=turn.llm_confidence,
            verification_status=turn.verification_status,
            response_time_ms=turn.response_time_ms,
            is_dtmf_input=turn.is_dtmf_input,
            is_barge_in=turn.is_barge_in,
            is_legal_required=False,
            masking_applied=False,
            masking_restore_success=True,
            unrestored_tokens=[],
            response_replaced_by_template=False,
            timestamp=turn.timestamp,
        )
        self._repository.insert_turn(db_turn)

        return context

    def end_session(self, session_id: str, reason: EndReason) -> None:
        """세션 종료.

        - ConversationSession UPDATE (end_time, end_reason)
        - 저장소에서 세션 삭제

        Args:
            session_id: 활성 세션 ID
            reason: 종료 사유

        Raises:
            SessionNotFoundError: session_id가 존재하지 않을 때
        """
        self._get_context(session_id)  # 존재 확인

        self._repository.update_session(session_id, {"end_time": datetime.now(), "end_reason": reason})
        self._store.delete(session_id)

        # 세션 종료 메트릭
        if self._metrics is not None:
            self._metrics.increment("session_ended_total")
            self._metrics.set_gauge("active_sessions", self._store.count())

    def check_limits(self, session_id: str) -> SessionLimitStatus:
        """턴/시간 제한 확인.

        Args:
            session_id: 활성 세션 ID

        Returns:
            SessionLimitStatus

        Raises:
            SessionNotFoundError: session_id가 존재하지 않을 때
        """
        context = self._get_context(session_id)
        elapsed_minutes = (datetime.now() - context.start_time).total_seconds() / 60
        current_business_turns = context.business_turn_count

        is_warning_needed = (
            current_business_turns >= self.WARNING_TURNS
            or elapsed_minutes >= self.WARNING_MINUTES
        )
        is_limit_reached = (
            current_business_turns >= self.MAX_BUSINESS_TURNS
            or elapsed_minutes >= self.MAX_MINUTES
        )
        remaining_turns = self.MAX_BUSINESS_TURNS - current_business_turns
        remaining_minutes = self.MAX_MINUTES - elapsed_minutes
        has_active_transaction = context.cached_billing_data is not None

        return SessionLimitStatus(
            current_business_turns=current_business_turns,
            max_business_turns=self.MAX_BUSINESS_TURNS,
            elapsed_minutes=elapsed_minutes,
            max_minutes=self.MAX_MINUTES,
            is_warning_needed=is_warning_needed,
            is_limit_reached=is_limit_reached,
            has_active_transaction=has_active_transaction,
            remaining_turns=remaining_turns,
            remaining_minutes=remaining_minutes,
        )

    # ------------------------------------------------------------------
    # SessionContext 상태 관리 헬퍼 메서드
    # ------------------------------------------------------------------

    def increment_injection_count(self, session_id: str) -> int:
        """프롬프트 인젝션 탐지 횟수를 1 증가시키고 현재 값을 반환한다."""
        ctx = self._get_context(session_id)
        ctx.injection_detection_count += 1
        self._save_context(ctx)
        return ctx.injection_detection_count

    def increment_masking_failure_count(self, session_id: str) -> int:
        """마스킹 복원 실패 횟수를 1 증가시키고 현재 값을 반환한다."""
        ctx = self._get_context(session_id)
        ctx.masking_restore_failure_count += 1
        self._save_context(ctx)
        return ctx.masking_restore_failure_count

    def update_cached_billing_data(self, session_id: str, data: dict) -> None:
        """과금 데이터 캐시를 업데이트한다."""
        ctx = self._get_context(session_id)
        ctx.cached_billing_data = data
        self._save_context(ctx)

    def invalidate_billing_cache(self, session_id: str) -> None:
        """과금 데이터 캐시를 None으로 초기화한다 (트랜잭션 완료 시 호출)."""
        ctx = self._get_context(session_id)
        ctx.cached_billing_data = None
        self._save_context(ctx)

    def set_pending_intent(
        self,
        session_id: str,
        intent: Any,
        classification: Any,
    ) -> None:
        """인증 전 업무 의도와 분류 결과를 저장한다."""
        ctx = self._get_context(session_id)
        ctx.pending_intent = intent
        ctx.pending_classification = classification
        self._save_context(ctx)

    def pop_pending_intent(self, session_id: str) -> tuple[Any, Any]:
        """저장된 pending_intent와 pending_classification을 반환하고 초기화한다."""
        ctx = self._get_context(session_id)
        intent = ctx.pending_intent
        classification = ctx.pending_classification
        ctx.pending_intent = None
        ctx.pending_classification = None
        self._save_context(ctx)
        return intent, classification

    def set_plan_list_context(self, session_id: str, context: PlanListContext) -> None:
        """요금제 목록 페이징 상태를 저장한다."""
        ctx = self._get_context(session_id)
        ctx.plan_list_context = context
        self._save_context(ctx)

    def clear_plan_list_context(self, session_id: str) -> None:
        """요금제 목록 페이징 상태를 초기화한다."""
        ctx = self._get_context(session_id)
        ctx.plan_list_context = None
        self._save_context(ctx)
