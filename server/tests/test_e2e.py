"""E2E Integration Test — 실제 PG + Redis, Bedrock mock."""
from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock, patch
from httpx import ASGITransport, AsyncClient


E2E_DATABASE_URL = os.environ.get("E2E_DATABASE_URL", "postgresql://callbot:localdev@localhost:5432/callbot")
E2E_REDIS_HOST = os.environ.get("E2E_REDIS_HOST", "localhost")
E2E_REDIS_PORT = os.environ.get("E2E_REDIS_PORT", "6380")

skip_no_e2e = pytest.mark.skipif(
    os.environ.get("RUN_E2E") != "1",
    reason="E2E disabled (set RUN_E2E=1)"
)


@pytest.fixture
def _e2e_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", E2E_DATABASE_URL)
    monkeypatch.setenv("REDIS_HOST", E2E_REDIS_HOST)
    monkeypatch.setenv("REDIS_PORT", E2E_REDIS_PORT)
    monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
    monkeypatch.setenv("BEDROCK_REGION", "ap-northeast-2")


@skip_no_e2e
@pytest.mark.asyncio
@pytest.mark.usefixtures("_e2e_env")
async def test_app_starts_with_real_pg_redis():
    """앱이 실제 PG+Redis로 시작되는지 확인."""
    mock_bedrock = MagicMock()
    mock_bedrock.generate.return_value = "mock response"

    with patch("server.app._init_bedrock", return_value=mock_bedrock):
        from server.app import create_app
        app = create_app()
        async with app.router.lifespan_context(app):
            # PG/Redis 연결 성공 → healthy
            assert app.state.healthy is True
            assert app.state.pg_connection is not None


@skip_no_e2e
@pytest.mark.asyncio
@pytest.mark.usefixtures("_e2e_env")
async def test_health_endpoint_e2e():
    """GET /health/live → 200."""
    mock_bedrock = MagicMock()

    with patch("server.app._init_bedrock", return_value=mock_bedrock):
        from server.app import create_app
        app = create_app()
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/health/live")
            assert resp.status_code == 200


@skip_no_e2e
@pytest.mark.asyncio
@pytest.mark.usefixtures("_e2e_env")
async def test_turn_endpoint_e2e():
    """POST /api/v1/turn — 실제 PG/Redis + Bedrock mock."""
    mock_bedrock = MagicMock()
    mock_bedrock.generate.return_value = "테스트 응답입니다."

    with patch("server.app._init_bedrock", return_value=mock_bedrock):
        from server.app import create_app
        app = create_app()
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/v1/turn", json={
                    "caller_id": "01012345678",
                    "text": "요금 조회해주세요",
                })
                print(f"Status: {resp.status_code}")
                print(f"Body: {resp.text}")
                # 200이면 풀 파이프라인 성공, 500이면 통합 버그 발견
                assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


@skip_no_e2e
@pytest.mark.asyncio
@pytest.mark.usefixtures("_e2e_env")
async def test_turn_invalid_body_e2e():
    """POST /api/v1/turn 잘못된 body → 422."""
    mock_bedrock = MagicMock()

    with patch("server.app._init_bedrock", return_value=mock_bedrock):
        from server.app import create_app
        app = create_app()
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/v1/turn", json={"bad": "data"})
                assert resp.status_code == 422
