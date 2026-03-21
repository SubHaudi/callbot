"""callbot.business 통합 테스트 — Task 13.1"""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from callbot.business import (
    AuthenticationModule,
    ExternalAPIWrapper,
    RoutingEngine,
)
from callbot.business.api_wrapper import CircuitBreaker, APIWrapperSystemBase
from callbot.business.enums import (
    APIErrorType,
    AgentGroup,
    AuthType,
    BillingOperation,
    CircuitStatus,
    CustomerDBOperation,
)
from callbot.business.models import APIError, APIResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _api_result_success(data: dict) -> APIResult:
    return APIResult(is_success=True, data=data, error=None, response_time_ms=10, retry_count=0)


def _api_result_failure() -> APIResult:
    return APIResult(
        is_success=False,
        data=None,
        error=APIError(error_type=APIErrorType.TIMEOUT, message="timeout", is_retryable=True),
        response_time_ms=1000,
        retry_count=2,
    )


# ---------------------------------------------------------------------------
# 본인 인증 전체 흐름 통합 테스트
# ---------------------------------------------------------------------------

def test_auth_full_flow_identify_then_authenticate_success():
    """식별 → 인증 → 성공 전체 흐름"""
    wrapper = MagicMock()
    # 1st call: identify, 2nd call: authenticate success
    wrapper.call_customer_db.side_effect = [
        _api_result_success({"customer_info": {"id": "C001"}}),
        _api_result_success({"verified": True, "has_password": False}),
    ]
    module = AuthenticationModule(api_wrapper=wrapper)

    id_result = module.identify_by_caller_id("01012345678")
    assert id_result.is_found is True

    auth_result = module.authenticate("sess-1", AuthType.BIRTHDATE, "900101")
    assert auth_result.is_authenticated is True
    assert auth_result.failure_count == 0


def test_auth_full_flow_three_failures_locks_out():
    """식별 → 인증 3회 실패 → is_authenticated=False"""
    wrapper = MagicMock()
    wrapper.call_customer_db.side_effect = [
        _api_result_success({"customer_info": {"id": "C002"}}),
        _api_result_success({"verified": False, "has_password": False}),
        _api_result_success({"verified": False, "has_password": False}),
        _api_result_success({"verified": False, "has_password": False}),
    ]
    module = AuthenticationModule(api_wrapper=wrapper)

    module.identify_by_caller_id("01099999999")
    module.authenticate("sess-2", AuthType.BIRTHDATE, "000000")
    module.authenticate("sess-2", AuthType.BIRTHDATE, "000001")
    result = module.authenticate("sess-2", AuthType.BIRTHDATE, "000002")

    assert result.is_authenticated is False
    assert result.failure_count == 3


# ---------------------------------------------------------------------------
# 상담사 연결 폴백 통합 테스트
# ---------------------------------------------------------------------------

def test_routing_agent_available_success():
    """상담사 가용 → 연결 성공"""
    agent_sys = MagicMock()
    agent_sys.connect_agent.return_value = True
    engine = RoutingEngine(agent_system=agent_sys)

    session = MagicMock()
    session.session_id = "sess-r1"
    session.intent = None

    result = engine.route_to_agent(session, None, None)
    assert result.is_success is True
    assert result.is_system_error is False


def test_routing_system_error_fallback():
    """상담사 시스템 장애 → fallback_message 포함"""
    agent_sys = MagicMock()
    agent_sys.connect_agent.side_effect = Exception("시스템 장애")
    engine = RoutingEngine(agent_system=agent_sys)

    session = MagicMock()
    session.session_id = "sess-r2"
    session.intent = None

    result = engine.route_to_agent(session, None, None)
    assert result.is_success is False
    assert result.is_system_error is True
    assert result.fallback_message is not None


def test_routing_outside_business_hours():
    """영업시간 외 → is_open=False"""
    from datetime import datetime
    engine = RoutingEngine()
    result = engine.is_business_hours(datetime(2024, 1, 6, 10, 0))  # Saturday
    assert result.is_open is False


# ---------------------------------------------------------------------------
# API_래퍼 재시도 + 서킷브레이커 통합 테스트
# ---------------------------------------------------------------------------

def test_api_wrapper_retry_then_circuit_opens():
    """반복 실패 후 서킷브레이커 OPEN → 이후 요청 즉시 차단"""
    sys_mock = MagicMock(spec=APIWrapperSystemBase)
    sys_mock.call.side_effect = Exception("서버 오류")
    wrapper = ExternalAPIWrapper(external_system=sys_mock)

    # 서킷브레이커를 강제 OPEN
    breaker = wrapper._get_breaker("billing")
    breaker._status = CircuitStatus.OPEN
    breaker._opened_at = time.monotonic()

    result = wrapper.call_billing_api(BillingOperation.QUERY_BILLING, {})

    assert result.is_success is False
    assert result.error.error_type == APIErrorType.PARTIAL_FAILURE
    # 외부 시스템 호출 없음
    sys_mock.call.assert_not_called()


def test_api_wrapper_retry_succeeds_on_second_attempt():
    """1회 실패 후 재시도 성공"""
    sys_mock = MagicMock(spec=APIWrapperSystemBase)
    sys_mock.call.side_effect = [Exception("일시 오류"), {"result": "ok"}]
    wrapper = ExternalAPIWrapper(external_system=sys_mock)

    result = wrapper.call_billing_api(BillingOperation.QUERY_BILLING, {})

    assert result.is_success is True
    assert result.retry_count == 1
