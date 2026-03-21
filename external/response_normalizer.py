"""callbot.external.response_normalizer — API 응답 정규화."""
from __future__ import annotations


class ResponseNormalizer:
    """AnyTelecom API raw 응답을 비즈니스 로직이 기대하는 표준 형식으로 변환.

    정규화는 멱등: ``normalize(normalize(data)) == normalize(data)``
    """

    @staticmethod
    def normalize(system: str, operation: str, raw_data: dict) -> dict:
        """raw API 응답 → 표준 형식 dict."""
        key = (system, operation)
        handler = _HANDLERS.get(key)
        if handler is None:
            raise ValueError(
                f"Unknown normalization target: system={system!r}, operation={operation!r}"
            )
        return handler(raw_data)


# ---------------------------------------------------------------------------
# 오퍼레이션별 정규화 핸들러 (private)
# ---------------------------------------------------------------------------


def _normalize_customer_info(data: dict) -> dict:
    """고객_식별 / 고객_정보_조회 → {"customer_info": {...}}"""
    if "customer_info" in data:
        return data
    return {"customer_info": data}


def _normalize_verify_auth(data: dict) -> dict:
    """인증_검증 → {"verified": bool, "has_password": bool}"""
    if set(data.keys()) == {"verified", "has_password"}:
        return data
    return {
        "verified": data.get("verified", False),
        "has_password": data.get("has_password", False),
    }


def _normalize_charges(data: dict) -> dict:
    """요금_조회 → {"charges": [...]}"""
    if "charges" in data and len(data) == 1:
        return data
    return {"charges": data.get("charges", [])}


def _normalize_payments(data: dict) -> dict:
    """납부_확인 → {"payments": [...]}"""
    if "payments" in data and len(data) == 1:
        return data
    return {"payments": data.get("payments", [])}


def _normalize_plans(data: dict) -> dict:
    """요금제_목록_조회 → {"plans": [...]}"""
    if "plans" in data and len(data) == 1:
        return data
    return {"plans": data.get("plans", [])}


def _normalize_change_plan(data: dict) -> dict:
    """요금제_변경 → {"transaction_id": str, "result": str}"""
    if set(data.keys()) == {"transaction_id", "result"}:
        return data
    return {
        "transaction_id": data.get("transaction_id", ""),
        "result": data.get("result", ""),
    }


def _normalize_rollback(data: dict) -> dict:
    """요금제_변경_롤백 → {"transaction_id": str, "rollback_result": str}"""
    if set(data.keys()) == {"transaction_id", "rollback_result"}:
        return data
    return {
        "transaction_id": data.get("transaction_id", ""),
        "rollback_result": data.get("rollback_result", ""),
    }


def _normalize_data_usage(data: dict) -> dict:
    """데이터_잔여량_조회 → {"total_gb": float, "used_gb": float, "remaining_gb": float, ...}"""
    return {
        "total_gb": data.get("total_gb", 0.0),
        "used_gb": data.get("used_gb", 0.0),
        "remaining_gb": data.get("remaining_gb", 0.0),
        "reset_date": data.get("reset_date", ""),
        "plan_name": data.get("plan_name", ""),
    }


def _normalize_cancel_addon(data: dict) -> dict:
    """부가서비스_해지 → {"result": str, "addon_name": str} or {"reason": str}"""
    if "reason" in data:
        return {"reason": data["reason"]}
    return {
        "result": data.get("result", ""),
        "addon_name": data.get("addon_name", ""),
    }


_HANDLERS: dict[tuple[str, str], callable] = {
    ("billing", "요금_조회"): _normalize_charges,
    ("billing", "납부_확인"): _normalize_payments,
    ("billing", "요금제_목록_조회"): _normalize_plans,
    ("billing", "요금제_변경"): _normalize_change_plan,
    ("billing", "요금제_변경_롤백"): _normalize_rollback,
    ("billing", "데이터_잔여량_조회"): _normalize_data_usage,
    ("billing", "부가서비스_해지"): _normalize_cancel_addon,
    ("customer_db", "고객_식별"): _normalize_customer_info,
    ("customer_db", "인증_검증"): _normalize_verify_auth,
    ("customer_db", "고객_정보_조회"): _normalize_customer_info,
}
