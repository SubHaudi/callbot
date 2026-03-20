"""callbot.server.app — FastAPI 앱 팩토리"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from health.router import configure_health_dependencies, router as health_router
from server.config import ServerConfig
from server.routes import router as api_router
from session.exceptions import SessionNotFoundError

logger = logging.getLogger(__name__)


def _init_pg(config: ServerConfig) -> Any:
    """PostgreSQL 커넥션 풀 생성."""
    from session.pg_connection import PostgreSQLConnection
    return PostgreSQLConnection(dsn=config.database_url)


def _init_redis(config: ServerConfig) -> Any:
    """Redis 클라이언트 생성."""
    import redis
    return redis.Redis(host=config.redis_host, port=config.redis_port, decode_responses=True)


def _init_bedrock(config: ServerConfig) -> Any:
    """Bedrock 서비스 초기화."""
    from llm_engine.bedrock_service import BedrockConfig, BedrockService
    bedrock_config = BedrockConfig(
        model_id=config.bedrock_model_id,
        region=config.bedrock_region,
        timeout_seconds=30,
        max_tokens=16384,
        max_retries=3,
    )
    return BedrockService(bedrock_config)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """앱 라이프사이클: startup → yield → shutdown."""
    app.state.healthy = False
    app.state.pg_connection = None
    app.state.redis_store = None
    app.state.bedrock_service = None

    try:
        config = ServerConfig.from_env()
        app.state.pg_connection = _init_pg(config)
        app.state.redis_store = _init_redis(config)
        app.state.bedrock_service = _init_bedrock(config)

        configure_health_dependencies(
            pg_provider=lambda: app.state.pg_connection,
            redis_provider=lambda: app.state.redis_store,
        )
        app.state.healthy = True
        logger.info("서버 초기화 완료: environment=%s", config.environment)
    except Exception:
        logger.exception("서버 초기화 실패 — graceful degradation 모드")

    yield

    # Shutdown
    if app.state.pg_connection is not None:
        try:
            app.state.pg_connection.close()
        except Exception:
            logger.exception("PG 연결 종료 실패")
    if app.state.redis_store is not None:
        try:
            app.state.redis_store.close()
        except Exception:
            logger.exception("Redis 연결 종료 실패")


def create_app() -> FastAPI:
    """FastAPI 앱을 생성하고 라우터/미들웨어를 등록한다."""
    app = FastAPI(
        title="Callbot API",
        version="0.1.0",
        description="LLM 기반 콜봇 — 전화 상담 자동화",
        lifespan=_lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health router
    app.include_router(health_router)

    # API router
    app.include_router(api_router)

    # Error handlers
    @app.exception_handler(SessionNotFoundError)
    async def _session_not_found(request: Request, exc: SessionNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _value_error(request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.middleware("http")
    async def _catch_all_errors(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:
            logger.exception("Unhandled error")
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )

    return app


app = create_app()
