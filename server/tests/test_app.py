"""server.app 테스트 — FastAPI 앱 팩토리"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_create_app_returns_fastapi_instance():
    """create_app()이 FastAPI 인스턴스를 반환한다."""
    from server.app import create_app
    from fastapi import FastAPI

    app = create_app()
    assert isinstance(app, FastAPI)


@pytest.mark.asyncio
async def test_health_live_router_is_mounted():
    """GET /health/live → 200 응답."""
    from server.app import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"


@pytest.mark.asyncio
async def test_cors_middleware_is_added():
    """CORS 미들웨어가 등록되어 있다 (preflight 요청 허용)."""
    from server.app import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.options(
            "/health/live",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers
