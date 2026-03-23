"""callbot.llm_engine.prompt_loader — intent별 프롬프트 템플릿 관리

PromptLoader는 DI로 pipeline에 주입되어 하드코딩 system_prompt를 대체한다.
"""
from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------------------------
# 기본 프롬프트 템플릿
# ---------------------------------------------------------------------------

_BASE_SYSTEM_PROMPT = (
    "당신은 AnyTelecom 고객센터 AI 상담사입니다.\n\n"
    "## 음성 응답 원칙\n"
    "- 간결: 핵심 정보 1~2문장으로 답변. 부연 설명 금지.\n"
    "- 구어체: '~이에요', '~해 드릴게요' 등 자연스러운 전화 상담 말투 사용.\n"
    "- 핵심 우선: 숫자/금액은 바로 말하기.\n"
    "- 대화 유도: 추가 안내 필요 시 '더 궁금하신 거 있으세요?'로 마무리.\n"
    "- 서식 금지: 마크다운, 불릿 기호(- *), 번호 기호(1.) 사용 금지. "
    "나열은 '첫 번째는 ~, 두 번째는 ~' 형태로."
)

_INTENT_PROMPTS: dict[str, str] = {
    "BILLING_INQUIRY": (
        f"{_BASE_SYSTEM_PROMPT}\n\n"
        "요금 관련 질문에 답변합니다.\n"
        "필수 포함: 금액. 예: '이번 달 요금은 65,000원이에요.'\n"
        "금액은 바로 말하고, 세부 내역은 고객이 물으면 안내하세요."
    ),
    "PAYMENT_CHECK": (
        f"{_BASE_SYSTEM_PROMPT}\n\n"
        "납부 내역을 확인합니다.\n"
        "필수 포함: 납부 상태, 금액.\n"
        "예: '최근 납부는 3월 15일에 65,000원 완료됐어요.'"
    ),
    "DATA_USAGE_INQUIRY": (
        f"{_BASE_SYSTEM_PROMPT}\n\n"
        "데이터 사용량을 안내합니다.\n"
        "필수 포함: 잔여 데이터량.\n"
        "예: '데이터 3.2GB 남아 있어요. 초기화일은 4월 1일이에요.'"
    ),
    "PLAN_INQUIRY": (
        f"{_BASE_SYSTEM_PROMPT}\n\n"
        "요금제 정보를 안내합니다.\n"
        "필수 포함: 요금제명, 월 요금.\n"
        "목록은 3개씩 나열: '첫 번째는 ~ 월 ~원, 두 번째는 ~' 형태로."
    ),
    "GENERAL_INQUIRY": (
        f"{_BASE_SYSTEM_PROMPT}\n\n"
        "일반 고객 문의에 답변합니다.\n"
        "모르는 정보는 '상담사 연결해 드릴까요?'로 안내하세요."
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
