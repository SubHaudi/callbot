"""callbot.llm_engine — LLM 엔진 공개 API"""
from __future__ import annotations

from dataclasses import dataclass, field

from callbot.llm_engine.enums import VerificationStatus, ScopeType
from callbot.llm_engine.models import LLMResponse, VerificationResult, HallucinationMetrics, TokenUsage
from callbot.llm_engine.llm_engine import LLMEngine
from callbot.llm_engine.hallucination_verifier import HallucinationVerifier


@dataclass
class LLMEngineConfig:
    """LLM 엔진 통합 설정.

    Attributes:
        confidence_threshold: 환각 검증기 확신도 임계값 (기본 0.7, 범위 0.5~0.9)
        max_syllables: 일반 응답 최대 글자 수 (기본 80)
        max_syllables_legal: 법적 필수 안내 최대 음절 수 (기본 300)
    """
    confidence_threshold: float = 0.7
    max_syllables: int = 80
    max_syllables_legal: int = 300


__all__ = [
    "LLMEngine",
    "HallucinationVerifier",
    "LLMResponse",
    "VerificationResult",
    "VerificationStatus",
    "HallucinationMetrics",
    "ScopeType",
    "LLMEngineConfig",
    "TokenUsage",
]
