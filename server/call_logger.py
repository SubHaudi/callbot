"""callbot.server.call_logger — 통화 기록 + 요약 생성"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
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
        resolution = self._determine_resolution(end_reason, turns)
        primary_intent = self._extract_primary_intent(turns)
        summary = self._generate_summary(turns)
        now = datetime.now(timezone.utc)

        if self._pg is None:
            return

        conn = self._pg._acquire_conn()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE conversation_sessions
                       SET end_time = %s, end_reason = %s, resolution = %s,
                           primary_intent = %s, call_summary = %s,
                           summary_generated_at = %s, updated_at = %s
                       WHERE session_id = %s""",
                    (now, end_reason, resolution, primary_intent, summary,
                     now if summary else None, now, session_id),
                )
            logger.info("통화 기록 완료: session=%s resolution=%s", session_id, resolution)
        except Exception as e:
            logger.error("통화 기록 실패: session=%s error=%s", session_id, e)
        finally:
            self._pg._release_conn(conn, close=False)

    def _determine_resolution(
        self, end_reason: str, turns: List[Dict[str, Any]]
    ) -> str:
        """end_reason + 턴 이력 기반 resolution 판정."""
        if end_reason == "transfer":
            return "escalated"
        if end_reason in ("timeout", "disconnect"):
            return "abandoned"
        # 정상 종료: 마지막 턴의 action_type 확인
        if turns:
            last_action = turns[-1].get("action_type") or ""
            if last_action == "업무_처리":
                return "resolved"
        return "unresolved"

    def _extract_primary_intent(self, turns: List[Dict[str, Any]]) -> Optional[str]:
        """마지막 비-null 인텐트 추출."""
        for turn in reversed(turns):
            intent = turn.get("intent")
            if intent is not None:
                return intent
        return None

    def _generate_summary(self, turns: List[Dict[str, Any]]) -> Optional[str]:
        """LLM으로 대화 요약 생성 (최대 200자). 실패 시 None."""
        if self._llm is None:
            return None
        try:
            conversation = "\n".join(
                f"고객: {t.get('user_text', '')}\n봇: {t.get('bot_text', '')}"
                for t in turns
            )
            prompt = (
                f"다음 콜봇 대화를 200자 이내로 요약해주세요. "
                f"목적, 결과, 핵심 내용을 포함하세요.\n\n{conversation}"
            )
            summary = self._llm.generate(prompt)
            if summary and len(summary) > 200:
                summary = summary[:200]
            return summary
        except Exception as e:
            logger.warning("요약 생성 실패: %s", e)
            return None
