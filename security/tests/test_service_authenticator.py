"""ServiceAuthenticator 속성 기반 테스트 및 단위 테스트.

TASK-S03: HS256 → RS256 전환.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from hypothesis import given, settings
from hypothesis import strategies as st

from callbot.security.exceptions import (
    InvalidTokenError,
    RevokedTokenError,
    SecretNotFoundError,
    TokenExpiredError,
)
from callbot.security.secrets_manager import SecretsManager
from callbot.security.service_authenticator import ServiceAuthenticator
from callbot.security.token_store import InMemoryTokenStore

# RSA 키페어 생성 (테스트용)
_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
RSA_PRIVATE_PEM = _RSA_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode("utf-8")
RSA_PUBLIC_PEM = _RSA_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode("utf-8")


def _make_mock_sm() -> SecretsManager:
    mock_sm = MagicMock(spec=SecretsManager)

    def _get_secret(name: str) -> str:
        if "private" in name:
            return RSA_PRIVATE_PEM
        if "public" in name:
            return RSA_PUBLIC_PEM
        return RSA_PRIVATE_PEM

    mock_sm.get_secret.side_effect = _get_secret
    return mock_sm


# ---------------------------------------------------------------------------
# Property 1: JWT 클레임 완전성
# ---------------------------------------------------------------------------


@given(service_identity=st.text(min_size=1, max_size=50))
@settings(max_examples=100)
def test_property1_jwt_claim_completeness(service_identity: str) -> None:
    """발급된 JWT에 sub, iat, exp, jti 클레임 모두 존재 검증."""
    mock_sm = _make_mock_sm()
    auth = ServiceAuthenticator(mock_sm, InMemoryTokenStore())
    token = auth.issue_token(service_identity)

    payload = jwt.decode(token, RSA_PUBLIC_PEM, algorithms=["RS256"], audience="callbot-services")
    assert "sub" in payload
    assert "iat" in payload
    assert "exp" in payload
    assert "jti" in payload


# ---------------------------------------------------------------------------
# Property 2: JWT TTL 적용
# ---------------------------------------------------------------------------


@given(ttl=st.integers(min_value=1, max_value=86400))
@settings(max_examples=100)
def test_property2_jwt_ttl_applied(ttl: int) -> None:
    """exp - iat == TTL 검증."""
    mock_sm = _make_mock_sm()
    auth = ServiceAuthenticator(mock_sm, InMemoryTokenStore(), jwt_ttl_seconds=ttl)
    token = auth.issue_token("test-service")

    payload = jwt.decode(token, RSA_PUBLIC_PEM, algorithms=["RS256"], audience="callbot-services")
    assert payload["exp"] - payload["iat"] == ttl


# ---------------------------------------------------------------------------
# Property 3: JWT 발급-검증 라운드트립
# ---------------------------------------------------------------------------


@given(service_identity=st.text(min_size=1, max_size=50))
@settings(max_examples=100)
def test_property3_jwt_issue_verify_roundtrip(service_identity: str) -> None:
    """issue → verify → 동일 service_identity 검증."""
    mock_sm = _make_mock_sm()
    store = InMemoryTokenStore()
    auth = ServiceAuthenticator(mock_sm, store)

    token = auth.issue_token(service_identity)
    result = auth.verify_token(token)
    assert result == service_identity


# ---------------------------------------------------------------------------
# Property 4: 폐기된 JWT 검증 거부
# ---------------------------------------------------------------------------


@given(service_identity=st.text(min_size=1, max_size=50))
@settings(max_examples=100)
def test_property4_revoked_jwt_rejected(service_identity: str) -> None:
    """issue → revoke → verify 시 RevokedTokenError."""
    mock_sm = _make_mock_sm()
    store = InMemoryTokenStore()
    auth = ServiceAuthenticator(mock_sm, store)

    token = auth.issue_token(service_identity)
    auth.revoke(token)

    with pytest.raises(RevokedTokenError):
        auth.verify_token(token)


# ---------------------------------------------------------------------------
# 단위 테스트
# ---------------------------------------------------------------------------


class TestServiceAuthenticatorUnit:
    """ServiceAuthenticator 단위 테스트."""

    def test_private_key_not_found_raises_error(self) -> None:
        """private key 조회 실패 → SecretNotFoundError."""
        mock_sm = MagicMock(spec=SecretsManager)
        mock_sm.get_secret.side_effect = SecretNotFoundError("key not found")
        auth = ServiceAuthenticator(mock_sm, InMemoryTokenStore())

        with pytest.raises(SecretNotFoundError):
            auth.issue_token("some-service")

    def test_default_ttl_is_3600(self) -> None:
        """기본 TTL 3600초."""
        mock_sm = _make_mock_sm()
        auth = ServiceAuthenticator(mock_sm, InMemoryTokenStore())
        token = auth.issue_token("test-service")

        payload = jwt.decode(token, RSA_PUBLIC_PEM, algorithms=["RS256"], audience="callbot-services")
        assert payload["exp"] - payload["iat"] == 3600

    def test_tampered_jwt_raises_invalid_token(self) -> None:
        """변조된 JWT → InvalidTokenError."""
        mock_sm = _make_mock_sm()
        auth = ServiceAuthenticator(mock_sm, InMemoryTokenStore())
        token = auth.issue_token("test-service")

        tampered = token[:-4] + "XXXX"

        with pytest.raises(InvalidTokenError):
            auth.verify_token(tampered)

    def test_expired_jwt_raises_token_expired(self) -> None:
        """만료된 JWT → TokenExpiredError."""
        mock_sm = _make_mock_sm()
        auth = ServiceAuthenticator(mock_sm, InMemoryTokenStore(), jwt_ttl_seconds=0)

        token = auth.issue_token("test-service")
        time.sleep(1)

        with pytest.raises(TokenExpiredError):
            auth.verify_token(token)

    def test_revoked_jti_raises_revoked_token(self) -> None:
        """폐기된 jti → RevokedTokenError."""
        mock_sm = _make_mock_sm()
        store = InMemoryTokenStore()
        auth = ServiceAuthenticator(mock_sm, store)

        token = auth.issue_token("test-service")
        auth.revoke(token)

        with pytest.raises(RevokedTokenError):
            auth.verify_token(token)

    def test_public_key_cannot_sign(self) -> None:
        """public key만으로 JWT 발급 불가 확인 (RS256 핵심 속성)."""
        mock_sm = MagicMock(spec=SecretsManager)
        # private key 자리에 public key를 넣음
        mock_sm.get_secret.return_value = RSA_PUBLIC_PEM
        auth = ServiceAuthenticator(mock_sm, InMemoryTokenStore())

        with pytest.raises(Exception):  # jwt.encode raises with wrong key type
            auth.issue_token("attacker-service")

    def test_hs256_token_rejected(self) -> None:
        """HS256으로 서명된 토큰이 RS256 검증에서 거부됨."""
        mock_sm = _make_mock_sm()
        auth = ServiceAuthenticator(mock_sm, InMemoryTokenStore())

        # HS256으로 직접 서명
        fake_token = jwt.encode(
            {"sub": "fake", "iat": int(time.time()), "exp": int(time.time()) + 3600, "jti": "fake-jti"},
            "some-symmetric-key",
            algorithm="HS256",
        )

        with pytest.raises(InvalidTokenError):
            auth.verify_token(fake_token)


# ---------------------------------------------------------------------------
# TASK-S06: JWT aud/iss 검증 테스트
# ---------------------------------------------------------------------------


class TestJwtAudIss:
    """JWT audience/issuer 검증."""

    def test_token_includes_iss_and_aud(self) -> None:
        """발급된 토큰에 iss, aud 클레임 포함."""
        mock_sm = _make_mock_sm()
        auth = ServiceAuthenticator(mock_sm, InMemoryTokenStore())
        token = auth.issue_token("test-svc")
        payload = jwt.decode(token, RSA_PUBLIC_PEM, algorithms=["RS256"], audience="callbot-services")
        assert payload["iss"] == "callbot"
        assert payload["aud"] == "callbot-services"

    def test_wrong_audience_rejected(self) -> None:
        """잘못된 audience → InvalidTokenError."""
        mock_sm = _make_mock_sm()
        auth_issuer = ServiceAuthenticator(mock_sm, InMemoryTokenStore(), audience="callbot-services")
        token = auth_issuer.issue_token("test-svc")

        auth_wrong_aud = ServiceAuthenticator(mock_sm, InMemoryTokenStore(), audience="wrong-audience")
        with pytest.raises(InvalidTokenError):
            auth_wrong_aud.verify_token(token)

    def test_wrong_issuer_rejected(self) -> None:
        """잘못된 issuer → InvalidTokenError."""
        mock_sm = _make_mock_sm()
        auth_issuer = ServiceAuthenticator(mock_sm, InMemoryTokenStore(), issuer="callbot")
        token = auth_issuer.issue_token("test-svc")

        auth_wrong_iss = ServiceAuthenticator(mock_sm, InMemoryTokenStore(), issuer="evil-issuer")
        with pytest.raises(InvalidTokenError):
            auth_wrong_iss.verify_token(token)

    def test_custom_aud_iss_roundtrip(self) -> None:
        """커스텀 aud/iss로 발급→검증 라운드트립."""
        mock_sm = _make_mock_sm()
        store = InMemoryTokenStore()
        auth = ServiceAuthenticator(mock_sm, store, issuer="my-issuer", audience="my-audience")
        token = auth.issue_token("my-service")
        assert auth.verify_token(token) == "my-service"
