"""callbot.external.operation_mapping — 오퍼레이션-엔드포인트 매핑."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EndpointInfo:
    """오퍼레이션-엔드포인트 매핑 정보."""

    method: str  # "GET" | "POST"
    path_template: str  # e.g. "/api/v1/billing/charges"


# (system, operation) → EndpointInfo
_MAPPING: dict[tuple[str, str], EndpointInfo] = {
    # billing
    ("billing", "요금_조회"): EndpointInfo("GET", "/api/v1/billing/charges"),
    ("billing", "납부_확인"): EndpointInfo("GET", "/api/v1/billing/payments"),
    ("billing", "요금제_목록_조회"): EndpointInfo("GET", "/api/v1/billing/plans"),
    ("billing", "요금제_변경"): EndpointInfo("POST", "/api/v1/billing/plans/change"),
    ("billing", "요금제_변경_롤백"): EndpointInfo("POST", "/api/v1/billing/plans/rollback"),
    ("billing", "데이터_잔여량_조회"): EndpointInfo("GET", "/api/v1/billing/data-usage"),
    ("billing", "부가서비스_해지"): EndpointInfo("POST", "/api/v1/billing/addons/cancel"),
    # customer_db
    ("customer_db", "고객_식별"): EndpointInfo("GET", "/api/v1/customers/identify"),
    ("customer_db", "인증_검증"): EndpointInfo("POST", "/api/v1/customers/verify"),
    ("customer_db", "고객_정보_조회"): EndpointInfo("GET", "/api/v1/customers/{customer_id}"),
}


class OperationMapping:
    """오퍼레이션 열거형을 HTTP 메서드 + URL 경로로 매핑."""

    @staticmethod
    def resolve(system: str, operation: str) -> EndpointInfo:
        """system + operation → EndpointInfo. 매핑 없으면 ValueError."""
        key = (system, operation)
        try:
            return _MAPPING[key]
        except KeyError:
            raise ValueError(
                f"Unknown mapping: system={system!r}, operation={operation!r}"
            )

    @staticmethod
    def all_operations() -> list[tuple[str, str, EndpointInfo]]:
        """모든 매핑 목록 반환 (검증용)."""
        return [(sys, op, info) for (sys, op), info in _MAPPING.items()]
