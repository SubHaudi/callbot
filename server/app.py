"""callbot.server.app — FastAPI 앱 팩토리"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from health.router import router as health_router


def create_app() -> FastAPI:
    """FastAPI 앱을 생성하고 라우터/미들웨어를 등록한다."""
    app = FastAPI(
        title="Callbot API",
        version="0.1.0",
        description="LLM 기반 콜봇 — 전화 상담 자동화",
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

    return app


app = create_app()
