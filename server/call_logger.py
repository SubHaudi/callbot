"""callbot.server.call_logger — 통화 기록 + 요약 생성"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CallLogger:
    """통화 종료 시 resolution 판정 + 요약 생성 + DB 저장."""

    def __init__(self, pg_conn: Any, llm_engine: Any = None) -> None:
        self._pg = pg_conn
        self._llm = llm_engine

    def finalize_session(
        self,
        session_id: str,
        turns: List[Dict[str, Any]],
        end_reason: str = "normal",
    ) -> None:
        """통화 종료 처리: resolution 판정 + primary_intent 추출 + 요약 생성 + DB 저장."""
        pass

    def _determine_resolution(
        self, end_reason: str, turns: List[Dict[str, Any]]
    ) -> str:
        """end_reason + 턴 이력 기반 resolution 판정."""
        pass

    def _extract_primary_intent(self, turns: List[Dict[str, Any]]) -> Optional[str]:
        """마지막 비-null 인텐트 추출."""
        pass

    def _generate_summary(self, turns: List[Dict[str, Any]]) -> Optional[str]:
        """LLM으로 대화 요약 생성 (최대 200자). 실패 시 None."""
        pass
