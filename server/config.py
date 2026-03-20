"""callbot.server.config — 환경변수 기반 서버 설정"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ServerConfig:
    """서버 설정. 환경변수에서 로드."""

    database_url: str
    redis_host: str
    bedrock_model_id: str
    redis_port: int = 6379
    bedrock_region: str = "ap-northeast-2"
    environment: str = "dev"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> ServerConfig:
        """환경변수에서 설정을 읽는다. 필수 변수 누락 시 ValueError."""
        # DATABASE_URL이 JSON이면 (Secrets Manager) DSN으로 변환
        database_url = cls._resolve_database_url()

        redis_host = os.environ.get("REDIS_HOST")
        bedrock_model_id = os.environ.get("BEDROCK_MODEL_ID")

        missing = []
        if not database_url:
            missing.append("DATABASE_URL (or DB_HOST+DB_SECRET)")
        if not redis_host:
            missing.append("REDIS_HOST")
        if not bedrock_model_id:
            missing.append("BEDROCK_MODEL_ID")
        if missing:
            raise ValueError(f"필수 환경변수 누락: {', '.join(missing)}")

        return cls(
            database_url=database_url,
            redis_host=redis_host,
            bedrock_model_id=bedrock_model_id,
            redis_port=int(os.environ.get("REDIS_PORT", "6379")),
            bedrock_region=os.environ.get("BEDROCK_REGION", "ap-northeast-2"),
            environment=os.environ.get("ENVIRONMENT", "dev"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )

    @staticmethod
    def _resolve_database_url() -> str:
        """DATABASE_URL을 해석한다.

        - 일반 DSN (postgresql://...) → 그대로
        - JSON ({"username":..., "password":...}) → DB_HOST, DB_PORT, DB_NAME과 조합
        - 개별 환경변수 (DB_HOST, DB_USER, DB_PASSWORD) → DSN 조합
        """
        raw = os.environ.get("DATABASE_URL", "")

        # 이미 DSN 형태
        if raw.startswith("postgresql://"):
            return raw

        # JSON (Secrets Manager에서 주입)
        if raw.startswith("{"):
            try:
                creds = json.loads(raw)
                username = creds["username"]
                password = creds["password"]
                host = os.environ.get("DB_HOST", "localhost")
                port = os.environ.get("DB_PORT", "5432")
                dbname = os.environ.get("DB_NAME", "callbot")
                return f"postgresql://{username}:{password}@{host}:{port}/{dbname}"
            except (json.JSONDecodeError, KeyError):
                return raw

        # 개별 환경변수
        db_host = os.environ.get("DB_HOST")
        db_user = os.environ.get("DB_USER")
        db_password = os.environ.get("DB_PASSWORD", "")
        if db_host and db_user:
            port = os.environ.get("DB_PORT", "5432")
            dbname = os.environ.get("DB_NAME", "callbot")
            return f"postgresql://{db_user}:{db_password}@{db_host}:{port}/{dbname}"

        return raw
