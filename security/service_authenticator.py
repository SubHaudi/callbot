"""JWT 기반 내부 서비스 인증: 발급, 검증, 폐기."""

from __future__ import annotations

import os
import time
import uuid

import jwt

from callbot.security.exceptions import (
    InvalidTokenError,
    RevokedTokenError,
    TokenExpiredError,
)
from callbot.security.secrets_manager import SecretsManager
from callbot.security.token_store import TokenStoreBase


class ServiceAuthenticator:
    """RS256 (비대칭) JWT를 발급·검증·폐기하는 인증 컴포넌트.

    - 발급: private key로 서명
    - 검증: public key로 검증 (서비스가 signing key를 알 필요 없음)
    - 생성자 주입으로 SecretsManager와 TokenStoreBase 구현체를 교체할 수 있다.
    """

    def __init__(
        self,
        secrets_manager: SecretsManager,
        token_store: TokenStoreBase,
        jwt_ttl_seconds: int = 3600,
        private_key_secret_name: str = "callbot/jwt-private-key",
        public_key_secret_name: str = "callbot/jwt-public-key",
        issuer: str = "callbot",
        audience: str = "callbot-services",
    ) -> None:
        self._secrets_manager = secrets_manager
        self._token_store = token_store
        self._jwt_ttl_seconds = jwt_ttl_seconds
        self._private_key_secret_name = private_key_secret_name
        self._public_key_secret_name = public_key_secret_name
        self._issuer = issuer
        self._audience = audience

    @classmethod
    def from_env(
        cls,
        secrets_manager: SecretsManager,
        token_store: TokenStoreBase,
    ) -> ServiceAuthenticator:
        """환경변수에서 설정을 읽어 인스턴스를 생성한다.

        - CALLBOT_JWT_TTL_SECONDS: JWT 유효 기간 (기본 3600초)
        """
        ttl = int(os.environ.get("CALLBOT_JWT_TTL_SECONDS", "3600"))
        return cls(
            secrets_manager=secrets_manager,
            token_store=token_store,
            jwt_ttl_seconds=ttl,
        )

    def _get_private_key(self) -> str:
        """SecretsManager에서 RSA private key를 조회한다."""
        return self._secrets_manager.get_secret(self._private_key_secret_name)

    def _get_public_key(self) -> str:
        """SecretsManager에서 RSA public key를 조회한다."""
        return self._secrets_manager.get_secret(self._public_key_secret_name)

    def issue_token(self, service_identity: str) -> str:
        """RS256 서명 JWT를 발급한다.

        Args:
            service_identity: sub 클레임에 포함할 서비스 식별자.

        Returns:
            인코딩된 JWT 문자열.

        Raises:
            SecretNotFoundError: private key 조회 실패 시
        """
        private_key = self._get_private_key()
        now = int(time.time())
        payload = {
            "sub": service_identity,
            "iat": now,
            "exp": now + self._jwt_ttl_seconds,
            "jti": str(uuid.uuid4()),
            "iss": self._issuer,
            "aud": self._audience,
        }
        return jwt.encode(payload, private_key, algorithm="RS256")

    def verify_token(self, token: str) -> str:
        """JWT를 검증하고 service_identity(sub)를 반환한다.

        검증 순서: 서명 → 만료 → 폐기 상태.

        Args:
            token: 검증할 JWT 문자열.

        Returns:
            sub 클레임의 service_identity 값.

        Raises:
            InvalidTokenError: 서명 검증 실패 또는 형식 오류
            TokenExpiredError: JWT 만료
            RevokedTokenError: 폐기된 JWT
        """
        public_key = self._get_public_key()
        try:
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["sub", "iat", "exp", "jti", "iss", "aud"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenExpiredError("Token has expired") from exc
        except (
            jwt.InvalidSignatureError,
            jwt.DecodeError,
            jwt.MissingRequiredClaimError,
            jwt.InvalidAlgorithmError,
            jwt.InvalidAudienceError,
            jwt.InvalidIssuerError,
        ) as exc:
            raise InvalidTokenError(f"Invalid token: {exc}") from exc

        jti = payload["jti"]
        if self._token_store.is_revoked(jti):
            raise RevokedTokenError(f"Token {jti} has been revoked")

        return payload["sub"]

    def revoke(self, token: str) -> None:
        """JWT를 즉시 폐기한다.

        토큰에서 jti와 exp를 추출하여 Token_Store에 등록한다.
        만료 검증 없이 디코딩하여 이미 만료된 토큰도 폐기 가능하다.

        Args:
            token: 폐기할 JWT 문자열.

        Raises:
            InvalidTokenError: 토큰 디코딩 실패 시
        """
        public_key = self._get_public_key()
        try:
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"verify_exp": False},
            )
        except (
            jwt.InvalidSignatureError,
            jwt.DecodeError,
            jwt.InvalidAlgorithmError,
            jwt.InvalidAudienceError,
            jwt.InvalidIssuerError,
        ) as exc:
            raise InvalidTokenError(f"Invalid token: {exc}") from exc

        self._token_store.revoke(payload["jti"], float(payload["exp"]))
