"""Phase D PG turn_count 갱신 테스트 (M-18)."""

from datetime import datetime
from callbot.session.repository import CallbotDBRepository, InMemoryDBConnection
from callbot.session.models import ConversationSession, ConversationTurn


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
        speaker="customer",
        text="요금 조회해줘",
        intent=None,
        confidence=None,
        api_called=None,
        api_result=None,
        response_text="안내드리겠습니다",
        started_at=now,
        ended_at=now,
        duration_ms=100,
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
        speaker="customer",
        text="더 알려줘",
        intent=None, confidence=None,
        api_called=None, api_result=None,
        response_text="네",
        started_at=now, ended_at=now, duration_ms=50,
    )
    repo.insert_turn(turn2)
    stored = repo.get_session("test-session-1")
    assert stored.total_turn_count == 2
