"""server.tests.test_wiring — 컴포넌트 조립 검증 (mock 최소화).

bootstrap.py의 조립 함수를 실제 컴포넌트로 테스트.
DB만 mock, 나머지는 실제 객체.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import MagicMock

from server.bootstrap import assemble_pipeline


class TestLifespanFailFast:
    """_lifespan이 필수 의존성 실패 시 예외를 전파하는지 검증."""

    @pytest.mark.asyncio
    async def test_lifespan_raises_on_db_failure(self):
        """DB 초기화 실패 시 _lifespan이 예외를 삼키지 않고 전파."""
        import os
        from unittest.mock import patch
        from server.app import create_app

        env = {
            "DATABASE_URL": "postgresql://fake:fake@localhost:5432/fake",
            "REDIS_HOST": "localhost",
            "BEDROCK_MODEL_ID": "fake-model",
            "BEDROCK_REGION": "us-east-1",
        }
        with patch.dict(os.environ, env):
            app = create_app()
            with patch("server.app._init_pg", side_effect=RuntimeError("DB connection failed")):
                with pytest.raises(RuntimeError, match="DB connection failed"):
                    async with app.router.lifespan_context(app):
                        pass  # should not reach here


class TestAssemblePipeline:
    """assemble_pipeline 조립 검증."""

    def test_raises_when_pg_is_none(self):
        """DB 없으면 명시적 RuntimeError."""
        with pytest.raises(RuntimeError, match="PostgreSQL"):
            assemble_pipeline(
                pg_connection=None,
                redis_store=None,
                bedrock_service=MagicMock(),
            )

    def test_assembles_with_mock_db(self):
        """mock DB로 Pipeline 조립 성공 — 내부 컴포넌트가 실제 객체."""
        mock_pg = MagicMock()
        mock_llm = MagicMock()

        pipeline = assemble_pipeline(
            pg_connection=mock_pg,
            redis_store=None,
            bedrock_service=mock_llm,
        )

        assert pipeline is not None
        assert callable(pipeline.process)
        # 내부 컴포넌트가 실제 객체인지 확인
        assert pipeline._pif is not None
        assert pipeline._orchestrator is not None
        assert pipeline._session_manager is not None

    def test_pipeline_process_is_async(self):
        """조립된 Pipeline.process()가 async 함수."""
        mock_pg = MagicMock()
        mock_llm = MagicMock()

        pipeline = assemble_pipeline(
            pg_connection=mock_pg,
            redis_store=None,
            bedrock_service=mock_llm,
        )

        assert asyncio.iscoroutinefunction(pipeline.process)
