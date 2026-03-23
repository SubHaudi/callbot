"""callbot.llm_engine.tests.test_integration — LLM 엔진 통합 테스트

LLM_엔진 → 환각_검증기 파이프라인 통합 테스트.
Validates: Requirements 1.1, 2.1, 2.4
"""
from __future__ import annotations

from datetime import datetime

import pytest

from callbot.llm_engine import (
    LLMEngine,
    HallucinationVerifier,
    LLMEngineConfig,
    VerificationStatus,
)
from callbot.llm_engine.llm_engine import MockLLMService
from callbot.llm_engine.hallucination_verifier import MockDBService
from callbot.nlu.enums import Intent
from callbot.nlu.models import ClassificationResult
from callbot.session.enums import AuthStatus
from callbot.session.models import SessionContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config() -> LLMEngineConfig:
    return LLMEngineConfig()


@pytest.fixture
def session() -> SessionContext:
    return SessionContext(
        session_id="integ-session-001",
        caller_id="010-9999-0000",
        is_authenticated=True,
        customer_info=None,
        auth_status=AuthStatus.SUCCESS,
        turns=[],
        business_turn_count=0,
        start_time=datetime.now(),
        tts_speed_factor=1.0,
        cached_billing_data=None,
        injection_detection_count=0,
        masking_restore_failure_count=0,
        plan_list_context=None,
        pending_intent=None,
        pending_classification=None,
    )


def make_classification(intent: Intent, confidence: float = 0.9) -> ClassificationResult:
    return ClassificationResult.create(primary_intent=intent, confidence=confidence)


# ---------------------------------------------------------------------------
# 통합 테스트 1: LLM_엔진 → 환각_검증기 파이프라인 (일반 대화 시나리오)
# Validates: Requirements 1.1, 2.1
# ---------------------------------------------------------------------------

class TestLLMEngineToVerifierPipeline:
    """LLM_엔진 → 환각_검증기 파이프라인 통합 테스트 (일반 대화 시나리오)."""

    def test_general_inquiry_pipeline_returns_pass(
        self, config: LLMEngineConfig, session: SessionContext
    ):
        """일반_문의 의도 → is_factual=False → 환각_검증기 PASS (is_skipped=True)."""
        engine = LLMEngine(llm_service=MockLLMService("안녕하세요, 무엇을 도와드릴까요?"))
        verifier = HallucinationVerifier(confidence_threshold=config.confidence_threshold)

        classification = make_classification(Intent.GENERAL_INQUIRY, confidence=0.9)
        llm_response = engine.generate_response(classification, session)

        assert llm_response.is_factual is False
        assert llm_response.requires_verification is False

        result = verifier.verify(llm_response, session)

        assert result.status == VerificationStatus.PASS
        assert result.is_skipped is True

    def test_pipeline_response_text_preserved_for_non_factual(
        self, config: LLMEngineConfig, session: SessionContext
    ):
        """비사실 기반 응답은 파이프라인 통과 후 원본 텍스트가 유지된다."""
        response_text = "안녕하세요, 무엇을 도와드릴까요?"
        engine = LLMEngine(llm_service=MockLLMService(response_text))
        verifier = HallucinationVerifier(confidence_threshold=config.confidence_threshold)

        classification = make_classification(Intent.GENERAL_INQUIRY, confidence=0.9)
        llm_response = engine.generate_response(classification, session)
        result = verifier.verify(llm_response, session)

        assert result.final_response == response_text
        assert result.original_response == response_text

    def test_complaint_intent_pipeline_returns_pass_skipped(
        self, config: LLMEngineConfig, session: SessionContext
    ):
        """불만_접수 의도 → is_factual=False → PASS, is_skipped=True."""
        engine = LLMEngine(llm_service=MockLLMService("불편을 드려 죄송합니다."))
        verifier = HallucinationVerifier(confidence_threshold=config.confidence_threshold)

        classification = make_classification(Intent.COMPLAINT, confidence=0.85)
        llm_response = engine.generate_response(classification, session)
        result = verifier.verify(llm_response, session)

        assert result.status == VerificationStatus.PASS
        assert result.is_skipped is True


