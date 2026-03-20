"""server.config 테스트 — 환경변수 기반 설정"""
from __future__ import annotations

import os
import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """테스트 간 환경변수 격리."""
    for key in [
        "DATABASE_URL", "REDIS_HOST", "REDIS_PORT",
        "BEDROCK_MODEL_ID", "BEDROCK_REGION",
        "ENVIRONMENT", "LOG_LEVEL",
    ]:
        monkeypatch.delenv(key, raising=False)


def _set_required(monkeypatch):
    """필수 환경변수를 설정한다."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@localhost:5432/callbot")
    monkeypatch.setenv("REDIS_HOST", "localhost")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-haiku-20241022-v1:0")


def test_config_reads_required_env_vars(monkeypatch):
    """필수 환경변수가 설정되면 정상 로드된다."""
    _set_required(monkeypatch)

    from server.config import ServerConfig
    cfg = ServerConfig.from_env()

    assert cfg.database_url == "postgresql://user:pw@localhost:5432/callbot"
    assert cfg.redis_host == "localhost"
    assert cfg.bedrock_model_id == "anthropic.claude-3-5-haiku-20241022-v1:0"


def test_config_fails_on_missing_database_url(monkeypatch):
    """DATABASE_URL 누락 시 ValueError."""
    monkeypatch.setenv("REDIS_HOST", "localhost")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "some-model")

    from server.config import ServerConfig
    with pytest.raises(ValueError, match="DATABASE_URL"):
        ServerConfig.from_env()


def test_config_fails_on_missing_redis_host(monkeypatch):
    """REDIS_HOST 누락 시 ValueError."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/db")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "some-model")

    from server.config import ServerConfig
    with pytest.raises(ValueError, match="REDIS_HOST"):
        ServerConfig.from_env()


def test_config_fails_on_missing_bedrock_model_id(monkeypatch):
    """BEDROCK_MODEL_ID 누락 시 ValueError."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/db")
    monkeypatch.setenv("REDIS_HOST", "localhost")

    from server.config import ServerConfig
    with pytest.raises(ValueError, match="BEDROCK_MODEL_ID"):
        ServerConfig.from_env()


def test_config_uses_defaults_for_optional_vars(monkeypatch):
    """선택 변수는 기본값 적용."""
    _set_required(monkeypatch)

    from server.config import ServerConfig
    cfg = ServerConfig.from_env()

    assert cfg.redis_port == 6379
    assert cfg.bedrock_region == "ap-northeast-2"
    assert cfg.environment == "dev"
    assert cfg.log_level == "INFO"
