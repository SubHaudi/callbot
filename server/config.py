"""callbot.server.config — 환경변수 기반 서버 설정"""
from __future__ import annotations

import os
from dataclasses import dataclass


_REQUIRED_VARS = ("DATABASE_URL", "REDIS_HOST", "BEDROCK_MODEL_ID")


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
        missing = [v for v in _REQUIRED_VARS if not os.environ.get(v)]
        if missing:
            raise ValueError(f"필수 환경변수 누락: {', '.join(missing)}")

        return cls(
            database_url=os.environ["DATABASE_URL"],
            redis_host=os.environ["REDIS_HOST"],
            bedrock_model_id=os.environ["BEDROCK_MODEL_ID"],
            redis_port=int(os.environ.get("REDIS_PORT", "6379")),
            bedrock_region=os.environ.get("BEDROCK_REGION", "ap-northeast-2"),
            environment=os.environ.get("ENVIRONMENT", "dev"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
