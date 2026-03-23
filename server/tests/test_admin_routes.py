"""Admin API 테스트."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient


def _create_test_app():
    """pg_conn mock으로 테스트용 앱 생성."""
    import os
    os.environ.setdefault("CALLBOT_EXTERNAL_BACKEND", "fake")
    os.environ.setdefault("CALLBOT_LLM_BACKEND", "fake")
    os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
    os.environ.setdefault("REDIS_HOST", "localhost")
    os.environ.setdefault("BEDROCK_MODEL_ID", "test")
    os.environ.setdefault("ENVIRONMENT", "local")

    from server.admin_routes import router
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)

    # Mock pg_conn in app.state
    mock_pg = MagicMock()
    app.state.pg_conn = mock_pg
    return app, mock_pg


def _mock_cursor_with_rows(rows, description=None):
    """커서 mock 생성."""
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    cursor.fetchone.return_value = rows[0] if rows else None
    cursor.description = description
    cursor.__enter__ = lambda s: s
    cursor.__exit__ = lambda s, *a: None
    return cursor


class TestListCalls:
    def test_list_calls_returns_200(self):
        app, mock_pg = _create_test_app()
        conn = MagicMock()
        mock_pg._acquire_conn.return_value = conn
        cursor = _mock_cursor_with_rows([])
        # count cursor
        count_cursor = MagicMock()
        count_cursor.fetchone.return_value = (0,)
        count_cursor.__enter__ = lambda s: s
        count_cursor.__exit__ = lambda s, *a: None
        conn.cursor.side_effect = [count_cursor, cursor]
        client = TestClient(app)
        resp = client.get("/api/v1/admin/calls")
        assert resp.status_code == 200
        data = resp.json()
        assert "calls" in data
        assert "total" in data

    def test_list_calls_with_search(self):
        app, mock_pg = _create_test_app()
        conn = MagicMock()
        mock_pg._acquire_conn.return_value = conn
        count_cursor = MagicMock()
        count_cursor.fetchone.return_value = (1,)
        count_cursor.__enter__ = lambda s: s
        count_cursor.__exit__ = lambda s, *a: None
        row_cursor = _mock_cursor_with_rows([
            ("sess1", "010-1234", "2026-03-22T10:00:00", "2026-03-22T10:05:00",
             "resolved", "billing_inquiry", 3, "고객이 요금 조회함")
        ])
        conn.cursor.side_effect = [count_cursor, row_cursor]
        client = TestClient(app)
        resp = client.get("/api/v1/admin/calls?search=010")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1


class TestCallDetail:
    def test_detail_returns_200(self):
        app, mock_pg = _create_test_app()
        conn = MagicMock()
        mock_pg._acquire_conn.return_value = conn
        session_cursor = MagicMock()
        session_cursor.fetchone.return_value = (
            "sess1", "010-1234", "2026-03-22T10:00:00", "2026-03-22T10:05:00",
            "resolved", "billing_inquiry", 3, "고객이 요금 조회함", "normal"
        )
        session_cursor.__enter__ = lambda s: s
        session_cursor.__exit__ = lambda s, *a: None
        turns_cursor = _mock_cursor_with_rows([
            (1, "요금 조회", "현재 요금은 55,000원입니다", "billing_inquiry", "업무_처리", "2026-03-22T10:00:30")
        ])
        conn.cursor.side_effect = [session_cursor, turns_cursor]
        client = TestClient(app)
        resp = client.get("/api/v1/admin/calls/sess1")
        assert resp.status_code == 200
        data = resp.json()
        assert "session" in data
        assert "turns" in data

    def test_detail_404_not_found(self):
        app, mock_pg = _create_test_app()
        conn = MagicMock()
        mock_pg._acquire_conn.return_value = conn
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        cursor.__enter__ = lambda s: s
        cursor.__exit__ = lambda s, *a: None
        conn.cursor.return_value = cursor
        client = TestClient(app)
        resp = client.get("/api/v1/admin/calls/nonexistent")
        assert resp.status_code == 404
