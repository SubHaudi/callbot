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
