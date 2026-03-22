"""Phase F TASK-012: DTMF 특수키 + TTL 테스트."""
from __future__ import annotations

import pytest
from unittest.mock import patch

from callbot.voice_io.dtmf_processor import (
    DTMFProcessor,
    DTMF_SPECIAL_KEYS,
    DTMF_SESSION_TTL_SEC,
)


class TestDTMFSpecialKeys:
    """FR-007: DTMF 특수키 매핑 (M-26, M-32)."""

    def test_star_key_returns_previous_menu(self):
        """* 키 → '이전_메뉴' 액션."""
        proc = DTMFProcessor()
        proc.start_capture("sess-1", expected_length=4)
        action = proc.push_digit("sess-1", "*")
        assert action == "이전_메뉴"

    def test_hash_key_returns_confirm(self):
        """# 키 → '입력_확인' 액션."""
        proc = DTMFProcessor()
        proc.start_capture("sess-1", expected_length=4)
        action = proc.push_digit("sess-1", "#")
        assert action == "입력_확인"

    def test_digit_key_returns_none(self):
        """숫자 키 → None (버퍼에 저장)."""
        proc = DTMFProcessor()
        proc.start_capture("sess-1", expected_length=4)
        action = proc.push_digit("sess-1", "5")
        assert action is None

    def test_special_keys_not_stored_in_buffer(self):
        """특수키는 digits 버퍼에 저장되지 않는다."""
        proc = DTMFProcessor()
        proc.start_capture("sess-1", expected_length=4)
        proc.push_digit("sess-1", "*")
        proc.push_digit("sess-1", "1")
        proc.push_digit("sess-1", "#")
        proc.push_digit("sess-1", "2")
        result = proc.get_input("sess-1")
        assert result.digits == "12"


class TestDTMFSessionTTL:
    """DTMF 세션 TTL 자동 정리."""

    def test_ttl_expired_session_cleaned(self):
        """TTL 만료 시 세션 자동 정리."""
        proc = DTMFProcessor()
        proc.start_capture("sess-1", expected_length=4)
        assert proc.active_session_count == 1

        # last_activity를 과거로 조작
        proc._sessions["sess-1"]["last_activity"] -= DTMF_SESSION_TTL_SEC + 1
        cleaned = proc.cleanup_expired()
        assert cleaned == 1
        assert proc.active_session_count == 0

    def test_ttl_not_expired_session_kept(self):
        """TTL 미만이면 세션 유지."""
        proc = DTMFProcessor()
        proc.start_capture("sess-1", expected_length=4)
        cleaned = proc.cleanup_expired()
        assert cleaned == 0
        assert proc.active_session_count == 1

    def test_push_digit_updates_last_activity(self):
        """push_digit 호출 시 last_activity 갱신."""
        proc = DTMFProcessor()
        proc.start_capture("sess-1", expected_length=4)
        old_activity = proc._sessions["sess-1"]["last_activity"]
        # 약간의 시간 지연 시뮬
        proc._sessions["sess-1"]["last_activity"] -= 10
        proc.push_digit("sess-1", "5")
        assert proc._sessions["sess-1"]["last_activity"] > old_activity - 10
