"""callbot.llm_engine.llm_engine — LLM 엔진 핵심 로직"""
from __future__ import annotations

import time
import yaml
from abc import ABC, abstractmethod
from typing import Optional

from callbot.nlu.enums import Intent
from callbot.nlu.models import ClassificationResult
from callbot.session.models import SessionContext
from callbot.llm_engine.enums import ScopeType
from callbot.llm_engine.models import LLMResponse
from callbot.llm_engine.prompt_loader import PromptLoader as BasePromptLoader

_FACTUAL_INTENTS: frozenset[Intent] = frozenset({
    Intent.BILLING_INQUIRY,
    Intent.PAYMENT_CHECK,
    Intent.PLAN_CHANGE,
    Intent.PLAN_INQUIRY,
})

_MAX_SYLLABLES_DEFAULT = 150
_MAX_SYLLABLES_LEGAL = 300
_END_CALL_SIGNALS: list[str] = ["끊을게요", "종료", "그만", "됐어요"]
_SYSTEM_PROMPT_FALLBACK = "죄송합니다, 다시 말씀해 주시겠어요?"
_ROLE_DEVIATION_FALLBACK = "죄송합니다, 통신 관련 문의만 도와드릴 수 있습니다."


class LLMServiceBase(ABC):
    """LLM 서비스 추상 인터페이스."""

    @abstractmethod
    def generate(self, system_prompt: str, user_message: str) -> str: ...


class MockLLMService(LLMServiceBase):
    """테스트용 Mock LLM 서비스."""

    def __init__(self, response: str = "안녕하세요, 무엇을 도와드릴까요?") -> None:
        self._response = response

    def generate(self, system_prompt: str, user_message: str) -> str:
        return self._response


class ResponseSplitter:
    """응답 텍스트를 문장 경계에서 분할."""

    _SENTENCE_ENDINGS = (".", "?", "!", "。")

    def split(self, text: str, max_syllables: int = 150) -> list[str]:
        if len(text) <= max_syllables:
            return [text]
        best_split = -1
        for i in range(min(max_syllables, len(text))):
            if text[i] in self._SENTENCE_ENDINGS:
                best_split = i + 1
        if best_split > 0:
            first = text[:best_split].strip()
            rest = text[best_split:].strip()
        else:
            first = text[:max_syllables]
            rest = text[max_syllables:]
        result = [first]
        if rest:
            result.extend(self.split(rest, max_syllables))
        return result


class PromptLoader:
    """YAML 파일에서 의도별 시스템 프롬프트를 로드하는 유틸리티."""

    def __init__(self, file_path: str) -> None:
        self._file_path = file_path
        self._data: dict[str, str] = self.load()

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "PromptLoader":
        """테스트용: 파일 없이 dict로 직접 초기화."""
        instance = cls.__new__(cls)
        instance._file_path = ""
        instance._data = data
        return instance

    def load(self) -> dict[str, str]:
        """YAML 파일 로드. 실패 시 빈 dict 반환 (예외 없음)."""
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def get_prompt(self, intent_key: str) -> Optional[str]:
        """intent_key에 해당하는 프롬프트 반환. 없으면 default 키 반환, 그것도 없으면 None."""
        return self._data.get(intent_key) or self._data.get("default")


