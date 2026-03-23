"""callbot.nlu.llm_intent_classifier — LLM 기반 인텐트 분류기 (Phase M)

Bedrock Claude를 호출하여 인텐트를 분류한다.
기존 IntentClassifierBase 인터페이스를 구현하며,
FallbackIntentClassifier로 래핑하여 폴백을 제공한다.
"""
from __future__ import annotations

import json
import logging
import re
from collections import OrderedDict
from typing import Any, Optional

from callbot.nlu.enums import Intent
from callbot.nlu.intent_classifier import IntentClassifierBase, _RawPrediction
from callbot.nlu.prompts import NLU_SYSTEM_PROMPT, NLU_USER_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)

_JSON_PATTERN = re.compile(r"\{[^{}]*\}")
_CACHE_MAX_SIZE = 256


class LLMIntentClassifier(IntentClassifierBase):
    """LLM(Bedrock Claude) 기반 인텐트 분류기."""

    def __init__(
        self,
        bedrock_service: Any,
        model_id: str = "anthropic.claude-sonnet-4-20250514",
        timeout: float = 3.0,
    ) -> None:
        self._bedrock = bedrock_service
        self._model_id = model_id
        self._timeout = timeout
        self._cache: OrderedDict[str, _RawPrediction] = OrderedDict()

    def predict(self, text: str) -> _RawPrediction:
        """텍스트에서 인텐트를 분류한다."""
        normalized = text.strip().lower()

        # 캐시 조회
        if normalized in self._cache:
            self._cache.move_to_end(normalized)
            return self._cache[normalized]

        # Bedrock 호출
        user_msg = NLU_USER_PROMPT_TEMPLATE.format(text=text)
        response = self._bedrock.invoke(
            model_id=self._model_id,
            system=NLU_SYSTEM_PROMPT,
            message=user_msg,
            timeout=self._timeout,
        )

        # JSON 파싱
        result = self._parse_response(response)

        # 캐시 저장
        self._cache[normalized] = result
        if len(self._cache) > _CACHE_MAX_SIZE:
            self._cache.popitem(last=False)

        return result

    def _parse_response(self, response: str) -> _RawPrediction:
        """LLM 응답에서 JSON을 추출하고 _RawPrediction으로 변환."""
        # JSON 추출 (앞뒤 텍스트 허용)
        match = _JSON_PATTERN.search(response)
        if not match:
            raise ValueError(f"JSON not found in response: {response[:200]}")

        try:
            data = json.loads(match.group())
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e

        # 인텐트 매핑
        intent_str = data.get("intent", "UNCLASSIFIED")
        confidence = float(data.get("confidence", 0.0))

        try:
            intent = Intent[intent_str]
        except KeyError:
            logger.warning("Unknown intent from LLM: %s → UNCLASSIFIED", intent_str)
            intent = Intent.UNCLASSIFIED
            confidence = 0.0

        # secondary_intents
        secondary_strs = data.get("secondary_intents", [])
        secondary: list[Intent] = []
        for s in secondary_strs:
            try:
                secondary.append(Intent[s])
            except KeyError:
                logger.warning("Unknown secondary intent: %s (skipped)", s)

        return _RawPrediction(
            intent=intent,
            confidence=confidence,
            secondary_intents=secondary,
        )


class FallbackIntentClassifier(IntentClassifierBase):
    """Primary(LLM) + Fallback(Mock) 래핑 분류기.

    LLMIntentClassifier에서 raise된 예외를 catch하여
    MockIntentClassifier로 자동 전환한다.
    """

    def __init__(
        self,
        primary: IntentClassifierBase,
        fallback: IntentClassifierBase,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    def predict(self, text: str) -> _RawPrediction:
        """Primary → 실패 시 Fallback → 실패 시 UNCLASSIFIED."""
        try:
            return self._primary.predict(text)
        except Exception:
            logger.warning("LLM classifier failed, falling back to pattern-based", exc_info=True)

        try:
            return self._fallback.predict(text)
        except Exception:
            logger.error("Fallback classifier also failed", exc_info=True)

        return _RawPrediction(
            intent=Intent.UNCLASSIFIED,
            confidence=0.0,
            secondary_intents=[],
        )