# ---------------------------------------------------------------------------
# 통합 테스트 2: 과금 업무 캐시 저장 → 환각_검증기 캐시 참조
# Validates: Requirements 2.4
# ---------------------------------------------------------------------------

class TestBillingCachePipeline:
    """과금 업무 시 캐시 저장 → 환각_검증기 캐시 참조 통합 테스트."""

    def test_billing_inquiry_with_matching_cached_data_returns_pass(
        self, config: LLMEngineConfig, session: SessionContext
    ):
        """요금_조회 의도 + 캐시 데이터 일치 → PASS."""
        engine = LLMEngine(llm_service=MockLLMService("이번 달 요금은 55,000원입니다."))
        verifier = HallucinationVerifier(confidence_threshold=config.confidence_threshold)

        classification = make_classification(Intent.BILLING_INQUIRY, confidence=0.9)
        llm_response = engine.generate_response(classification, session)

        assert llm_response.is_factual is True

        # 캐시 데이터: LLM 응답과 일치하는 금액
        cached_data = {"billing_202607": {"amount": 55000}}
        result = verifier.verify(llm_response, session, cached_data=cached_data)

        assert result.status == VerificationStatus.PASS

    def test_billing_inquiry_with_mismatched_cached_data_returns_replaced(
        self, config: LLMEngineConfig, session: SessionContext
    ):
        """요금_조회 의도 + 캐시 데이터 불일치 → REPLACED."""
        # LLM이 45,000원이라고 응답하지만 실제는 55,000원
        engine = LLMEngine(llm_service=MockLLMService("이번 달 요금은 45,000원입니다."))
        verifier = HallucinationVerifier(confidence_threshold=config.confidence_threshold)

        classification = make_classification(Intent.BILLING_INQUIRY, confidence=0.9)
        llm_response = engine.generate_response(classification, session)

        cached_data = {"billing_202607": {"amount": 55000}}
        result = verifier.verify(llm_response, session, cached_data=cached_data)

        assert result.status == VerificationStatus.REPLACED
        assert result.final_response != result.original_response
        assert len(result.discrepancies) >= 1

    def test_payment_check_with_cached_data_no_requery(
        self, config: LLMEngineConfig, session: SessionContext
    ):
        """납부_확인 의도 + cached_data 제공 → DB 재조회 없이 검증 수행."""
        # db_service가 없어도 cached_data로 검증 가능해야 함
        engine = LLMEngine(llm_service=MockLLMService("납부 금액은 33,000원입니다."))
        verifier = HallucinationVerifier(
            confidence_threshold=config.confidence_threshold,
            db_service=None,  # DB 서비스 없음
        )

        classification = make_classification(Intent.PAYMENT_CHECK, confidence=0.9)
        llm_response = engine.generate_response(classification, session)

        cached_data = {"payment_202607": {"amount": 33000}}
        result = verifier.verify(llm_response, session, cached_data=cached_data)

        # cached_data와 일치하므로 PASS
        assert result.status == VerificationStatus.PASS


# ---------------------------------------------------------------------------
# 통합 테스트 3: 확신도 미달 → BLOCKED → 상담사 연결 흐름
# Validates: Requirements 2.1, 2.2
# ---------------------------------------------------------------------------

