"""LLMIntentClassifier + FallbackIntentClassifier 테스트 (Phase M)"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from callbot.nlu.enums import Intent
from callbot.nlu.intent_classifier import _RawPrediction


# ── LLMIntentClassifier 테스트 ──


class TestLLMIntentClassifier:
    """LLM 기반 인텐트 분류기 단위 테스트."""

    def _make_classifier(self, bedrock_response: str | Exception):
        """Mock BedrockService로 LLMIntentClassifier 생성."""
        from callbot.nlu.llm_intent_classifier import LLMIntentClassifier

        mock_bedrock = MagicMock()
        if isinstance(bedrock_response, Exception):
            mock_bedrock.invoke.side_effect = bedrock_response
        else:
            mock_bedrock.invoke.return_value = bedrock_response
        return LLMIntentClassifier(
            bedrock_service=mock_bedrock,
            model_id="anthropic.claude-sonnet-4-20250514",
            timeout=3.0,
        ), mock_bedrock

    def test_normal_classification(self):
        """정상 JSON → _RawPrediction 매핑."""
        response = json.dumps({
            "intent": "BILLING_INQUIRY",
            "confidence": 0.95,
            "secondary_intents": [],
        })
        clf, _ = self._make_classifier(response)
        result = clf.predict("이번 달 요금 알려줘")
        assert result.intent == Intent.BILLING_INQUIRY
        assert result.confidence == 0.95
        assert result.secondary_intents == []

    def test_complex_intent(self):
        """복합 인텐트 추출."""
        response = json.dumps({
            "intent": "PLAN_CHANGE",
            "confidence": 0.9,
            "secondary_intents": ["DATA_USAGE_INQUIRY"],
        })
        clf, _ = self._make_classifier(response)
        result = clf.predict("요금제 바꾸고 데이터도 확인해줘")
        assert result.intent == Intent.PLAN_CHANGE
        assert Intent.DATA_USAGE_INQUIRY in result.secondary_intents

    def test_invalid_json_raises_valueerror(self):
        """잘못된 JSON → ValueError."""
        clf, _ = self._make_classifier("이것은 JSON이 아닙니다")
        with pytest.raises(ValueError):
            clf.predict("아무 말")

    def test_unknown_intent_returns_unclassified(self):
        """존재하지 않는 인텐트명 → UNCLASSIFIED."""
        response = json.dumps({
            "intent": "NONEXISTENT_INTENT",
            "confidence": 0.8,
            "secondary_intents": [],
        })
        clf, _ = self._make_classifier(response)
        result = clf.predict("테스트")
        assert result.intent == Intent.UNCLASSIFIED
        assert result.confidence == 0.0

    def test_timeout_raises_exception(self):
        """타임아웃 → Exception."""
        clf, _ = self._make_classifier(TimeoutError("timeout"))
        with pytest.raises(TimeoutError):
            clf.predict("테스트")

    def test_json_with_extra_text(self):
        """JSON 앞뒤 텍스트가 있는 경우에도 파싱."""
        response = '여기 결과입니다:\n{"intent": "COMPLAINT", "confidence": 0.85, "secondary_intents": []}\n끝'
        clf, _ = self._make_classifier(response)
        result = clf.predict("불만이야")
        assert result.intent == Intent.COMPLAINT

    def test_missing_secondary_intents_defaults_empty(self):
        """secondary_intents 키 누락 시 빈 리스트."""
        response = json.dumps({"intent": "END_CALL", "confidence": 0.99})
        clf, _ = self._make_classifier(response)
        result = clf.predict("끊을게")
        assert result.intent == Intent.END_CALL
        assert result.secondary_intents == []


# ── FallbackIntentClassifier 테스트 ──


class TestFallbackIntentClassifier:
    """폴백 분류기 테스트."""

    def test_llm_success_returns_llm_result(self):
        """LLM 성공 → LLM 결과 반환."""
        from callbot.nlu.llm_intent_classifier import FallbackIntentClassifier

        primary = MagicMock()
        primary.predict.return_value = _RawPrediction(
            intent=Intent.BILLING_INQUIRY, confidence=0.9
        )
        fallback = MagicMock()
        clf = FallbackIntentClassifier(primary=primary, fallback=fallback)
        result = clf.predict("요금 조회")
        assert result.intent == Intent.BILLING_INQUIRY
        fallback.predict.assert_not_called()

    def test_llm_failure_uses_fallback(self):
        """LLM 실패(Exception) → Mock 결과 반환."""
        from callbot.nlu.llm_intent_classifier import FallbackIntentClassifier

        primary = MagicMock()
        primary.predict.side_effect = ValueError("bad json")
        fallback = MagicMock()
        fallback.predict.return_value = _RawPrediction(
            intent=Intent.GENERAL_INQUIRY, confidence=0.7
        )
        clf = FallbackIntentClassifier(primary=primary, fallback=fallback)
        result = clf.predict("테스트")
        assert result.intent == Intent.GENERAL_INQUIRY

    def test_both_failure_returns_unclassified(self):
        """LLM + Mock 모두 실패 → UNCLASSIFIED."""
        from callbot.nlu.llm_intent_classifier import FallbackIntentClassifier

        primary = MagicMock()
        primary.predict.side_effect = RuntimeError("llm down")
        fallback = MagicMock()
        fallback.predict.side_effect = RuntimeError("mock down")
        clf = FallbackIntentClassifier(primary=primary, fallback=fallback)
        result = clf.predict("테스트")
        assert result.intent == Intent.UNCLASSIFIED
        assert result.confidence == 0.0


# ── LRU 캐시 테스트 ──


class TestLLMIntentClassifierCache:
    """LRU 캐시 동작 검증."""

    def _make_cached_classifier(self, responses: list[str]):
        from callbot.nlu.llm_intent_classifier import LLMIntentClassifier

        mock_bedrock = MagicMock()
        mock_bedrock.invoke.side_effect = responses
        return LLMIntentClassifier(
            bedrock_service=mock_bedrock,
            model_id="anthropic.claude-sonnet-4-20250514",
            timeout=3.0,
        ), mock_bedrock

    def test_same_text_cached(self):
        """동일 발화 2회 호출 → Bedrock 1회만 호출."""
        resp = json.dumps({"intent": "BILLING_INQUIRY", "confidence": 0.9, "secondary_intents": []})
        clf, mock = self._make_cached_classifier([resp])
        clf.predict("요금 알려줘")
        clf.predict("요금 알려줘")
        assert mock.invoke.call_count == 1

    def test_different_text_not_cached(self):
        """다른 발화 → 각각 Bedrock 호출."""
        resp1 = json.dumps({"intent": "BILLING_INQUIRY", "confidence": 0.9, "secondary_intents": []})
        resp2 = json.dumps({"intent": "PLAN_INQUIRY", "confidence": 0.8, "secondary_intents": []})
        clf, mock = self._make_cached_classifier([resp1, resp2])
        clf.predict("요금 알려줘")
        clf.predict("요금제 알려줘")
        assert mock.invoke.call_count == 2

    def test_normalization_strips_and_lowercases(self):
        """strip/lower 정규화 동작 — 같은 텍스트로 인식."""
        resp = json.dumps({"intent": "BILLING_INQUIRY", "confidence": 0.9, "secondary_intents": []})
        clf, mock = self._make_cached_classifier([resp])
        clf.predict("  요금 알려줘  ")
        clf.predict("요금 알려줘")
        assert mock.invoke.call_count == 1
