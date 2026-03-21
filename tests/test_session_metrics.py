"""Phase D 세션 메트릭 테스트."""

from callbot.session.repository import CallbotDBRepository, InMemoryDBConnection
from callbot.session.session_manager import SessionManager
from callbot.session.session_store import InMemorySessionStore
from callbot.session.enums import EndReason
from callbot.monitoring.in_memory import InMemoryCollector


def _make():
    db = InMemoryDBConnection()
    repo = CallbotDBRepository(db, retry_delays=[0, 0, 0])
    store = InMemorySessionStore()
    metrics = InMemoryCollector()
    sm = SessionManager(repo, store, metrics_collector=metrics)
    return sm, metrics


class TestSessionMetrics:
    def test_session_created_counter(self):
        sm, metrics = _make()
        sm.create_session("010-0000-0000")
        assert metrics.get_counter("session_created_total") == 1
        sm.create_session("010-0000-0001")
        assert metrics.get_counter("session_created_total") == 2

    def test_session_ended_counter(self):
        sm, metrics = _make()
        session = sm.create_session("010-0000-0000")
        sm.end_session(session.session_id, EndReason.NORMAL)
        assert metrics.get_counter("session_ended_total") == 1

    def test_active_sessions_gauge(self):
        sm, metrics = _make()
        s1 = sm.create_session("010-0000-0000")
        assert metrics.get_gauge("active_sessions") == 1
        s2 = sm.create_session("010-0000-0001")
        assert metrics.get_gauge("active_sessions") == 2
        sm.end_session(s1.session_id, EndReason.NORMAL)
        assert metrics.get_gauge("active_sessions") == 1
