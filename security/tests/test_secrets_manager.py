"""SecretsManager 속성 기반 테스트 및 단위 테스트."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from callbot.security.exceptions import SecretNotFoundError
from callbot.security.secrets_manager import SecretsManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_aws_manager(secret_value: str = "test-secret") -> tuple[SecretsManager, MagicMock]:
    """Mock AWS client를 주입한 SecretsManager를 생성한다."""
    mock_client = MagicMock()
    mock_client.get_secret_value.return_value = {"SecretString": secret_value}
    manager = SecretsManager(backend="aws", cache_ttl_seconds=300, client=mock_client)
    return manager, mock_client


# ---------------------------------------------------------------------------
# Property 10: 시크릿 캐시 히트 시 API 미호출
# Feature: callbot-security, Property 10: 시크릿 캐시 히트 시 API 미호출
# ---------------------------------------------------------------------------


@given(secret_name=st.text(min_size=1, max_size=50))
@settings(max_examples=100)
def test_property10_cache_hit_no_api_call(secret_name: str) -> None:
    """첫 번째 get_secret 호출 후 TTL 내에 두 번째 호출 시 AWS API는 1회만 호출된다.

    **Validates: Requirements 6.2, 6.3**
    """
    manager, mock_client = _make_aws_manager("cached-value")

    # 첫 번째 호출 → API 호출
    result1 = manager.get_secret(secret_name)
    # 두 번째 호출 → 캐시 히트
    result2 = manager.get_secret(secret_name)

    assert result1 == "cached-value"
    assert result2 == "cached-value"
    assert mock_client.get_secret_value.call_count == 1


# ---------------------------------------------------------------------------
# Property 11: 시크릿 캐시 TTL 적용
# Feature: callbot-security, Property 11: 시크릿 캐시 TTL 적용
# ---------------------------------------------------------------------------


@given(ttl=st.integers(min_value=1, max_value=600))
@settings(max_examples=100)
def test_property11_cache_ttl_expiry(ttl: int) -> None:
    """TTL 경과 후 get_secret 호출 시 AWS API가 재호출된다.

    **Validates: Requirements 6.4, 6.5**
    """
    mock_client = MagicMock()
    mock_client.get_secret_value.return_value = {"SecretString": "v1"}
    manager = SecretsManager(backend="aws", cache_ttl_seconds=ttl, client=mock_client)

    # monotonic 시각을 제어하기 위해 patch
    with patch("callbot.security.secrets_manager.time") as mock_time:
        mock_time.monotonic.return_value = 1000.0
        manager.get_secret("my-secret")
        assert mock_client.get_secret_value.call_count == 1

        # TTL 경과 전 → 캐시 히트
        mock_time.monotonic.return_value = 1000.0 + ttl - 0.1
        manager.get_secret("my-secret")
        assert mock_client.get_secret_value.call_count == 1

        # TTL 경과 후 → API 재호출
        mock_time.monotonic.return_value = 1000.0 + ttl + 0.1
        manager.get_secret("my-secret")
        assert mock_client.get_secret_value.call_count == 2


# ---------------------------------------------------------------------------
# Property 12: env 백엔드 이름 변환 규칙
# Feature: callbot-security, Property 12: env 백엔드 이름 변환 규칙
# ---------------------------------------------------------------------------

# secret_name에 사용할 문자: 영문, 숫자, 점, 하이픈, 슬래시, 밑줄
_env_name_chars = st.sampled_from(
    list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-/")
)


@given(secret_name=st.text(alphabet=_env_name_chars, min_size=1, max_size=50))
@settings(max_examples=100)
def test_property12_env_backend_name_transform(secret_name: str) -> None:
    """env 백엔드에서 secret_name → 대문자 + 특수문자 '_' 변환 후 환경변수 조회.

    **Validates: Requirements 7.1, 7.2**
    """
    expected_env_key = secret_name.upper().replace(".", "_").replace("/", "_").replace("-", "_")
    expected_value = "env-secret-value"

    # 빈 문자열이나 기존 환경변수와 충돌하는 키는 스킵
    if not expected_env_key or expected_env_key in os.environ:
        return

    manager = SecretsManager(backend="env", cache_ttl_seconds=300)

    with patch.dict(os.environ, {expected_env_key: expected_value}, clear=False):
        result = manager.get_secret(secret_name)
        assert result == expected_value


# ---------------------------------------------------------------------------
# 단위 테스트: SecretsManager
# ---------------------------------------------------------------------------


class TestSecretsManagerUnit:
    """SecretsManager 단위 테스트."""

    def test_aws_api_failure_raises_secret_not_found(self) -> None:
        """AWS API 실패 시 SecretNotFoundError가 발생한다.

        **Validates: Requirement 6.6**
        """
        mock_client = MagicMock()
        mock_client.get_secret_value.side_effect = Exception("AWS error")
        manager = SecretsManager(backend="aws", client=mock_client)

        with pytest.raises(SecretNotFoundError):
            manager.get_secret("nonexistent-secret")

    def test_refresh_invalidates_cache_and_refetches(self) -> None:
        """refresh() 후 재조회 시 API가 다시 호출된다.

        **Validates: Requirement 6.7**
        """
        mock_client = MagicMock()
        mock_client.get_secret_value.side_effect = [
            {"SecretString": "v1"},
            {"SecretString": "v2"},
        ]
        manager = SecretsManager(backend="aws", client=mock_client)

        val1 = manager.get_secret("my-secret")
        assert val1 == "v1"
        assert mock_client.get_secret_value.call_count == 1

        val2 = manager.refresh("my-secret")
        assert val2 == "v2"
        assert mock_client.get_secret_value.call_count == 2

    def test_default_cache_ttl_is_300(self) -> None:
        """기본 캐시 TTL은 300초이다.

        **Validates: Requirement 6.4**
        """
        manager = SecretsManager(backend="env")
        assert manager._cache_ttl_seconds == 300

    def test_default_backend_is_aws(self) -> None:
        """기본 백엔드는 'aws'이다.

        **Validates: Requirement 7.4**
        """
        mock_client = MagicMock()
        manager = SecretsManager(client=mock_client)
        assert manager._backend == "aws"

    def test_env_backend_missing_var_raises_error(self) -> None:
        """env 백엔드에서 환경변수가 존재하지 않으면 SecretNotFoundError가 발생한다.

        **Validates: Requirement 7.3**
        """
        manager = SecretsManager(backend="env")
        # 존재하지 않을 환경변수 이름 사용
        with pytest.raises(SecretNotFoundError):
            manager.get_secret("nonexistent.secret.key.xyz")


# ---------------------------------------------------------------------------
# TASK-S07: env 키 변환 버그 수정
# ---------------------------------------------------------------------------


def test_env_key_converts_slash_and_dash():
    """'callbot/jwt-signing-key' → 'CALLBOT_JWT_SIGNING_KEY'."""
    import os
    os.environ["CALLBOT_JWT_SIGNING_KEY"] = "test-value"
    try:
        sm = SecretsManager(backend="env")
        assert sm.get_secret("callbot/jwt-signing-key") == "test-value"
    finally:
        del os.environ["CALLBOT_JWT_SIGNING_KEY"]


def test_env_key_converts_dot():
    """'callbot.config.key' → 'CALLBOT_CONFIG_KEY'."""
    import os
    os.environ["CALLBOT_CONFIG_KEY"] = "dot-value"
    try:
        sm = SecretsManager(backend="env")
        assert sm.get_secret("callbot.config.key") == "dot-value"
    finally:
        del os.environ["CALLBOT_CONFIG_KEY"]


def test_env_key_converts_all_special_chars():
    """'app/my-service.secret' → 'APP_MY_SERVICE_SECRET'."""
    import os
    os.environ["APP_MY_SERVICE_SECRET"] = "all-special"
    try:
        sm = SecretsManager(backend="env")
        assert sm.get_secret("app/my-service.secret") == "all-special"
    finally:
        del os.environ["APP_MY_SERVICE_SECRET"]
