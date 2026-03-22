"""callbot.voice_io.dtmf_processor — DTMF 처리기"""
from __future__ import annotations

import time
from typing import Any, Optional

from callbot.voice_io.models import DTMFResult

# Default timeout in seconds
DTMF_DEFAULT_TIMEOUT_SEC: int = 5

# DTMF 특수키 매핑 (M-26, M-32)
DTMF_SPECIAL_KEYS: dict[str, str] = {
    "*": "이전_메뉴",
    "#": "입력_확인",
}

# 세션 TTL (초) — 이 시간 동안 push_digit이 없으면 세션 자동 정리
DTMF_SESSION_TTL_SEC: int = 300  # 5분


class DTMFProcessor:
    """DTMF 키패드 입력 처리기.

    세션별 캡처 상태를 내부적으로 관리한다.
    start_capture() → push_digit() × N → get_input() 순서로 사용한다.
    """

    def __init__(self) -> None:
        # session_id → capture state dict
        self._sessions: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_capture(
        self,
        session_id: str,
        expected_length: int,
        input_type: str = "unknown",
        timeout_sec: int = DTMF_DEFAULT_TIMEOUT_SEC,
    ) -> None:
        """DTMF 입력 캡처 시작. 지정 자릿수 입력 시 자동 완료."""
        self._sessions[session_id] = {
            "digits": "",
            "expected_length": expected_length,
            "input_type": input_type,
            "timeout_sec": timeout_sec,
            "start_time": time.monotonic(),
            "last_activity": time.monotonic(),
        }

    def push_digit(self, session_id: str, digit: str) -> Optional[str]:
        """DTMF 신호 한 자리 추가.

        숫자(0~9)는 저장, 특수키(*, #)는 매핑된 액션 반환.
        Returns:
            None: 숫자 입력 (버퍼에 저장됨)
            str: 특수키 액션 (예: "이전_메뉴", "입력_확인")
        """
        state = self._sessions[session_id]
        state["last_activity"] = time.monotonic()

        # 특수키 체크 (M-26, M-32)
        if digit in DTMF_SPECIAL_KEYS:
            return DTMF_SPECIAL_KEYS[digit]

        # Filter: only 0-9
        if digit.isdigit():
            state["digits"] += digit

        return None

    def get_input(self, session_id: str) -> DTMFResult:
        """캡처된 DTMF 입력 반환."""
        state = self._sessions[session_id]
        digits = state["digits"]
        expected_length = state["expected_length"]
        input_type = state["input_type"]
        timeout_sec = state["timeout_sec"]
        start_time = state["start_time"]

        elapsed = time.monotonic() - start_time
        is_timeout = elapsed >= timeout_sec and len(digits) < expected_length

        return DTMFResult.create(
            digits=digits,
            expected_length=expected_length,
            is_timeout=is_timeout,
            input_type=input_type,
        )

    def cleanup_expired(self) -> int:
        """TTL 만료된 세션 정리. 정리된 세션 수 반환."""
        now = time.monotonic()
        expired = [
            sid for sid, state in self._sessions.items()
            if now - state.get("last_activity", state["start_time"]) >= DTMF_SESSION_TTL_SEC
        ]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)

    @property
    def active_session_count(self) -> int:
        """현재 활성 DTMF 세션 수."""
        return len(self._sessions)
