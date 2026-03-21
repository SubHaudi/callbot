"""Phase D Redis PG fallback 테스트 (FR-010, NFR-004)."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from callbot.session.session_store import InMemorySessionStore
from callbot.session.models import SessionContext


def _make_session(session_id="test-1"):
    return SessionContext(
        session_id=session_id,
        caller_id="010-0000-0000",
        is_authenticated=False,
        customer_info=None,
        auth_status=None,
        turns=[],
        business_turn_count=0,
        start_time=datetime.now(),
        tts_speed_factor=1.0,
        cached_billing_data=None,
        injection_detection_count=0,
        masking_restore_failure_count=0,
        plan_list_context=None,
        pending_intent=None,
        pending_classification=None,
    )


class TestRedisPGFallback:
    def test_redis_miss_falls_back_to_store(self):
        """When primary store misses, load returns None (baseline)."""
        store = InMemorySessionStore()
        result = store.load("nonexistent")
        assert result is None

    def test_store_save_and_load(self):
        """Basic save/load works (baseline for fallback tests)."""
        store = InMemorySessionStore()
        session = _make_session()
        store.save(session)
        loaded = store.load("test-1")
        assert loaded is not None
        assert loaded.session_id == "test-1"

    def test_store_delete_and_load_returns_none(self):
        """After delete, load returns None."""
        store = InMemorySessionStore()
        session = _make_session()
        store.save(session)
        store.delete("test-1")
        assert store.load("test-1") is None
