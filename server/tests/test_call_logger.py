"""CallLogger resolution 판정 + primary_intent 추출 테스트."""
from __future__ import annotations

import pytest
from server.call_logger import CallLogger


def _make_logger():
    """pg_conn=None, llm_engine=None으로 테스트용 CallLogger 생성."""
    return CallLogger(pg_conn=None, llm_engine=None)


def _turn(intent=None, action_type=None, user_text="", bot_text=""):
    return {
        "intent": intent,
        "action_type": action_type,
        "user_text": user_text,
        "bot_text": bot_text,
    }


class TestDetermineResolution:
    def test_transfer_is_escalated(self):
        cl = _make_logger()
        assert cl._determine_resolution("transfer", [_turn()]) == "escalated"

    def test_timeout_is_abandoned(self):
        cl = _make_logger()
        assert cl._determine_resolution("timeout", [_turn()]) == "abandoned"

    def test_disconnect_is_abandoned(self):
        cl = _make_logger()
        assert cl._determine_resolution("disconnect", [_turn()]) == "abandoned"

    def test_normal_end_with_business_is_resolved(self):
        cl = _make_logger()
        turns = [_turn(action_type="업무_처리")]
        assert cl._determine_resolution("normal", turns) == "resolved"

    def test_normal_end_without_business_is_unresolved(self):
        cl = _make_logger()
        turns = [_turn(action_type="시스템_제어")]
        assert cl._determine_resolution("normal", turns) == "unresolved"


class TestExtractPrimaryIntent:
    def test_extracts_last_non_null_intent(self):
        cl = _make_logger()
        turns = [
            _turn(intent="greeting"),
            _turn(intent="billing_inquiry"),
            _turn(intent=None),
        ]
        assert cl._extract_primary_intent(turns) == "billing_inquiry"
