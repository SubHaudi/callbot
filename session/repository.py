"""callbot.session.repository — 콜봇 DB 저장소"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Optional

from callbot.session.models import ConversationSession, ConversationTurn

logger = logging.getLogger(__name__)

RETRY_DELAYS = [0.1, 0.2, 0.4]  # 100ms, 200ms, 400ms
MAX_RETRIES = 3


class DBConnectionBase(ABC):
    """PostgreSQL 연결 추상 인터페이스."""

    @abstractmethod
    def execute(self, query: str, params: tuple = ()) -> None:
        """쿼리 실행."""
        ...

    @abstractmethod
    def fetchone(self, query: str, params: tuple = ()) -> Optional[dict]:
        """단일 행 조회."""
        ...

    @abstractmethod
    def fetchall(self, query: str, params: tuple = ()) -> list:
        """다중 행 조회."""
        ...


class InMemoryDBConnection(DBConnectionBase):
    """테스트용 인메모리 DB 연결 구현.

    query 문자열 prefix로 동작을 구분한다:
    - "INSERT_SESSION": params = (ConversationSession,)
    - "UPDATE_SESSION": params = (session_id, updates_dict)
    - "INSERT_TURN":    params = (ConversationTurn,)
    - "SELECT_SESSION": params = (session_id,)
    - "SELECT_TURNS":   params = (session_id,)
    """

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationSession] = {}
        self._turns: dict[str, list[ConversationTurn]] = {}
        self.fail_next_n: int = 0  # 다음 N번 execute() 호출을 실패시킴

    def execute(self, query: str, params: tuple = ()) -> None:
        if self.fail_next_n > 0:
            self.fail_next_n -= 1
            raise RuntimeError("Simulated DB failure")

        q = query.strip().upper()
        if q.startswith("INSERT_SESSION"):
            session: ConversationSession = params[0]
            self._sessions[session.session_id] = session
        elif q.startswith("UPDATE_SESSION"):
            session_id: str = params[0]
            updates: dict = params[1]
            if session_id in self._sessions:
                stored = self._sessions[session_id]
                for key, value in updates.items():
                    if hasattr(stored, key):
                        object.__setattr__(stored, key, value)
        elif q.startswith("INSERT_TURN"):
            turn: ConversationTurn = params[0]
            sid = turn.session_id
            if sid not in self._turns:
                self._turns[sid] = []
            self._turns[sid].append(turn)
            # M-18: turn_count 갱신
            if sid in self._sessions:
                session = self._sessions[sid]
                session.total_turn_count = getattr(session, "total_turn_count", 0) + 1

    def fetchone(self, query: str, params: tuple = ()) -> Optional[object]:
        q = query.strip().upper()
        if q.startswith("SELECT_SESSION"):
            session_id: str = params[0]
            return self._sessions.get(session_id)
        return None

    def fetchall(self, query: str, params: tuple = ()) -> list:
        q = query.strip().upper()
        if q.startswith("SELECT_TURNS"):
            session_id: str = params[0]
            return self._turns.get(session_id, [])
        return []


class DBOperationError(Exception):
    """DB 작업 최대 재시도 후 실패 시 발생."""
    pass


class SessionFKError(Exception):
    """FK 제약 위반: 존재하지 않는 session_id로 turn INSERT 시도."""
    pass


class CallbotDBRepository:
    """콜봇 DB 저장소.

    PostgreSQL 기반 영속 저장 계층. ConversationSession, ConversationTurn 등
    대화 데이터를 저장하고 조회한다.

    Args:
        db: DB 연결 구현체
        retry_delays: 재시도 대기 시간 목록 (테스트 시 [0,0,0]으로 설정 가능)
    """

    def __init__(
        self,
        db: DBConnectionBase,
        retry_delays: list[float] | None = None,
    ) -> None:
        self._db = db
        self._retry_delays = retry_delays if retry_delays is not None else RETRY_DELAYS

    def _execute_with_retry(self, query: str, params: tuple = ()) -> None:
        """최대 3회 재시도 (지수 백오프)."""
        last_error: Exception | None = None
        for attempt, delay in enumerate(self._retry_delays):
            try:
                self._db.execute(query, params)
                return
            except Exception as e:
                last_error = e
                logger.warning("DB execute 실패 (attempt %d): %s", attempt + 1, e)
                if attempt < len(self._retry_delays) - 1:
                    time.sleep(delay)
        raise DBOperationError(
            f"DB 작업 {len(self._retry_delays)}회 모두 실패"
        ) from last_error

    def insert_session(self, session: ConversationSession) -> None:
        """세션 레코드 INSERT (세션 생성 시)."""
        self._execute_with_retry("INSERT_SESSION", (session,))

    def update_session(self, session_id: str, updates: dict) -> None:
        """세션 레코드 UPDATE (세션 종료 시 end_time, end_reason, csat_score 등)."""
        self._execute_with_retry("UPDATE_SESSION", (session_id, updates))

    def insert_turn(self, turn: ConversationTurn) -> None:
        """턴 레코드 INSERT (각 턴 완료 시 실시간 저장, RPO 1분 보장).

        Also increments turn_count on the session (M-18: FR-011).

        Raises:
            SessionFKError: 해당 session_id의 세션이 존재하지 않을 때
        """
        existing = self._db.fetchone("SELECT_SESSION", (turn.session_id,))
        if existing is None:
            raise SessionFKError(
                f"FK 제약 위반: session_id '{turn.session_id}'가 존재하지 않습니다"
            )
        self._execute_with_retry("INSERT_TURN", (turn,))

    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """세션 조회."""
        return self._db.fetchone("SELECT_SESSION", (session_id,))

    def get_turns(self, session_id: str) -> list[ConversationTurn]:
        """세션의 모든 턴 조회."""
        return self._db.fetchall("SELECT_TURNS", (session_id,))
