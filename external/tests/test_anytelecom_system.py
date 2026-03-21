"""AnyTelecomExternalSystem 테스트 — PBT + 단위 테스트."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from callbot.business.enums import BillingOperation, CustomerDBOperation
from callbot.business.models import APIResult
from callbot.business.api_wrapper import APIWrapperSystemBase
from callbot.external.anytelecom_system import AnyTelecomExternalSystem


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------


def _make_mock_http_client() -> MagicMock:
    """Mock AnyTelecomHTTPClient (api_wrapper.APIWrapperSystemBase 구현체)."""
    mock_client = MagicMock(spec=APIWrapperSystemBase)
    mock_client.call.return_value = {"result": "ok"}
    return mock_client


# ---------------------------------------------------------------------------
# Property 7: 고수준 어댑터 반환 타입 불변성
# Feature: callbot-external-api-integration, Property 7: 고수준 어댑터 반환 타입 불변성
# **Validates: Requirements 5.5, 5.6**
# ---------------------------------------------------------------------------


@given(
    operation=st.sampled_from(BillingOperation),
    params=st.dictionaries(st.text(), st.text()),
)
@settings(max_examples=100)
def test_call_billing_api_returns_api_result(
    operation: BillingOperation, params: dict
) -> None:
    """For all BillingOperation 값과 임의의 params에 대해, call_billing_api() 반환값은 APIResult."""
    mock_client = _make_mock_http_client()

    with patch("callbot.external.anytelecom_system.time.sleep"):
        system = AnyTelecomExternalSystem(http_client=mock_client)
        result = system.call_billing_api(operation, params)

    assert isinstance(result, APIResult), f"Expected APIResult, got {type(result)}"


@given(
    operation=st.sampled_from(CustomerDBOperation),
    params=st.dictionaries(st.text(), st.text()),
)
@settings(max_examples=100)
def test_call_customer_db_returns_api_result(
    operation: CustomerDBOperation, params: dict
) -> None:
    """For all CustomerDBOperation 값과 임의의 params에 대해, call_customer_db() 반환값은 APIResult."""
    mock_client = _make_mock_http_client()

    with patch("callbot.external.anytelecom_system.time.sleep"):
        system = AnyTelecomExternalSystem(http_client=mock_client)
        result = system.call_customer_db(operation, params)

    assert isinstance(result, APIResult), f"Expected APIResult, got {type(result)}"



# ---------------------------------------------------------------------------
# 단위 테스트 — 고수준 어댑터
# Requirements: 5.2, 5.3, 8.9
# ---------------------------------------------------------------------------


def test_call_billing_api_normalizes_response() -> None:
    """성공 응답의 data가 ResponseNormalizer로 정규화됨을 검증."""
    mock_client = _make_mock_http_client()
    # raw 응답: 정규화 전 형태 (charges 키 없이 flat dict)
    mock_client.call.return_value = {"amount": 10000, "due_date": "2025-01-01"}

    with patch("callbot.external.anytelecom_system.time.sleep"):
        system = AnyTelecomExternalSystem(http_client=mock_client)
        result = system.call_billing_api(
            BillingOperation.QUERY_BILLING, {"phone": "010-1234-5678"}
        )

    assert result.is_success is True
    # ResponseNormalizer는 요금_조회를 {"charges": [...]} 형식으로 정규화
    assert "charges" in result.data


def test_call_customer_db_normalizes_response() -> None:
    """성공 응답의 data가 ResponseNormalizer로 정규화됨을 검증."""
    mock_client = _make_mock_http_client()
    # raw 응답: 정규화 전 형태 (customer_info 키 없이 flat dict)
    mock_client.call.return_value = {"name": "홍길동", "phone": "010-1234-5678"}

    with patch("callbot.external.anytelecom_system.time.sleep"):
        system = AnyTelecomExternalSystem(http_client=mock_client)
        result = system.call_customer_db(
            CustomerDBOperation.IDENTIFY, {"phone": "010-1234-5678"}
        )

    assert result.is_success is True
    # ResponseNormalizer는 고객_식별을 {"customer_info": {...}} 형식으로 정규화
    assert "customer_info" in result.data


def test_failed_result_not_normalized() -> None:
    """실패 APIResult는 정규화 없이 그대로 반환."""
    mock_client = _make_mock_http_client()
    # ValueError를 발생시켜 ExternalAPIWrapper가 실패 APIResult를 반환하도록 함
    mock_client.call.side_effect = ValueError("HTTP 400: Bad Request")

    with patch("callbot.external.anytelecom_system.time.sleep"):
        system = AnyTelecomExternalSystem(http_client=mock_client)
        result = system.call_billing_api(
            BillingOperation.QUERY_BILLING, {"phone": "010-1234-5678"}
        )

    assert result.is_success is False
    assert result.data is None
    assert result.error is not None
