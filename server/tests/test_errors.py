"""server 에러 핸들링 테스트"""
from __future__ import annotations

from unittest.mock import AsyncMock
import pytest
from httpx import ASGITransport, AsyncClient

from session.exceptions import SessionNotFoundError


def _make_app_with_error(error):
    """파이프라인이 특정 에러를 던지는 앱."""
    from server.app import create_app
    mock_pipeline = AsyncMock()
    mock_pipeline.process.side_effect = error
    app = create_app()
    app.state.healthy = True
    app.state.pipeline = mock_pipeline
    return app


@pytest.mark.asyncio
async def test_session_not_found_returns_404():
    """SessionNotFoundError → 404."""
    app = _make_app_with_error(SessionNotFoundError("sess-999"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/turn", json={"caller_id": "010", "text": "hi"})
    assert resp.status_code == 404
    assert "sess-999" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_unexpected_error_returns_500_without_details():
    """RuntimeError → 500 + generic message."""
    app = _make_app_with_error(RuntimeError("DB connection string leaked"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/turn", json={"caller_id": "010", "text": "hi"})
    assert resp.status_code == 500
    data = resp.json()
    assert "Internal server error" in data["detail"]
    assert "DB connection" not in data["detail"]


@pytest.mark.asyncio
async def test_value_error_returns_400():
    """ValueError → 400."""
    app = _make_app_with_error(ValueError("invalid caller_id"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/turn", json={"caller_id": "010", "text": "hi"})
    assert resp.status_code == 400
