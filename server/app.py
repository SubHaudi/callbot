"""callbot.server.app — FastAPI 앱 팩토리"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from callbot.health.router import configure_health_dependencies, router as health_router
from server.config import ServerConfig
from server.routes import router as api_router
from server.admin_routes import router as admin_router
from callbot.session.exceptions import SessionNotFoundError

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def _init_pg(config: ServerConfig) -> Any:
    """PostgreSQL 커넥션 풀 생성."""
    from callbot.session.pg_connection import PostgreSQLConnection
    return PostgreSQLConnection(dsn=config.database_url)


def _ensure_schema(pg_conn: Any) -> None:
    """필요한 테이블이 없으면 생성한다."""
    conn = pg_conn._acquire_conn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversation_sessions (
                    session_id TEXT PRIMARY KEY,
                    caller_id TEXT,
                    customer_id TEXT,
                    start_time TIMESTAMPTZ,
                    end_time TIMESTAMPTZ,
                    end_reason TEXT,
                    is_authenticated BOOLEAN DEFAULT FALSE,
                    auth_method TEXT,
                    business_turn_count INTEGER DEFAULT 0,
                    total_turn_count INTEGER DEFAULT 0,
                    tts_speed_factor FLOAT DEFAULT 1.0,
                    csat_score INTEGER,
                    escalation_reason TEXT,
                    escalation_reasons JSONB DEFAULT '[]',
                    auth_attempts JSONB DEFAULT '[]',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    expires_at TIMESTAMPTZ
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT REFERENCES conversation_sessions(session_id),
                    turn_number INTEGER,
                    user_text TEXT,
                    bot_text TEXT,
                    intent TEXT,
                    action_type TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            # Phase J: 통화 기록 + 분석 컬럼 확장
            for stmt in [
                "ALTER TABLE conversation_sessions ADD COLUMN IF NOT EXISTS resolution TEXT DEFAULT 'unknown'",
                "ALTER TABLE conversation_sessions ADD COLUMN IF NOT EXISTS call_summary TEXT",
                "ALTER TABLE conversation_sessions ADD COLUMN IF NOT EXISTS primary_intent TEXT",
                "ALTER TABLE conversation_sessions ADD COLUMN IF NOT EXISTS summary_generated_at TIMESTAMPTZ",
                "CREATE INDEX IF NOT EXISTS idx_sessions_start_time ON conversation_sessions(start_time DESC)",
                "CREATE INDEX IF NOT EXISTS idx_sessions_resolution ON conversation_sessions(resolution)",
                "CREATE INDEX IF NOT EXISTS idx_sessions_caller_id ON conversation_sessions(caller_id)",
            ]:
                cur.execute(stmt)
        logger.info("DB 스키마 확인 완료")
    finally:
        pg_conn._release_conn(conn, close=False)


def _init_redis(config: ServerConfig) -> Any:
    """Redis SessionStore 생성."""
    import redis as redis_lib
    from callbot.session.redis_session_store import RedisSessionStore
    # ElastiCache Serverless requires TLS
    use_ssl = config.environment != "local"
    client = redis_lib.Redis(
        host=config.redis_host,
        port=config.redis_port,
        decode_responses=True,
        ssl=use_ssl,
        ssl_cert_reqs=None,
        socket_connect_timeout=5,
    )
    # 연결 확인
    try:
        client.ping()
        logger.info("Redis 연결 성공: %s:%s (ssl=%s)", config.redis_host, config.redis_port, use_ssl)
    except Exception as e:
        logger.error("Redis ping 실패: %s", e)
    return RedisSessionStore(redis_client=client)


def _init_bedrock(config: ServerConfig) -> Any:
    """Bedrock 서비스 초기화. CALLBOT_LLM_BACKEND=fake이면 FakeLLM 반환."""
    import os
    if os.getenv("CALLBOT_LLM_BACKEND") == "fake":
        from server.fake_llm import FakeLLMEngine
        logger.info("Bedrock fake 모드 — FakeLLMEngine 사용")
        return FakeLLMEngine()

    from callbot.llm_engine.bedrock_service import BedrockConfig, BedrockClaudeService
    bedrock_config = BedrockConfig(
        model_id=config.bedrock_model_id,
        region=config.bedrock_region,
        timeout_seconds=30,
        max_tokens=16384,
        max_retries=3,
    )
    return BedrockClaudeService(bedrock_config)


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
        _ensure_schema(app.state.pg_connection)
        app.state.redis_store = _init_redis(config)
        app.state.bedrock_service = _init_bedrock(config)

        # CallLogger 초기화
        from server.call_logger import CallLogger
        app.state.call_logger = CallLogger(
            pg_conn=app.state.pg_connection,
            llm_engine=app.state.bedrock_service,
        )
        # Admin API에서 사용할 pg_conn
        app.state.pg_conn = app.state.pg_connection

        configure_health_dependencies(
            pg_provider=lambda: app.state.pg_connection,
            redis_provider=lambda: app.state.redis_store,
        )

        # Pipeline 조립 (bootstrap.py)
        from server.bootstrap import assemble_pipeline, assemble_voice_server, init_stt_engine, init_tts_engine
        app.state.pipeline = assemble_pipeline(
            pg_connection=app.state.pg_connection,
            redis_store=app.state.redis_store,
            bedrock_service=app.state.bedrock_service,
        )

        # VoiceServer 조립 (bootstrap.py) — STT/TTS 없으면 텍스트 전용
        stt_engine = init_stt_engine()
        tts_engine = init_tts_engine()
        app.state.voice_server = assemble_voice_server(
            pipeline=app.state.pipeline,
            stt_engine=stt_engine,
            tts_engine=tts_engine,
        )
        app.state.voice_server.start_background_cleanup()

        # 모든 조립 완료 후 healthy 설정
        app.state.healthy = True
        logger.info("서버 초기화 완료: environment=%s", config.environment)
    except Exception as exc:
        logger.critical("서버 초기화 실패 — 서버 시작 불가: %s", exc)
        raise

    yield

    # Shutdown
    if hasattr(app.state, 'voice_server'):
        app.state.voice_server.stop_background_cleanup()
    if app.state.pg_connection is not None:
        try:
            app.state.pg_connection.close()
        except Exception:
            logger.exception("PG 연결 종료 실패")
    if app.state.redis_store is not None:
        try:
            if hasattr(app.state.redis_store, '_redis'):
                app.state.redis_store._redis.close()
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

    # Voice WebSocket router
    from server.voice_ws import router as voice_router
    app.include_router(voice_router)

    # Admin API router
    app.include_router(admin_router)

    # Demo static files
    import pathlib
    from fastapi.responses import HTMLResponse
    demo_html = pathlib.Path(__file__).resolve().parent.parent / "voice_io" / "demo" / "index.html"

    @app.get("/demo", response_class=HTMLResponse)
    async def demo_page():
        if demo_html.exists():
            return demo_html.read_text(encoding="utf-8")
        return HTMLResponse("<h1>Demo not found</h1>", status_code=404)

    admin_html = pathlib.Path(__file__).parent / "static" / "admin.html"

    @app.get("/admin", response_class=HTMLResponse)
    async def admin_page():
        if admin_html.exists():
            return admin_html.read_text(encoding="utf-8")
        return HTMLResponse("<h1>Admin not found</h1>", status_code=404)

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
