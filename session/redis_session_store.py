"""callbot.session.redis_session_store — Redis 기반 세션 저장소"""
from __future__ import annotations

import logging
import os
from typing import Optional

from callbot.session import session_serializer
from callbot.session.exceptions import RedisConnectionError
from callbot.session.models import SessionContext
from callbot.session.session_store import SessionStoreBase

logger = logging.getLogger(__name__)


class RedisSessionStore(SessionStoreBase):
    """Redis 기반 세션 저장소.

    SessionContext를 JSON 직렬화하여 Redis에 저장한다.
    키 형식: callbot:session:{session_id}
    TTL: 기본 1200초 (20분)
    """

    KEY_PREFIX = "callbot:session:"
    DEFAULT_TTL = 1200  # 20분

    def __init__(
        self,
        redis_client,
        ttl_seconds: int = DEFAULT_TTL,
    ) -> None:
        self._redis = redis_client
        self._ttl = ttl_seconds

    @classmethod
    def from_env(cls) -> "RedisSessionStore":
        """환경변수에서 RedisConfig를 로드하여 인스턴스 생성.

        CALLBOT_SESSION_TTL_SECONDS 환경변수로 TTL 오버라이드 가능.
        """
        import redis

        from callbot.session.redis_config import RedisConfig

        cfg = RedisConfig.from_env()
        client = redis.Redis(
            host=cfg.host,
            port=cfg.port,
            db=cfg.db,
            password=cfg.password,
            ssl=cfg.ssl,
        )
        ttl = int(os.environ.get("CALLBOT_SESSION_TTL_SECONDS", str(cls.DEFAULT_TTL)))
        return cls(redis_client=client, ttl_seconds=ttl)

    def _key(self, session_id: str) -> str:
        return f"{self.KEY_PREFIX}{session_id}"

    def save(self, context: SessionContext) -> None:
        """SET callbot:session:{id} json EX ttl."""
        try:
            data = session_serializer.serialize(context)
            self._redis.set(self._key(context.session_id), data, ex=self._ttl)
        except RedisConnectionError:
            raise
        except Exception as exc:
            raise RedisConnectionError(f"Redis SET failed: {exc}") from exc

    def load(self, session_id: str) -> Optional[SessionContext]:
        """GET callbot:session:{id} → deserialize."""
        try:
            data = self._redis.get(self._key(session_id))
        except Exception as exc:
            raise RedisConnectionError(f"Redis GET failed: {exc}") from exc
        if data is None:
            return None
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return session_serializer.deserialize(data)

    def delete(self, session_id: str) -> None:
        """DEL callbot:session:{id}."""
        try:
            self._redis.delete(self._key(session_id))
        except Exception as exc:
            raise RedisConnectionError(f"Redis DEL failed: {exc}") from exc

    def exists(self, session_id: str) -> bool:
        """EXISTS callbot:session:{id}."""
        try:
            return bool(self._redis.exists(self._key(session_id)))
        except Exception as exc:
            raise RedisConnectionError(f"Redis EXISTS failed: {exc}") from exc

    def count(self) -> int:
        """활성 세션 수 (키 패턴 매칭)."""
        try:
            keys = self._redis.keys(f"{self._prefix}:*")
            return len(keys)
        except Exception:
            return 0

    def health_check(self) -> bool:
        """PING → True/False. 예외 발생 시 False 반환."""
        try:
            return bool(self._redis.ping())
        except Exception:
            return False
