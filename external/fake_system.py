"""callbot.external.fake_system — 테스트/로컬 개발용 FakeExternalSystem.

demo.py의 FakeExternalSystem을 정식 모듈로 재배치.
CALLBOT_EXTERNAL_BACKEND=fake 시 팩토리에서 사용된다.
"""
from __future__ import annotations

from callbot.business.enums import APIErrorType, BillingOperation, CustomerDBOperation
from callbot.business.external_system import ExternalSystemBase
from callbot.business.models import APIError, APIResult


class FakeExternalSystem(ExternalSystemBase):
    """하드코딩 응답을 반환하는 테스트용 외부 시스템 구현체."""

    def __init__(self, auth_verified: bool = True) -> None:
        self._auth_verified = auth_verified
        self._current_plan = {"name": "5G 스탠다드", "monthly_fee": 55000, "penalty": 0}
        self._addons = [
            {"addon_id": "ADD-001", "name": "데이터 쉐어링", "monthly_fee": 5500, "cancelable": True},
            {"addon_id": "ADD-002", "name": "안심 데이터", "monthly_fee": 3300, "cancelable": True},
            {"addon_id": "ADD-003", "name": "약정 보험", "monthly_fee": 2200, "cancelable": False},
        ]

    def call_customer_db(
        self,
        operation: CustomerDBOperation,
        params: dict,
        timeout_sec: float = 1.0,
    ) -> APIResult:
        if operation == CustomerDBOperation.IDENTIFY:
            return APIResult(
                is_success=True,
                data={
                    "customer_info": {
                        "customer_id": "CUST-001",
                        "name": "홍길동",
                        "phone": params.get("phone", ""),
                    }
                },
                error=None,
                response_time_ms=10,
                retry_count=0,
            )
        if operation == CustomerDBOperation.VERIFY_AUTH:
            return APIResult(
                is_success=True,
                data={"verified": self._auth_verified, "has_password": True},
                error=None,
                response_time_ms=10,
                retry_count=0,
            )
        return APIResult(
            is_success=True, data={}, error=None, response_time_ms=10, retry_count=0
        )

    def call_billing_api(
        self,
        operation: BillingOperation,
        params: dict,
        timeout_sec: float = 5.0,
    ) -> APIResult:
        if operation == BillingOperation.QUERY_BILLING:
            return APIResult(
                is_success=True,
                data={
                    "monthly_fee": 55000,
                    "due_date": "2026-03-25",
                    "current_plan": self._current_plan["name"],
                },
                error=None,
                response_time_ms=20,
                retry_count=0,
            )
        if operation == BillingOperation.QUERY_PAYMENT:
            return APIResult(
                is_success=True,
                data={
                    "last_payment": "2026-02-25",
                    "last_payment_amount": 55000,
                    "status": "납부완료",
                },
                error=None,
                response_time_ms=20,
                retry_count=0,
            )
        if operation == BillingOperation.QUERY_PLANS:
            return APIResult(
                is_success=True,
                data={
                    "plans": [
                        {"name": "5G 라이트", "monthly_fee": 45000, "penalty": 0, "effective_date": "즉시"},
                        {"name": "5G 스탠다드", "monthly_fee": 55000, "penalty": 0, "effective_date": "즉시"},
                        {"name": "5G 프리미엄", "monthly_fee": 75000, "penalty": 0, "effective_date": "즉시"},
                    ],
                    "current_plan": self._current_plan,
                },
                error=None,
                response_time_ms=20,
                retry_count=0,
            )
        if operation == BillingOperation.CHANGE_PLAN:
            new_name = params.get("plan_name", "")
            fee_map = {"5G 라이트": 45000, "5G 스탠다드": 55000, "5G 프리미엄": 75000}
            self._current_plan = {
                "name": new_name,
                "monthly_fee": fee_map.get(new_name, 0),
                "penalty": 0,
            }
            return APIResult(
                is_success=True,
                data={"result": "변경완료", "new_plan": new_name},
                error=None,
                response_time_ms=30,
                retry_count=0,
            )
        if operation == BillingOperation.QUERY_DATA_USAGE:
            return APIResult(
                is_success=True,
                data={
                    "total_gb": 15.0,
                    "used_gb": 9.2,
                    "remaining_gb": 5.8,
                    "reset_date": "2026-04-01",
                    "plan_name": self._current_plan["name"],
                },
                error=None,
                response_time_ms=20,
                retry_count=0,
            )
        if operation == BillingOperation.CANCEL_ADDON:
            addon_id = params.get("addon_id", "")
            target = next((a for a in self._addons if a["addon_id"] == addon_id), None)
            if target is None:
                return APIResult(
                    is_success=False,
                    data={"reason": "존재하지 않는 부가서비스입니다."},
                    error=APIError(
                        error_type=APIErrorType.CLIENT_ERROR,
                        message="존재하지 않는 부가서비스입니다.",
                        is_retryable=False,
                    ),
                    response_time_ms=20,
                    retry_count=0,
                )
            if not target["cancelable"]:
                return APIResult(
                    is_success=False,
                    data={"reason": f"'{target['name']}'은(는) 약정 기간 내 해지 불가합니다."},
                    error=APIError(
                        error_type=APIErrorType.CLIENT_ERROR,
                        message=f"'{target['name']}'은(는) 약정 기간 내 해지 불가합니다.",
                        is_retryable=False,
                    ),
                    response_time_ms=20,
                    retry_count=0,
                )
            self._addons = [a for a in self._addons if a["addon_id"] != addon_id]
            return APIResult(
                is_success=True,
                data={"result": "해지완료", "addon_name": target["name"]},
                error=None,
                response_time_ms=30,
                retry_count=0,
            )
        return APIResult(
            is_success=True, data={}, error=None, response_time_ms=10, retry_count=0
        )
