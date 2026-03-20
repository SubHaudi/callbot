"""server.routes 테스트 — REST API"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import ASGITransport, AsyncClient


def _make_app_with_pipeline(pipeline_mock):
    """파이프라인 mock이 주입된 앱 생성."""
    from server.app import create_app
    app = create_app()
    # lifespan 없이 테스트 — state 직접 설정
    app.state.healthy = True
    app.state.pipeline = pipeline_mock
    return app


def _make_unhealthy_app():
    """unhealthy 앱."""
    from server.app import create_app
    app = create_app()
    app.state.healthy = False
    app.state.pipeline = None
    return app


@pytest.mark.asyncio
async def test_turn_endpoint_returns_response():
    """POST /api/v1/turn → 200 + TurnResponse."""
    from server.pipeline import TurnResult

    mock_pipeline = AsyncMock()
    mock_pipeline.process.return_value = TurnResult(
        session_id="sess-1",
        response_text="안녕하세요",
        action_type="PROCESS_BUSINESS",
        context={},
    )

    app = _make_app_with_pipeline(mock_pipeline)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/turn", json={
            "caller_id": "01012345678",
            "text": "요금 조회",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "sess-1"
    assert data["response_text"] == "안녕하세요"
    assert data["action_type"] == "PROCESS_BUSINESS"


@pytest.mark.asyncio
async def test_turn_endpoint_creates_session():
    """session_id 없이 요청 → 응답에 session_id 포함."""
    from server.pipeline import TurnResult

    mock_pipeline = AsyncMock()
    mock_pipeline.process.return_value = TurnResult(
        session_id="new-sess",
        response_text="응답",
        action_type="PROCESS_BUSINESS",
        context={},
    )

    app = _make_app_with_pipeline(mock_pipeline)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/turn", json={
            "caller_id": "010",
            "text": "hello",
        })
    assert resp.status_code == 200
    assert resp.json()["session_id"] == "new-sess"
    mock_pipeline.process.assert_called_once_with(
        session_id=None, caller_id="010", text="hello"
    )


@pytest.mark.asyncio
async def test_turn_endpoint_invalid_body():
    """text 누락 → 422."""
    mock_pipeline = AsyncMock()
    app = _make_app_with_pipeline(mock_pipeline)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/turn", json={"caller_id": "010"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_turn_endpoint_when_unhealthy():
    """의존성 미초기화 → 503."""
    app = _make_unhealthy_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/turn", json={
            "caller_id": "010",
            "text": "hello",
        })
    assert resp.status_code == 503
