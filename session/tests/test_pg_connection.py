"""test_pg_connection.py — PostgreSQLConnection Mock 단위 테스트 + PBT (P1, P2)"""
from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from callbot.session.pg_config import PoolTimeoutError
from callbot.session.pg_connection import PostgreSQLConnection


# ---------------------------------------------------------------------------
# 헬퍼: Mock Pool로 PostgreSQLConnection 인스턴스 생성
# ---------------------------------------------------------------------------

def _make_pg(mock_pool: MagicMock, max_connections: int = 5) -> PostgreSQLConnection:
    """실제 DB 없이 Mock Pool을 주입한 PostgreSQLConnection 생성."""
    with patch("callbot.session.pg_connection.ThreadedConnectionPool", return_value=mock_pool):
        pg = PostgreSQLConnection(
            dsn="postgresql://u:p@localhost/db",
            min_connections=1,
            max_connections=max_connections,
            pool_timeout=1.0,
        )
    return pg


def _mock_pool_with_conn() -> tuple[MagicMock, MagicMock]:
    """SELECT 1을 성공적으로 실행하는 Mock Pool + conn 반환."""
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_pool = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    return mock_pool, mock_conn


# ---------------------------------------------------------------------------
# 단위 테스트
# ---------------------------------------------------------------------------

def test_health_check_returns_true_on_success():
    mock_pool, _ = _mock_pool_with_conn()
    pg = _make_pg(mock_pool)
    assert pg.health_check() is True


def test_health_check_returns_false_on_failure():
    mock_pool = MagicMock()
    mock_pool.getconn.side_effect = Exception("connection refused")
    pg = _make_pg(mock_pool)
    assert pg.health_check() is False


def test_close_calls_closeall():
    mock_pool, _ = _mock_pool_with_conn()
    pg = _make_pg(mock_pool)
    pg.close()
    mock_pool.closeall.assert_called_once()


def test_pool_timeout_raises_error():
    mock_pool, _ = _mock_pool_with_conn()
    pg = _make_pg(mock_pool, max_connections=1)
    # Semaphore를 모두 소진시켜 타임아웃 유발
    pg._semaphore = threading.Semaphore(0)
    pg._pool_timeout = 0.01
    with pytest.raises(PoolTimeoutError):
        pg._acquire_conn()


# ---------------------------------------------------------------------------
# Property 1: 존재하지 않는 키 조회 시 None / 빈 리스트 반환
# ---------------------------------------------------------------------------

def _make_pg_empty_db(max_connections: int = 5) -> PostgreSQLConnection:
    """fetchone → None, fetchall → [] 를 반환하는 Mock DB."""
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchone.return_value = None
    mock_cursor.fetchall.return_value = []

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_pool = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    return _make_pg(mock_pool, max_connections)


@given(session_id=st.text(min_size=1, max_size=64))
@settings(max_examples=100)
def test_fetchone_missing_key_returns_none(session_id: str):
    """Property 1a: 존재하지 않는 session_id로 fetchone → None."""
    pg = _make_pg_empty_db()
    result = pg.fetchone("SELECT_SESSION", (session_id,))
    assert result is None


@given(session_id=st.text(min_size=1, max_size=64))
@settings(max_examples=100)
def test_fetchall_missing_key_returns_empty_list(session_id: str):
    """Property 1b: 존재하지 않는 session_id로 fetchall → []."""
    pg = _make_pg_empty_db()
    result = pg.fetchall("SELECT_TURNS", (session_id,))
    assert result == []


# ---------------------------------------------------------------------------
# Property 2: 쿼리 실행 후 Semaphore 값 복원 (연결 누수 없음)
# ---------------------------------------------------------------------------

@given(session_id=st.text(min_size=1, max_size=64))
@settings(max_examples=100)
def test_semaphore_restored_after_fetchone(session_id: str):
    """Property 2a: fetchone 후 semaphore._value가 복원된다."""
    pg = _make_pg_empty_db()
    before = pg._semaphore._value
    pg.fetchone("SELECT_SESSION", (session_id,))
    assert pg._semaphore._value == before


@given(session_id=st.text(min_size=1, max_size=64))
@settings(max_examples=100)
def test_semaphore_restored_after_fetchall(session_id: str):
    """Property 2b: fetchall 후 semaphore._value가 복원된다."""
    pg = _make_pg_empty_db()
    before = pg._semaphore._value
    pg.fetchall("SELECT_TURNS", (session_id,))
    assert pg._semaphore._value == before


@given(session_id=st.text(min_size=1, max_size=64))
@settings(max_examples=100)
def test_semaphore_restored_after_db_error(session_id: str):
    """Property 2c: DB 오류 발생 시에도 semaphore._value가 복원된다."""
    import psycopg2

    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchone.side_effect = psycopg2.OperationalError("db error")

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_pool = MagicMock()
    mock_pool.getconn.return_value = mock_conn

    pg = _make_pg(mock_pool)
    before = pg._semaphore._value

    with pytest.raises(psycopg2.OperationalError):
        pg.fetchone("SELECT_SESSION", (session_id,))

    assert pg._semaphore._value == before


# ---------------------------------------------------------------------------
# TASK-S05: SQL injection 방지 — 컬럼 화이트리스트
# ---------------------------------------------------------------------------


def test_update_session_rejects_disallowed_column():
    """허용되지 않은 컬럼 → ValueError."""
    from callbot.session.pg_connection import _ALLOWED_SESSION_COLUMNS

    # 화이트리스트 외 컬럼 확인
    assert "session_id" not in _ALLOWED_SESSION_COLUMNS
    assert "end_time" in _ALLOWED_SESSION_COLUMNS


def test_allowed_session_columns_is_frozenset():
    """화이트리스트가 frozenset으로 불변."""
    from callbot.session.pg_connection import _ALLOWED_SESSION_COLUMNS
    assert isinstance(_ALLOWED_SESSION_COLUMNS, frozenset)
