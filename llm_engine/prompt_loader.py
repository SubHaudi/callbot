"""callbot.llm_engine.prompt_loader — intent별 프롬프트 템플릿 관리

PromptLoader는 DI로 pipeline에 주입되어 하드코딩 system_prompt를 대체한다.
"""
from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------------------------
# 기본 프롬프트 템플릿
# ---------------------------------------------------------------------------

_BASE_SYSTEM_PROMPT = (
    "당신은 AnyTelecom 고객센터 AI 상담사입니다. "
    "고객의 요청에 친절하고 정확하게 답변하세요."
)

_INTENT_PROMPTS: dict[str, str] = {
    "BILLING_INQUIRY": (
        f"{_BASE_SYSTEM_PROMPT}\n\n"
        "고객의 요금 관련 질문에 답변합니다. "
        "제공된 API 조회 결과를 기반으로 정확한 금액과 날짜를 안내하세요."
    ),
    "PAYMENT_CHECK": (
        f"{_BASE_SYSTEM_PROMPT}\n\n"
        "고객의 납부 내역을 확인합니다. "
        "최근 납부 일자, 금액, 상태를 안내하세요."
    ),
    "DATA_USAGE_INQUIRY": (
        f"{_BASE_SYSTEM_PROMPT}\n\n"
        "고객의 데이터 사용량을 안내합니다. "
        "총 데이터, 사용량, 잔여량, 초기화 일자를 명확히 전달하세요."
    ),
    "PLAN_INQUIRY": (
        f"{_BASE_SYSTEM_PROMPT}\n\n"
        "요금제 정보를 안내합니다. "
        "현재 요금제와 변경 가능한 옵션을 비교하여 설명하세요."
    ),
    "GENERAL_INQUIRY": (
        f"{_BASE_SYSTEM_PROMPT}\n\n"
        "일반적인 고객 문의에 답변합니다. "
        "정확하지 않은 정보는 제공하지 말고, 상담사 연결을 안내하세요."
    ),
}


class PromptLoader:
    """intent별 프롬프트 템플릿 로더.

    사용법:
        loader = PromptLoader()
        prompt = loader.get_prompt("BILLING_INQUIRY")
        prompt = loader.get_prompt("BILLING_INQUIRY", api_result={"monthly_fee": 55000})
    """

    def __init__(self, custom_prompts: Optional[dict[str, str]] = None) -> None:
        """
        Args:
            custom_prompts: intent → prompt 매핑 (기본 템플릿 오버라이드)
        """
        self._prompts = dict(_INTENT_PROMPTS)
        if custom_prompts:
            self._prompts.update(custom_prompts)

    def get_prompt(
        self,
        intent_name: Optional[str] = None,
        api_result: Optional[dict] = None,
    ) -> str:
        """intent에 맞는 프롬프트를 반환한다.

        Args:
            intent_name: Intent enum의 name (e.g. "BILLING_INQUIRY")
            api_result: API 조회 결과 (있으면 프롬프트에 포함)

        Returns:
            완성된 system prompt 문자열
        """
        base = self._prompts.get(intent_name, _BASE_SYSTEM_PROMPT) if intent_name else _BASE_SYSTEM_PROMPT

        if api_result is not None:
            return f"{base}\n\n[API 조회 결과]\n{api_result}"
        return base

    @property
    def base_prompt(self) -> str:
        """기본 system prompt."""
        return _BASE_SYSTEM_PROMPT

    def list_intents(self) -> list[str]:
        """등록된 intent 목록."""
        return list(self._prompts.keys())
