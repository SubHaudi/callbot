"""callbot.llm_engine.tests.test_prompt_loader — PromptLoader 단위 테스트"""
from __future__ import annotations

import pytest
from callbot.llm_engine.prompt_loader import PromptLoader


def test_get_prompt_default():
    loader = PromptLoader()
    prompt = loader.get_prompt()
    assert "AnyTelecom" in prompt


def test_get_prompt_billing_inquiry():
    loader = PromptLoader()
    prompt = loader.get_prompt("BILLING_INQUIRY")
    assert "요금" in prompt


def test_get_prompt_with_api_result():
    loader = PromptLoader()
    prompt = loader.get_prompt("BILLING_INQUIRY", api_result={"monthly_fee": 55000})
    assert "55000" in prompt
    assert "API 조회 결과" in prompt


def test_get_prompt_unknown_intent_falls_back():
    loader = PromptLoader()
    prompt = loader.get_prompt("UNKNOWN_INTENT")
    assert "AnyTelecom" in prompt


def test_custom_prompts_override():
    loader = PromptLoader(custom_prompts={"BILLING_INQUIRY": "커스텀 프롬프트"})
    assert loader.get_prompt("BILLING_INQUIRY") == "커스텀 프롬프트"


def test_different_intents_different_prompts():
    """M-13: 다른 intent에 다른 프롬프트가 적용된다."""
    loader = PromptLoader()
    billing = loader.get_prompt("BILLING_INQUIRY")
    data_usage = loader.get_prompt("DATA_USAGE_INQUIRY")
    assert billing != data_usage


def test_list_intents():
    loader = PromptLoader()
    intents = loader.list_intents()
    assert "BILLING_INQUIRY" in intents
    assert "DATA_USAGE_INQUIRY" in intents
    assert len(intents) >= 5


# ---------------------------------------------------------------------------
# 음성 채널 최적화 테스트
# ---------------------------------------------------------------------------

class TestVoiceOptimization:
    """Phase K: 시스템 프롬프트 음성 최적화 테스트."""

    def test_base_prompt_contains_voice_guidelines(self):
        """베이스 프롬프트에 음성 채널 지침이 포함되어야 한다."""
        loader = PromptLoader()
        prompt = loader.base_prompt
        # 간결성 지침
        assert any(kw in prompt for kw in ["1~2문장", "간결"]), \
            f"간결성 지침이 없음: {prompt}"
        # 마크다운 서식 금지
        assert any(kw in prompt for kw in ["마크다운", "서식"]), \
            f"서식 금지 지침이 없음: {prompt}"
        # 구어체
        assert any(kw in prompt for kw in ["구어체", "~이에요", "~해요"]), \
            f"구어체 지침이 없음: {prompt}"

    def test_intent_prompts_have_required_fields(self):
        """인텐트별 프롬프트에 필수 포함 정보가 있어야 한다."""
        loader = PromptLoader()
        required = {
            "BILLING_INQUIRY": ["금액"],
            "PAYMENT_CHECK": ["납부"],
            "DATA_USAGE_INQUIRY": ["잔여"],
            "PLAN_INQUIRY": ["요금제"],
        }
        for intent, keywords in required.items():
            prompt = loader.get_prompt(intent)
            for kw in keywords:
                assert kw in prompt, \
                    f"{intent} 프롬프트에 '{kw}' 필수 키워드 없음"