class LLMEngine:
    """LLM 기반 응답 생성 엔진."""

    def __init__(
        self,
        llm_service: Optional[LLMServiceBase] = None,
        prompt_loader: Optional[BasePromptLoader] = None,
    ) -> None:
        self.llm_service: LLMServiceBase = llm_service or MockLLMService()
        self._base_prompt_loader = prompt_loader or BasePromptLoader()
        self.SYSTEM_PROMPT_KEYWORDS: list[str] = ["당신은 AI", "시스템 프롬프트"]
        self.ROLE_DEVIATION_PATTERNS: list[str] = ["```python", "```java", "코드를 작성"]
        self._splitter = ResponseSplitter()

    def generate_response(
        self,
        classification: ClassificationResult,
        session: SessionContext,
        is_legal_required: bool = False,
        customer_text: str = "",
    ) -> LLMResponse:
        """자연어 응답 생성."""
        start = time.monotonic()
        intent = classification.primary_intent
        is_factual = self._determine_is_factual(intent)

        system_prompt = self._build_system_prompt(session)
        user_message = self._build_user_message(classification, customer_text)

        raw_response = self.llm_service.generate(system_prompt, user_message)
        processed = self._post_process(raw_response)

        max_len = _MAX_SYLLABLES_LEGAL if is_legal_required else _MAX_SYLLABLES_DEFAULT
        if len(processed) > max_len:
            processed = processed[:max_len]

        elapsed_ms = int((time.monotonic() - start) * 1000)
        return LLMResponse(
            text=processed,
            confidence=classification.confidence,
            is_factual=is_factual,
            requires_verification=is_factual,
            is_legal_required=is_legal_required,
            remaining_legal_info=None,
            processing_time_ms=elapsed_ms,
        )

    def handle_ambiguous_input(self, text: str, session: SessionContext) -> str:
        return "죄송합니다, 말씀하신 내용을 정확히 이해하지 못했습니다. 다시 한번 말씀해 주시겠어요?"

    def check_end_call_intent(self, text: str, session: SessionContext) -> bool:
        return any(signal in text for signal in _END_CALL_SIGNALS)

    def handle_out_of_scope(
        self, text: str, session: SessionContext, scope_type: ScopeType
    ) -> str:
        if scope_type == ScopeType.NON_TELECOM:
            return "저는 통신 관련 문의를 도와드리고 있습니다. 통신 서비스에 관해 궁금하신 점이 있으시면 말씀해 주세요."
        return "해당 문의는 상담사를 통해 도움을 드릴 수 있습니다. 상담사에게 연결해 드릴까요?"

    def generate_plan_list_response(
        self,
        plans: list,
        current_plan: dict,
        page: int = 0,
    ) -> str:
        """요금제 목록 음성 채널 최적화 안내 — 3개씩 페이징."""
        page_size = 3
        total_pages = max(1, (len(plans) + page_size - 1) // page_size)
        page = min(page, total_pages - 1)
        start = page * page_size
        page_plans = plans[start: start + page_size]

        items = []
        for i, plan in enumerate(page_plans, start=1):
            fee_str = f"{plan['monthly_fee']:,}"
            items.append(f"{i}. {plan['name']} (월 {fee_str}원)")

        return "변경 가능한 요금제 목록입니다. " + " ".join(items)

    def generate_change_confirmation(
        self,
        before_plan: dict,
        after_plan: dict,
    ) -> str:
        """요금제 변경 동의 확인 정보 생성."""
        diff = after_plan["monthly_fee"] - before_plan["monthly_fee"]
        diff_abs = abs(diff)
        direction = "증가" if diff >= 0 else "감소"
        return (
            f"요금제 변경 확인입니다. "
            f"현재: {before_plan['name']} (월 {before_plan['monthly_fee']:,}원) → "
            f"변경: {after_plan['name']} (월 {after_plan['monthly_fee']:,}원). "
            f"월 {diff_abs:,}원 {direction}. "
            f"위약금: {before_plan['penalty']:,}원. "
            f"적용 시점: {after_plan['effective_date']}."
        )

    def _determine_is_factual(self, intent: Intent) -> bool:
        return intent in _FACTUAL_INTENTS

    def _build_system_prompt(self, session: SessionContext) -> str:
        return self._base_prompt_loader.base_prompt

    def _build_user_message(self, classification: ClassificationResult, customer_text: str) -> str:
        intent_label = classification.primary_intent.value
        if customer_text:
            return f"[의도: {intent_label}] {customer_text}"
        return f"[의도: {intent_label}]"

    def _post_process(self, response: str) -> str:
        for keyword in self.SYSTEM_PROMPT_KEYWORDS:
            if keyword in response:
                return _SYSTEM_PROMPT_FALLBACK
        for pattern in self.ROLE_DEVIATION_PATTERNS:
            if pattern in response:
                return _ROLE_DEVIATION_FALLBACK
        return response
