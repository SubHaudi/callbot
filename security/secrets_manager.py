"""AWS Secrets Manager 연동 및 환경변수 폴백을 지원하는 시크릿 관리 모듈."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import boto3

from callbot.security.exceptions import SecretNotFoundError


@dataclass
class _CacheEntry:
    """캐시된 시크릿 값과 만료 시각."""

    value: str
    expires_at: float  # time.monotonic() 기준


class SecretsManager:
    """시크릿 조회 및 캐싱을 담당하는 매니저.

    backend="aws" → AWS Secrets Manager API 사용
    backend="env" → 환경변수에서 조회 (로컬 개발용)
    """

    def __init__(
        self,
        backend: str = "aws",
        cache_ttl_seconds: int = 300,
        client=None,
    ) -> None:
        self._backend = backend
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, _CacheEntry] = {}

        if self._backend == "aws":
            self._client = client or boto3.client("secretsmanager")
        else:
            self._client = None

    @classmethod
    def from_env(cls) -> SecretsManager:
        """환경변수에서 설정을 읽어 인스턴스를 생성한다.

        - CALLBOT_SECRET_BACKEND: "aws" (기본) 또는 "env"
        - CALLBOT_SECRET_CACHE_TTL_SECONDS: 캐시 TTL (기본 300초)
        """
        backend = os.environ.get("CALLBOT_SECRET_BACKEND", "aws")
        ttl = int(os.environ.get("CALLBOT_SECRET_CACHE_TTL_SECONDS", "300"))
        return cls(backend=backend, cache_ttl_seconds=ttl)

    def get_secret(self, secret_name: str) -> str:
        """시크릿을 조회한다. 캐시 히트 시 외부 호출 없이 반환.

        Raises:
            SecretNotFoundError: 시크릿 조회 실패 시
        """
        entry = self._cache.get(secret_name)
        if entry is not None and time.monotonic() < entry.expires_at:
            return entry.value

        value = self._fetch(secret_name)
        self._cache[secret_name] = _CacheEntry(
            value=value,
            expires_at=time.monotonic() + self._cache_ttl_seconds,
        )
        return value

    def refresh(self, secret_name: str) -> str:
        """캐시를 무효화하고 시크릿을 재조회한다.

        Raises:
            SecretNotFoundError: 시크릿 조회 실패 시
        """
        self._cache.pop(secret_name, None)
        value = self._fetch(secret_name)
        self._cache[secret_name] = _CacheEntry(
            value=value,
            expires_at=time.monotonic() + self._cache_ttl_seconds,
        )
        return value

    def _fetch(self, secret_name: str) -> str:
        """백엔드에 따라 시크릿을 조회한다."""
        if self._backend == "aws":
            return self._fetch_aws(secret_name)
        return self._fetch_env(secret_name)

    def _fetch_aws(self, secret_name: str) -> str:
        """AWS Secrets Manager에서 시크릿을 조회한다."""
        try:
            response = self._client.get_secret_value(SecretId=secret_name)
            return response["SecretString"]
        except Exception as exc:
            raise SecretNotFoundError(
                f"Failed to retrieve secret '{secret_name}' from AWS: {exc}"
            ) from exc

    def _fetch_env(self, secret_name: str) -> str:
        """환경변수에서 시크릿을 조회한다.

        secret_name을 대문자로 변환하고 '.'을 '_'로 치환한다.
        예: "callbot/jwt-signing-key" → "CALLBOT/JWT-SIGNING-KEY" → 실제로는
            "CALLBOT/JWT-SIGNING-KEY".upper().replace(".", "_")
        """
        env_key = secret_name.upper().replace(".", "_").replace("/", "_").replace("-", "_")
        value = os.environ.get(env_key)
        if value is None:
            raise SecretNotFoundError(
                f"Environment variable '{env_key}' not found "
                f"(secret_name='{secret_name}')"
            )
        return value
