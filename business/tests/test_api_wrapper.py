"""Tests for ExternalAPIWrapper — Tasks 9, 10, 11"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, call

import pytest

from callbot.business.api_wrapper import (
    AlertServiceBase,
    CircuitBreaker,
    ExternalAPIWrapper,
    APIWrapperSystemBase,
)
from callbot.business.enums import APIErrorType, BillingOperation, CircuitStatus, CustomerDBOperation
from callbot.business.models import APIError, APIResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_wrapper(side_effects=None, return_value=None):
    sys_mock = MagicMock(spec=APIWrapperSystemBase)
    if side_effects is not None:
        sys_mock.call.side_effect = side_effects
    elif return_value is not None:
        sys_mock.call.return_value = return_value
    else:
        sys_mock.call.return_value = {"ok": True}
    return ExternalAPIWrapper(external_system=sys_mock), sys_mock


# ---------------------------------------------------------------------------
# 9.1 재시도 로직
# ---------------------------------------------------------------------------

def test_retry_once_then_success():
    """1회 실패 후 재시도 성공 → retry_count=1, is_success=True"""
    wrapper, sys_mock = _make_wrapper(
        side_effects=[Exception("일시 오류"), {"ok": True}]
    )
    result = wrapper.call_billing_api(BillingOperation.QUERY_BILLING, {})
    assert result.is_success is True
    assert result.retry_count == 1


def test_retry_twice_both_fail():
    """2회 모두 실패 → retry_count=2, is_success=False"""
    wrapper, sys_mock = _make_wrapper(
        side_effects=[Exception("오류1"), Exception("오류2"), Exception("오류3")]
    )
    result = wrapper.call_billing_api(BillingOperation.QUERY_BILLING, {})
    assert result.is_success is False
    assert result.retry_count == 2


# ---------------------------------------------------------------------------
# 9.2 타임아웃
# ---------------------------------------------------------------------------

def test_billing_api_timeout_returns_timeout_error():
    """과금_시스템 타임아웃 → error_type=TIMEOUT"""
    wrapper, _ = _make_wrapper(
        side_effects=[TimeoutError("5초 초과"), TimeoutError("5초 초과"), TimeoutError("5초 초과")]
    )
    result = wrapper.call_billing_api(BillingOperation.QUERY_BILLING, {}, timeout_sec=5.0)
    assert result.is_success is False
    assert result.error.error_type == APIErrorType.TIMEOUT


def test_customer_db_timeout_returns_timeout_error():
    """고객_DB 타임아웃 → error_type=TIMEOUT"""
    wrapper, _ = _make_wrapper(
        side_effects=[TimeoutError("1초 초과"), TimeoutError("1초 초과"), TimeoutError("1초 초과")]
    )
    result = wrapper.call_customer_db(CustomerDBOperation.IDENTIFY, {}, timeout_sec=1.0)
    assert result.is_success is False
    assert result.error.error_type == APIErrorType.TIMEOUT


# ---------------------------------------------------------------------------
# 10.1 서킷브레이커 OPEN 상태
# ---------------------------------------------------------------------------

def test_circuit_open_returns_partial_failure_without_calling_system():
    """OPEN 상태에서 API 호출 시 즉시 PARTIAL_FAILURE 반환 (외부 시스템 호출 없음)"""
    wrapper, sys_mock = _make_wrapper(return_value={"ok": True})

    # 서킷브레이커를 강제로 OPEN 상태로 설정
    breaker = wrapper._get_breaker("billing")
    breaker._status = CircuitStatus.OPEN
    breaker._opened_at = time.monotonic()  # 방금 열림

    result = wrapper.call_billing_api(BillingOperation.QUERY_BILLING, {})

    assert result.is_success is False
    assert result.error.error_type == APIErrorType.PARTIAL_FAILURE
    sys_mock.call.assert_not_called()


# ---------------------------------------------------------------------------
# 10.2 서킷브레이커 상태 전환
# ---------------------------------------------------------------------------

def test_circuit_opens_when_failure_rate_exceeds_threshold():
    """실패율 50% 초과 (최소 10건) → OPEN 전환"""
    breaker = CircuitBreaker()

    # 10건 중 6건 실패 (60% > 50%)
    for _ in range(4):
        breaker.record_success()
    for _ in range(6):
        breaker.record_failure()

    assert breaker.status == CircuitStatus.OPEN


def test_circuit_transitions_to_half_open_after_timeout(monkeypatch):
    """30초 후 → HALF_OPEN 전환"""
    breaker = CircuitBreaker()

    # OPEN 상태로 강제 설정, opened_at을 31초 전으로
    breaker._status = CircuitStatus.OPEN
    breaker._opened_at = time.monotonic() - 31  # 31초 전

    assert breaker.status == CircuitStatus.HALF_OPEN


# ---------------------------------------------------------------------------
# 11.1 롤백 3회 실패
# ---------------------------------------------------------------------------

def test_rollback_all_three_fail_requires_manual():
    """3회 모두 실패 → requires_manual=True, retry_count=3, is_success=False"""
    wrapper, sys_mock = _make_wrapper(
        side_effects=[Exception("실패1"), Exception("실패2"), Exception("실패3")]
    )
    # 빠른 테스트를 위해 sleep 패치
    import callbot.business.api_wrapper as mod
    original_sleep = mod.time.sleep
    mod.time.sleep = lambda _: None

    try:
        result = wrapper.rollback_transaction("txn-001", "billing")
    finally:
        mod.time.sleep = original_sleep

    assert result.is_success is False
    assert result.requires_manual is True
    assert result.retry_count == 3


def test_rollback_success_on_third_attempt():
    """2회 실패 후 성공 → is_success=True, requires_manual=False"""
    wrapper, sys_mock = _make_wrapper(
        side_effects=[Exception("실패1"), Exception("실패2"), {"ok": True}]
    )
    import callbot.business.api_wrapper as mod
    original_sleep = mod.time.sleep
    mod.time.sleep = lambda _: None

    try:
        result = wrapper.rollback_transaction("txn-002", "billing")
    finally:
        mod.time.sleep = original_sleep

    assert result.is_success is True
    assert result.requires_manual is False


def test_rollback_sends_critical_alert_on_three_failures():
    """3회 실패 시 운영팀 critical 알림 발송"""
    sys_mock = MagicMock(spec=APIWrapperSystemBase)
    sys_mock.call.side_effect = [Exception("실패1"), Exception("실패2"), Exception("실패3")]
    alert_mock = MagicMock(spec=AlertServiceBase)
    wrapper = ExternalAPIWrapper(external_system=sys_mock, alert_service=alert_mock)

    import callbot.business.api_wrapper as mod
    original_sleep = mod.time.sleep
    mod.time.sleep = lambda _: None

    try:
        wrapper.rollback_transaction("txn-003", "billing")
    finally:
        mod.time.sleep = original_sleep

    alert_mock.send_critical.assert_called_once()
