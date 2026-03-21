"""callbot.session.models — 세션 핵심 데이터 모델"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from callbot.session.enums import AuthStatus, AuthType, EndReason, TurnType


# ---------------------------------------------------------------------------
# 런타임 인메모리 모델
# ---------------------------------------------------------------------------

@dataclass
class Turn:
    """런타임 턴 데이터."""
    turn_id: str
    turn_type: TurnType
    customer_utterance: str
    bot_response: str
    intent: Optional[Any]
    entities: list
    stt_confidence: float
    intent_confidence: float
    llm_confidence: Optional[float]
    verification_status: Optional[Any]
    response_time_ms: int
    is_dtmf_input: bool
    is_barge_in: bool
    timestamp: datetime


@dataclass
class PlanListContext:
    """요금제 목록 페이징 상태."""
    available_plans: list
    current_page: int
    page_size: int
    current_plan: dict
    is_exhausted: bool


@dataclass
class SessionContext:
    """런타임 인메모리 세션 상태."""
    session_id: str
    caller_id: str
    is_authenticated: bool
    customer_info: Optional[Any]
    auth_status: AuthStatus
    turns: list                              # list[Turn]
    business_turn_count: int                 # 업무 턴 카운트 (최대 20)
    start_time: datetime
    tts_speed_factor: float                  # TTS 속도 (기본 1.0)
    cached_billing_data: Optional[dict]      # 과금 데이터 캐시
    injection_detection_count: int           # 프롬프트 인젝션 탐지 횟수
    masking_restore_failure_count: int       # 마스킹 복원 실패 횟수
    plan_list_context: Optional[PlanListContext]
    pending_intent: Optional[Any]
    pending_classification: Optional[Any]
    pending_switch_intent: Optional[Any] = None  # Phase E: 인텐트 전환 대기

    @property
    def turn_count(self) -> int:
        """총 턴 수 (turns 리스트 길이 기반)."""
        return len(self.turns)

    @property
    def elapsed_minutes(self) -> float:
        """세션 시작 이후 경과 시간 (분)."""
        delta = datetime.now() - self.start_time
        return delta.total_seconds() / 60.0

    @property
    def has_active_transaction(self) -> bool:
        """진행 중인 다단계 플로우가 있는지."""
        return self.pending_intent is not None


@dataclass
class SessionLimitStatus:
    """세션 턴/시간 제한 상태.

    Invariants:
    - is_limit_reached=True → is_warning_needed=True
    - remaining_turns = max_business_turns - current_business_turns
    - remaining_minutes = max_minutes - elapsed_minutes
    """
    current_business_turns: int
    max_business_turns: int
    elapsed_minutes: float
    max_minutes: float
    is_warning_needed: bool
    is_limit_reached: bool
    has_active_transaction: bool
    remaining_turns: int
    remaining_minutes: float

    def __post_init__(self) -> None:
        # 불변 조건: 제한 도달 시 경고도 반드시 True
        if self.is_limit_reached:
            self.is_warning_needed = True


# ---------------------------------------------------------------------------
# 영속 DB 모델
# ---------------------------------------------------------------------------

@dataclass
class AuthAttempt:
    """인증 시도 이력."""
    auth_type: AuthType
    is_success: bool
    attempted_at: datetime


@dataclass
class ConversationSession:
    """영속 DB 세션 레코드."""
    session_id: str
    caller_id: str
    customer_id: Optional[str]
    start_time: datetime
    end_time: Optional[datetime]
    end_reason: Optional[EndReason]
    is_authenticated: bool
    auth_method: Optional[AuthType]
    business_turn_count: int
    total_turn_count: int
    tts_speed_factor: float
    csat_score: Optional[int]
    escalation_reason: Optional[str]
    escalation_reasons: list
    auth_attempts: list                      # list[AuthAttempt]
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


@dataclass
class ConversationTurn:
    """영속 DB 턴 레코드."""
    turn_id: str
    session_id: str
    turn_number: int
    turn_type: TurnType
    customer_utterance: str
    stt_confidence: float
    intent: Optional[Any]
    intent_confidence: float
    entities: list
    bot_response: str
    llm_confidence: Optional[float]
    verification_status: Optional[Any]
    response_time_ms: int
    is_dtmf_input: bool
    is_barge_in: bool
    is_legal_required: bool
    masking_applied: bool
    masking_restore_success: bool
    unrestored_tokens: list
    response_replaced_by_template: bool
    timestamp: datetime
