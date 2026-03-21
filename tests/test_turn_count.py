"""Phase D PG turn_count 갱신 테스트 (M-18)."""

from datetime import datetime
from callbot.session.repository import CallbotDBRepository, InMemoryDBConnection
from callbot.session.models import ConversationSession, ConversationTurn, TurnType


def _make():
    db = InMemoryDBConnection()
    repo = CallbotDBRepository(db, retry_delays=[0, 0, 0])
    return repo, db


def test_turn_count_increments_after_insert_turn():
    """FR-011: insert_turn 후 turn_count = turn_count + 1."""
    repo, db = _make()
    now = datetime.now()

    session = ConversationSession(
        session_id="test-session-1",
        caller_id="010-0000-0000",
        customer_id=None,
        start_time=now, end_time=None, end_reason=None,
        is_authenticated=False, auth_method=None,
        business_turn_count=0, total_turn_count=0,
        tts_speed_factor=1.0,
        csat_score=None, escalation_reason=None,
        escalation_reasons=[], auth_attempts=[],
        created_at=now, updated_at=now,
        expires_at=now.replace(year=now.year + 1),
    )
    repo.insert_session(session)

    # Verify initial turn_count = 0
    stored = repo.get_session("test-session-1")
    assert stored.total_turn_count == 0

    # Insert a turn
    turn = ConversationTurn(
        turn_id="turn-1",
        session_id="test-session-1",
        turn_number=1,
        turn_type=TurnType.BUSINESS,
        customer_utterance="요금 조회해줘",
        stt_confidence=0.95,
        intent=None,
        intent_confidence=0.0,
        entities=[],
        bot_response="안내드리겠습니다",
        llm_confidence=None,
        verification_status=None,
        response_time_ms=100,
        is_dtmf_input=False,
        is_barge_in=False,
        is_legal_required=False,
        masking_applied=False,
        masking_restore_success=True,
        unrestored_tokens=[],
        response_replaced_by_template=False,
        timestamp=now,
    )
    repo.insert_turn(turn)

    # turn_count should be 1 now
    stored = repo.get_session("test-session-1")
    assert stored.total_turn_count == 1

    # Insert another turn
    turn2 = ConversationTurn(
        turn_id="turn-2",
        session_id="test-session-1",
        turn_number=2,
        turn_type=TurnType.BUSINESS,
        customer_utterance="더 알려줘",
        stt_confidence=0.95,
        intent=None, intent_confidence=0.0, entities=[],
        bot_response="네",
        llm_confidence=None, verification_status=None,
        response_time_ms=50,
        is_dtmf_input=False, is_barge_in=False,
        is_legal_required=False, masking_applied=False,
        masking_restore_success=True, unrestored_tokens=[],
        response_replaced_by_template=False, timestamp=now,
    )
    repo.insert_turn(turn2)
    stored = repo.get_session("test-session-1")
    assert stored.total_turn_count == 2
