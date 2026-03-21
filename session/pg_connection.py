"""callbot.session.pg_connection — PostgreSQL DBConnectionBase 구현체"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from callbot.session.pg_config import PoolTimeoutError
from callbot.session.pg_serializers import (
    row_to_session,
    row_to_turn,
    session_to_row,
    turn_to_row,
)
from callbot.session.repository import DBConnectionBase

logger = logging.getLogger(__name__)

# SQL injection 방지: UPDATE_SESSION에서 허용되는 컬럼 목록
_ALLOWED_SESSION_COLUMNS: frozenset[str] = frozenset({
    "end_time", "end_reason", "is_authenticated", "auth_method",
    "business_turn_count", "total_turn_count", "tts_speed_factor",
    "csat_score", "escalation_reason", "escalation_reasons",
    "auth_attempts", "updated_at", "expires_at",
})

# psycopg2는 런타임 의존성 — import 오류를 명확히 전달
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from psycopg2.pool import ThreadedConnectionPool
except ImportError as e:  # pragma: no cover
    raise ImportError("psycopg2-binary가 설치되어 있지 않습니다: pip install psycopg2-binary") from e


class PostgreSQLConnection(DBConnectionBase):
    """psycopg2 ThreadedConnectionPool 기반 PostgreSQL 연결 구현체."""

    def __init__(
        self,
        dsn: str,
        min_connections: int = 2,
        max_connections: int = 10,
        pool_timeout: float = 30.0,
    ) -> None:
        self._pool = ThreadedConnectionPool(min_connections, max_connections, dsn)
        self._semaphore = threading.Semaphore(max_connections)
        self._pool_timeout = pool_timeout

    @classmethod
    def from_env(
        cls,
        min_connections: int = 2,
        max_connections: int = 10,
        pool_timeout: float = 30.0,
    ) -> PostgreSQLConnection:
        """환경변수에서 DSN을 구성하여 인스턴스를 생성한다.

        CALLBOT_USE_SECRETS_MANAGER=true 시:
            SecretsManager에서 DB 비밀번호를 조회하고,
            CALLBOT_DB_HOST, CALLBOT_DB_PORT, CALLBOT_DB_NAME, CALLBOT_DB_USER
            환경변수와 조합하여 DSN을 구성한다.

        미설정 또는 false 시:
            기존 CALLBOT_DB_DSN 환경변수를 그대로 사용한다 (하위 호환성).

        Note:
            BedrockClaudeService는 IAM 역할 기반 인증이므로
            SecretsManager 연동 대상에서 제외한다.
        """
        use_sm = os.environ.get("CALLBOT_USE_SECRETS_MANAGER", "false").lower()

        if use_sm == "true":
            from callbot.security.secrets_manager import SecretsManager

            sm = SecretsManager.from_env()
            password = sm.get_secret("callbot/db-password")
            host = os.environ.get("CALLBOT_DB_HOST", "localhost")
            port = os.environ.get("CALLBOT_DB_PORT", "5432")
            dbname = os.environ.get("CALLBOT_DB_NAME", "callbot")
            user = os.environ.get("CALLBOT_DB_USER", "callbot")
            dsn = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
        else:
            dsn = os.environ["CALLBOT_DB_DSN"]

        return cls(
            dsn=dsn,
            min_connections=min_connections,
            max_connections=max_connections,
            pool_timeout=pool_timeout,
        )

    def _acquire_conn(self):
        acquired = self._semaphore.acquire(timeout=self._pool_timeout)
        if not acquired:
            raise PoolTimeoutError(
                f"커넥션 풀 타임아웃: {self._pool_timeout}초 이내에 연결을 획득하지 못했습니다."
            )
        return self._pool.getconn()

    def _release_conn(self, conn, close: bool = False) -> None:
        self._pool.putconn(conn, close=close)
        self._semaphore.release()

    # ------------------------------------------------------------------
    # execute
    # ------------------------------------------------------------------

    def execute(self, query: str, params: tuple = ()) -> None:
        q = query.strip().upper()
        conn = self._acquire_conn()
        _error = False
        try:
            with conn.cursor() as cur:
                if q.startswith("INSERT_SESSION"):
                    session = params[0]
                    row = session_to_row(session)
                    cur.execute(
                        """
                        INSERT INTO conversation_sessions (
                            session_id, caller_id, customer_id, start_time, end_time,
                            end_reason, is_authenticated, auth_method,
                            business_turn_count, total_turn_count, tts_speed_factor,
                            csat_score, escalation_reason, escalation_reasons,
                            auth_attempts, created_at, updated_at, expires_at
                        ) VALUES (
                            %(session_id)s, %(caller_id)s, %(customer_id)s, %(start_time)s,
                            %(end_time)s, %(end_reason)s, %(is_authenticated)s, %(auth_method)s,
                            %(business_turn_count)s, %(total_turn_count)s, %(tts_speed_factor)s,
                            %(csat_score)s, %(escalation_reason)s, %(escalation_reasons)s::jsonb,
                            %(auth_attempts)s::jsonb, %(created_at)s, %(updated_at)s, %(expires_at)s
                        )
                        """,
                        row,
                    )
                elif q.startswith("UPDATE_SESSION"):
                    session_id, updates = params[0], params[1]
                    # SQL injection 방지: 허용 컬럼만 SET 절에 사용
                    invalid_cols = set(updates.keys()) - _ALLOWED_SESSION_COLUMNS
                    if invalid_cols:
                        raise ValueError(
                            f"Disallowed column(s) in UPDATE: {invalid_cols}"
                        )
                    set_clauses = ", ".join(f"{k} = %({k})s" for k in updates)
                    updates["session_id"] = session_id
                    cur.execute(
                        f"UPDATE conversation_sessions SET {set_clauses} WHERE session_id = %(session_id)s",
                        updates,
                    )
                elif q.startswith("INSERT_TURN"):
                    turn = params[0]
                    row = turn_to_row(turn)
                    cur.execute(
                        """
                        INSERT INTO conversation_turns (
                            turn_id, session_id, turn_number, turn_type,
                            customer_utterance, stt_confidence, intent, intent_confidence,
                            entities, bot_response, llm_confidence, verification_status,
                            response_time_ms, is_dtmf_input, is_barge_in, is_legal_required,
                            masking_applied, masking_restore_success, unrestored_tokens,
                            response_replaced_by_template, timestamp
                        ) VALUES (
                            %(turn_id)s, %(session_id)s, %(turn_number)s, %(turn_type)s,
                            %(customer_utterance)s, %(stt_confidence)s, %(intent)s, %(intent_confidence)s,
                            %(entities)s::jsonb, %(bot_response)s, %(llm_confidence)s, %(verification_status)s,
                            %(response_time_ms)s, %(is_dtmf_input)s, %(is_barge_in)s, %(is_legal_required)s,
                            %(masking_applied)s, %(masking_restore_success)s, %(unrestored_tokens)s::jsonb,
                            %(response_replaced_by_template)s, %(timestamp)s
                        )
                        """,
                        row,
                    )
            conn.commit()
        except psycopg2.Error:
            conn.rollback()
            _error = True
            raise
        finally:
            self._release_conn(conn, close=_error)

    # ------------------------------------------------------------------
    # fetchone / fetchall
    # ------------------------------------------------------------------

    def fetchone(self, query: str, params: tuple = ()) -> Optional[object]:
        q = query.strip().upper()
        conn = self._acquire_conn()
        _error = False
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if q.startswith("SELECT_SESSION"):
                    session_id = params[0]
                    cur.execute(
                        "SELECT * FROM conversation_sessions WHERE session_id = %s",
                        (session_id,),
                    )
                    row = cur.fetchone()
                    return row_to_session(dict(row)) if row else None
                return None
        except psycopg2.Error:
            _error = True
            raise
        finally:
            self._release_conn(conn, close=_error)

    def fetchall(self, query: str, params: tuple = ()) -> list:
        q = query.strip().upper()
        conn = self._acquire_conn()
        _error = False
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if q.startswith("SELECT_TURNS"):
                    session_id = params[0]
                    cur.execute(
                        "SELECT * FROM conversation_turns WHERE session_id = %s ORDER BY turn_number",
                        (session_id,),
                    )
                    rows = cur.fetchall()
                    return [row_to_turn(dict(r)) for r in rows]
                return []
        except psycopg2.Error:
            _error = True
            raise
        finally:
            self._release_conn(conn, close=_error)

    # ------------------------------------------------------------------
    # health_check / close
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        try:
            conn = self._acquire_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            finally:
                self._release_conn(conn, close=False)
            return True
        except Exception as e:
            logger.error("DB health check 실패: %s", e)
            return False

    def close(self) -> None:
        try:
            self._pool.closeall()
        except Exception as e:
            logger.warning("DB 풀 종료 중 오류: %s", e)
