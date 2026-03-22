"""server.tests.test_wiring — 컴포넌트 조립 검증 (mock 최소화).

bootstrap.py의 assemble_pipeline을 실제 컴포넌트로 테스트.
DB만 mock (InMemory), 나머지는 실제 객체.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import MagicMock

from server.bootstrap import assemble_pipeline, assemble_voice_server


class TestAssemblePipeline:
    def test_raises_when_pg_is_none(self):
        """DB 없으면 명시적 RuntimeError."""
        with pytest.raises(RuntimeError, match="PostgreSQL"):
            assemble_pipeline(
                pg_connection=None,
                redis_store=None,
                bedrock_service=MagicMock(),
            )

    def test_assembles_with_mock_db(self):
        """mock DB로 Pipeline 조립 성공."""
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

    def test_pipeline_process_callable(self):
        """조립된 Pipeline.process()가 호출 가능."""
        mock_pg = MagicMock()
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "테스트 응답"

        pipeline = assemble_pipeline(
            pg_connection=mock_pg,
            redis_store=None,
            bedrock_service=mock_llm,
        )

        # process는 async — 시그니처만 확인
        assert asyncio.iscoroutinefunction(pipeline.process)


class TestAssembleVoiceServer:
    def test_assembles_without_stt_tts(self):
        """STT/TTS 없이 텍스트 전용 VoiceServer 생성."""
        vs = assemble_voice_server(pipeline=MagicMock())
        assert vs is not None
        vs.stop_background_cleanup()

    def test_assembles_with_all_engines(self):
        """Pipeline + STT + TTS 전체 조립."""
        vs = assemble_voice_server(
            pipeline=MagicMock(),
            stt_engine=MagicMock(),
            tts_engine=MagicMock(),
        )
        assert vs is not None
        assert vs._stt is not None
        assert vs._tts is not None
        vs.stop_background_cleanup()

    def test_voice_server_can_create_session(self):
        """조립된 VoiceServer로 세션 생성 가능."""
        vs = assemble_voice_server(pipeline=MagicMock())
        session = vs.create_session()
        assert session is not None
        assert session.session_id
        vs.stop_background_cleanup()


class TestRouteDefense:
    """routes.py의 pipeline None 방어 검증."""

    @pytest.mark.asyncio
    async def test_turn_returns_503_when_pipeline_missing(self):
        """Pipeline 미조립 시 503 반환."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from server.routes import router as api_router

        app = FastAPI()
        app.include_router(api_router)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/v1/turn", json={
            "caller_id": "test",
            "text": "요금 조회",
        })
        assert resp.status_code == 503
