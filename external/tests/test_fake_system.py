"""callbot.external.tests.test_fake_system — FakeExternalSystem 단위 테스트 (Phase C)"""
from __future__ import annotations

import pytest

from callbot.business.enums import BillingOperation
from callbot.external.fake_system import FakeExternalSystem


@pytest.fixture
def fake() -> FakeExternalSystem:
    return FakeExternalSystem()


class TestQueryDataUsage:
    def test_returns_success(self, fake: FakeExternalSystem) -> None:
        result = fake.call_billing_api(BillingOperation.QUERY_DATA_USAGE, {})
        assert result.is_success is True

    def test_has_remaining_gb(self, fake: FakeExternalSystem) -> None:
        result = fake.call_billing_api(BillingOperation.QUERY_DATA_USAGE, {})
        assert "remaining_gb" in result.data
        assert result.data["remaining_gb"] >= 0

    def test_has_total_and_used(self, fake: FakeExternalSystem) -> None:
        result = fake.call_billing_api(BillingOperation.QUERY_DATA_USAGE, {})
        assert result.data["total_gb"] == result.data["used_gb"] + result.data["remaining_gb"]

    def test_includes_plan_name(self, fake: FakeExternalSystem) -> None:
        result = fake.call_billing_api(BillingOperation.QUERY_DATA_USAGE, {})
        assert result.data["plan_name"] == "5G 스탠다드"


class TestCancelAddon:
    def test_cancel_success(self, fake: FakeExternalSystem) -> None:
        result = fake.call_billing_api(BillingOperation.CANCEL_ADDON, {"addon_id": "ADD-001"})
        assert result.is_success is True
        assert result.data["result"] == "해지완료"

    def test_cancel_removes_addon(self, fake: FakeExternalSystem) -> None:
        fake.call_billing_api(BillingOperation.CANCEL_ADDON, {"addon_id": "ADD-001"})
        # 같은 addon 다시 해지 시도 → 실패
        result = fake.call_billing_api(BillingOperation.CANCEL_ADDON, {"addon_id": "ADD-001"})
        assert result.is_success is False

    def test_cancel_non_cancelable_fails(self, fake: FakeExternalSystem) -> None:
        result = fake.call_billing_api(BillingOperation.CANCEL_ADDON, {"addon_id": "ADD-003"})
        assert result.is_success is False
        assert "약정" in result.data["reason"]

    def test_cancel_nonexistent_fails(self, fake: FakeExternalSystem) -> None:
        result = fake.call_billing_api(BillingOperation.CANCEL_ADDON, {"addon_id": "ADD-999"})
        assert result.is_success is False

    def test_normalizer_format_consistency(self, fake: FakeExternalSystem) -> None:
        """M-03: 모든 응답이 APIResult 표준 필드를 포함한다."""
        for op in [BillingOperation.QUERY_DATA_USAGE, BillingOperation.CANCEL_ADDON]:
            result = fake.call_billing_api(op, {"addon_id": "ADD-001"})
            assert hasattr(result, "is_success")
            assert hasattr(result, "data")
            assert hasattr(result, "error")
            assert hasattr(result, "response_time_ms")
