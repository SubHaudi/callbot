"""Tests for _call_with_retry ValueError 재시도 제외 수정 검증.

TDD: 테스트를 먼저 작성하고, 구현(1.3, 1.4)으로 통과시킨다.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from callbot.business.api_wrapper import ExternalAPIWrapper, APIWrapperSystemBase
from callbot.business.enums import APIErrorType
from callbot.business.models import APIResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_wrapper_with_mock(side_effects):
    """side_effects 리스트로 APIWrapperSystemBase mock을 구성한 wrapper 반환."""
    sys_mock = MagicMock(spec=APIWrapperSystemBase)
    sys_mock.call.side_effect = side_effects
    wrapper = ExternalAPIWrapper(external_system=sys_mock)
    return wrapper, sys_mock


def _patch_sleep():
    """time.sleep을 no-op으로 패치하여 테스트 속도를 높인다."""
    import callbot.business.api_wrapper as mod
    original = mod.time.sleep
    mod.time.sleep = lambda _: None
    return mod, original


def _restore_sleep(mod, original):
    mod.time.sleep = original


# ---------------------------------------------------------------------------
# 1.1 Property 6: ValueError 재시도 제외 PBT
# Feature: callbot-external-api-integration, Property 6: ValueError 재시도 제외
# **Validates: Requirements 4.8**
# ---------------------------------------------------------------------------

@given(msg=st.text())
@settings(max_examples=100)
def test_property6_valueerror_not_retried(msg):
    """For any ValueError message, _call_with_retry returns immediately
    with is_success=False, is_retryable=False, and retry_count == 0 (first attempt)."""
    wrapper, sys_mock = _make_wrapper_with_mock([ValueError(msg)])

    mod, original = _patch_sleep()
    try:
        result = wrapper.call_billing_api(
            __import__("callbot.business.enums", fromlist=["BillingOperation"]).BillingOperation.QUERY_BILLING,
            {},
        )
    finally:
        _restore_sleep(mod, original)

    assert isinstance(result, APIResult)
    assert result.is_success is False
    assert result.error is not None
    assert result.error.is_retryable is False
    assert result.error.error_type == APIErrorType.CLIENT_ERROR
    assert result.retry_count == 0
    # ValueError가 발생하면 단 1회만 호출되어야 한다 (재시도 없음)
    assert sys_mock.call.call_count == 1


# ---------------------------------------------------------------------------
# 1.2 ValueError 재시도 제외 단위 테스트
# Requirements: 4.8
# ---------------------------------------------------------------------------

class TestValueErrorNotRetried:
    """ValueError 발생 시 재시도 없이 즉시 실패 반환 검증."""

    def test_valueerror_not_retried(self):
        """첫 시도에서 ValueError 발생 → retry_count=0, 호출 횟수=1."""
        wrapper, sys_mock = _make_wrapper_with_mock([ValueError("bad request")])

        mod, original = _patch_sleep()
        try:
            from callbot.business.enums import BillingOperation
            result = wrapper.call_billing_api(BillingOperation.QUERY_BILLING, {})
        finally:
            _restore_sleep(mod, original)

        assert result.is_success is False
        assert result.retry_count == 0
        assert sys_mock.call.call_count == 1

    def test_valueerror_after_connection_error(self):
        """첫 시도 ConnectionError → 재시도 → ValueError → retry_count=1."""
        wrapper, sys_mock = _make_wrapper_with_mock([
            ConnectionError("server down"),
            ValueError("bad request"),
        ])

        mod, original = _patch_sleep()
        try:
            from callbot.business.enums import BillingOperation
            result = wrapper.call_billing_api(BillingOperation.QUERY_BILLING, {})
        finally:
            _restore_sleep(mod, original)

        assert result.is_success is False
        assert result.retry_count == 1
        assert result.error.is_retryable is False
        assert sys_mock.call.call_count == 2

    def test_valueerror_error_type_is_client_error(self):
        """반환된 APIResult.error.error_type이 CLIENT_ERROR."""
        wrapper, sys_mock = _make_wrapper_with_mock([ValueError("invalid param")])

        mod, original = _patch_sleep()
        try:
            from callbot.business.enums import BillingOperation
            result = wrapper.call_billing_api(BillingOperation.QUERY_BILLING, {})
        finally:
            _restore_sleep(mod, original)

        assert result.error.error_type == APIErrorType.CLIENT_ERROR
        assert result.error.message == "invalid param"
