"""server.app lifespan 테스트 — Startup/Shutdown"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest


@pytest.fixture
def _env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("REDIS_HOST", "localhost")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")


@pytest.mark.asyncio
@pytest.mark.usefixtures("_env")
async def test_startup_sets_healthy_state():
    """startup 성공 시 app.state.healthy = True."""
    mock_pg = MagicMock()
    mock_redis = MagicMock()
    mock_bedrock = MagicMock()

    with patch("server.app._init_pg", return_value=mock_pg), \
         patch("server.app._init_redis", return_value=mock_redis), \
         patch("server.app._init_bedrock", return_value=mock_bedrock):

        from server.app import create_app
        app = create_app()
        async with app.router.lifespan_context(app):
            assert app.state.healthy is True
            assert app.state.pg_connection is mock_pg


@pytest.mark.asyncio
@pytest.mark.usefixtures("_env")
async def test_startup_failure_raises_and_prevents_boot():
    """DB 연결 실패 시 fail-fast — 서버 부팅 중단 (예외 전파)."""
    with patch("server.app._init_pg", side_effect=Exception("refused")), \
         patch("server.app._init_redis", return_value=MagicMock()), \
         patch("server.app._init_bedrock", return_value=MagicMock()):

        from server.app import create_app
        app = create_app()
        with pytest.raises(Exception, match="refused"):
            async with app.router.lifespan_context(app):
                pass  # should not reach here


@pytest.mark.asyncio
@pytest.mark.usefixtures("_env")
async def test_shutdown_closes_pg():
    """shutdown 시 PG 풀이 close된다."""
    mock_pg = MagicMock()
    with patch("server.app._init_pg", return_value=mock_pg), \
         patch("server.app._init_redis", return_value=MagicMock()), \
         patch("server.app._init_bedrock", return_value=MagicMock()):

        from server.app import create_app
        app = create_app()
        async with app.router.lifespan_context(app):
            pass
    mock_pg.close.assert_called_once()
