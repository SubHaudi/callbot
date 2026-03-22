"""server.fake_llm — CI/테스트용 가짜 LLM 엔진.

MagicMock 대신 명시적 인터페이스로, 예상치 않은 호출은 AttributeError로 빠르게 실패.
"""
from __future__ import annotations


class FakeLLMEngine:
    """Bedrock 대신 사용하는 가짜 LLM. generate()만 구현."""

    def generate(self, *args, **kwargs) -> str:
        """항상 고정 응답을 반환."""
        return "테스트 응답입니다."