class TestLowConfidenceBlockedFlow:
    """확신도 미달 → BLOCKED → 상담사 연결 흐름 통합 테스트."""

    def test_low_confidence_factual_response_is_blocked(
        self, config: LLMEngineConfig, session: SessionContext
    ):
        """확신도 미달(0.5) + 사실 기반 의도 → BLOCKED."""
        engine = LLMEngine(llm_service=MockLLMService("요금은 55,000원입니다."))
        verifier = HallucinationVerifier(confidence_threshold=config.confidence_threshold)

        # 낮은 확신도로 분류된 요금 조회
        classification = make_classification(Intent.BILLING_INQUIRY, confidence=0.5)
        llm_response = engine.generate_response(classification, session)

        assert llm_response.confidence == 0.5

        result = verifier.verify(llm_response, session)

        assert result.status == VerificationStatus.BLOCKED
        assert result.block_reason == "확신도_미달"

    def test_low_confidence_non_factual_response_is_also_blocked(
        self, config: LLMEngineConfig, session: SessionContext
    ):
        """확신도 미달(0.6) + 비사실 기반 의도 → BLOCKED (is_factual 무관)."""
        engine = LLMEngine(llm_service=MockLLMService("안녕하세요."))
        verifier = HallucinationVerifier(confidence_threshold=config.confidence_threshold)

        classification = make_classification(Intent.GENERAL_INQUIRY, confidence=0.6)
        llm_response = engine.generate_response(classification, session)

        result = verifier.verify(llm_response, session)

        assert result.status == VerificationStatus.BLOCKED
        assert result.block_reason == "확신도_미달"

    def test_blocked_result_triggers_agent_connect_signal(
        self, config: LLMEngineConfig, session: SessionContext
    ):
        """BLOCKED 결과는 상담사 연결 트리거 조건을 충족한다 (block_reason 존재)."""
        engine = LLMEngine(llm_service=MockLLMService("요금은 55,000원입니다."))
        verifier = HallucinationVerifier(confidence_threshold=config.confidence_threshold)

        classification = make_classification(Intent.BILLING_INQUIRY, confidence=0.3)
        llm_response = engine.generate_response(classification, session)
        result = verifier.verify(llm_response, session)

        # 오케스트레이터가 상담사 연결을 트리거하는 조건 검증
        assert result.status == VerificationStatus.BLOCKED
        assert result.block_reason is not None
        assert result.original_response is not None

    def test_db_failure_also_triggers_blocked(
        self, config: LLMEngineConfig, session: SessionContext
    ):
        """DB 장애 시에도 BLOCKED → 상담사 연결 흐름."""
        engine = LLMEngine(llm_service=MockLLMService("요금은 55,000원입니다."))
        db_service = MockDBService(raise_error=True)
        verifier = HallucinationVerifier(
            confidence_threshold=config.confidence_threshold,
            db_service=db_service,
        )

        classification = make_classification(Intent.BILLING_INQUIRY, confidence=0.9)
        llm_response = engine.generate_response(classification, session)

        # cached_data=None → db_service 조회 시도 → 장애 → BLOCKED
        result = verifier.verify(llm_response, session, cached_data=None)

        assert result.status == VerificationStatus.BLOCKED
        assert result.block_reason == "DB_장애"


# ---------------------------------------------------------------------------
# 통합 테스트 4: LLMEngineConfig 설정 통합
# Validates: Requirements 1.2, 2.6
# ---------------------------------------------------------------------------

class TestLLMEngineConfigIntegration:
    """LLMEngineConfig 설정이 엔진과 검증기에 올바르게 적용되는지 통합 테스트."""

    def test_default_config_values(self):
        """기본 설정값 확인."""
        config = LLMEngineConfig()
        assert config.confidence_threshold == 0.7
        assert config.max_syllables == 80
        assert config.max_syllables_legal == 300

    def test_custom_config_applied_to_verifier(self, session: SessionContext):
        """커스텀 설정(threshold=0.8)이 검증기에 적용된다."""
        config = LLMEngineConfig(confidence_threshold=0.8)
        engine = LLMEngine(llm_service=MockLLMService("안녕하세요."))
        verifier = HallucinationVerifier(confidence_threshold=config.confidence_threshold)

        # confidence=0.75 → threshold=0.8 미달 → BLOCKED
        classification = make_classification(Intent.GENERAL_INQUIRY, confidence=0.75)
        llm_response = engine.generate_response(classification, session)
        result = verifier.verify(llm_response, session)

        assert result.status == VerificationStatus.BLOCKED

    def test_public_api_imports_work(self):
        """공개 API 임포트가 정상 동작한다."""
        from callbot.llm_engine import (
            LLMEngine,
            HallucinationVerifier,
            LLMResponse,
            VerificationResult,
            VerificationStatus,
            HallucinationMetrics,
            ScopeType,
            LLMEngineConfig,
        )
        assert LLMEngine is not None
        assert HallucinationVerifier is not None
        assert LLMResponse is not None
        assert VerificationResult is not None
        assert VerificationStatus is not None
        assert HallucinationMetrics is not None
        assert ScopeType is not None
        assert LLMEngineConfig is not None
