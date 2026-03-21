"""callbot.nlu.tests.test_intent_classifier — 의도 분류기 단위 테스트

Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9
"""
from __future__ import annotations

import pytest

from callbot.nlu.enums import (
    ClassificationStatus,
    Intent,
    RelationType,
    SYSTEM_CONTROL_INTENTS,
    ESCALATION_INTENTS,
)
from callbot.nlu.intent_classifier import IntentClassifier, SessionContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def classifier() -> IntentClassifier:
    return IntentClassifier()


@pytest.fixture
def ctx() -> SessionContext:
    return SessionContext(session_id="test-session-001", turn_count=1)


# ---------------------------------------------------------------------------
# 4.1 의도 분류 확신도 경계 단위 테스트
# Validates: Requirements 2.5, 2.6
# ---------------------------------------------------------------------------

def test_confidence_below_threshold_returns_failure(classifier: IntentClassifier, ctx: SessionContext):
    """confidence=0.699 (threshold=0.7 미만) → FAILURE.
    Validates: Requirements 2.5, 2.6
    """
    result = classifier.classify("이번 달 요금이 얼마예요?", ctx)
    # mock 분류기는 키워드 매칭 시 confidence=0.9 반환하므로
    # threshold를 0.95로 높여 FAILURE 케이스를 테스트
    from callbot.nlu.intent_classifier import MockIntentClassifier
    mock = MockIntentClassifier(confidence=0.699)
    classifier_low = IntentClassifier(model=mock, confidence_threshold=0.7)
    result = classifier_low.classify("이번 달 요금이 얼마예요?", ctx)
    assert result.classification_status == ClassificationStatus.FAILURE


def test_confidence_at_threshold_returns_success(classifier: IntentClassifier, ctx: SessionContext):
    """confidence=0.7 (threshold=0.7 경계) → SUCCESS.
    Validates: Requirements 2.5
    """
    from callbot.nlu.intent_classifier import MockIntentClassifier
    mock = MockIntentClassifier(confidence=0.7)
    classifier_exact = IntentClassifier(model=mock, confidence_threshold=0.7)
    result = classifier_exact.classify("이번 달 요금이 얼마예요?", ctx)
    assert result.classification_status == ClassificationStatus.SUCCESS


def test_confidence_above_threshold_returns_success(classifier: IntentClassifier, ctx: SessionContext):
    """confidence=0.701 (threshold=0.7 초과) → SUCCESS.
    Validates: Requirements 2.5
    """
    from callbot.nlu.intent_classifier import MockIntentClassifier
    mock = MockIntentClassifier(confidence=0.701)
    classifier_above = IntentClassifier(model=mock, confidence_threshold=0.7)
    result = classifier_above.classify("이번 달 요금이 얼마예요?", ctx)
    assert result.classification_status == ClassificationStatus.SUCCESS


def test_unclassified_intent_returns_unclassified_status(classifier: IntentClassifier, ctx: SessionContext):
    """UNCLASSIFIED 의도 → ClassificationStatus.UNCLASSIFIED.
    Validates: Requirements 2.6
    """
    result = classifier.classify("오늘 날씨 어때요?", ctx)
    assert result.classification_status == ClassificationStatus.UNCLASSIFIED
    assert result.primary_intent == Intent.UNCLASSIFIED


def test_default_confidence_threshold_is_0_7(ctx: SessionContext):
    """기본 확신도 임계값은 0.7이다.
    Validates: Requirements 2.5
    """
    classifier = IntentClassifier()
    assert classifier.confidence_threshold == 0.7


def test_confidence_threshold_range_min(ctx: SessionContext):
    """확신도 임계값 최솟값 0.5 설정 가능.
    Validates: Requirements 2.5
    """
    classifier = IntentClassifier(confidence_threshold=0.5)
    assert classifier.confidence_threshold == 0.5


def test_confidence_threshold_range_max(ctx: SessionContext):
    """확신도 임계값 최댓값 0.9 설정 가능.
    Validates: Requirements 2.5
    """
    classifier = IntentClassifier(confidence_threshold=0.9)
    assert classifier.confidence_threshold == 0.9


# ---------------------------------------------------------------------------
# 4.2 시스템 제어 의도 플래그 단위 테스트
# Validates: Requirements 2.8
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected_intent", [
    ("전화 종료해줘", Intent.END_CALL),
    ("끊어줘", Intent.END_CALL),
    ("좀 빠르게 말해줘", Intent.SPEED_CONTROL),
    ("느리게 말해줘", Intent.SPEED_CONTROL),
    ("다시 말해줘", Intent.REPEAT_REQUEST),
    ("반복해줘", Intent.REPEAT_REQUEST),
    ("잠깐만요", Intent.WAIT_REQUEST),
    ("대기해줘", Intent.WAIT_REQUEST),
])
def test_system_control_intent_sets_flag(
    classifier: IntentClassifier, ctx: SessionContext, text: str, expected_intent: Intent
):
    """시스템 제어 의도 → is_system_control=True.
    Validates: Requirements 2.8
    """
    result = classifier.classify(text, ctx)
    assert result.primary_intent == expected_intent
    assert result.is_system_control is True


@pytest.mark.parametrize("text,expected_intent", [
    ("이번 달 요금이 얼마예요?", Intent.BILLING_INQUIRY),
    ("납부 확인해줘", Intent.PAYMENT_CHECK),
    ("상담사 연결해줘", Intent.AGENT_CONNECT),
])
def test_non_system_control_intent_clears_flag(
    classifier: IntentClassifier, ctx: SessionContext, text: str, expected_intent: Intent
):
    """업무 의도 → is_system_control=False.
    Validates: Requirements 2.8
    """
    result = classifier.classify(text, ctx)
    assert result.primary_intent == expected_intent
    assert result.is_system_control is False


# ---------------------------------------------------------------------------
# 4.3 즉시 에스컬레이션 플래그 단위 테스트
# Validates: Requirements 2.7
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected_intent", [
    ("해지하고 싶어요", Intent.CANCELLATION),
    ("불만이 있어요", Intent.COMPLAINT),
])
def test_escalation_intent_sets_flag(
    classifier: IntentClassifier, ctx: SessionContext, text: str, expected_intent: Intent
):
    """해지_문의, 불만_접수 → requires_immediate_escalation=True.
    Validates: Requirements 2.7
    """
    result = classifier.classify(text, ctx)
    assert result.primary_intent == expected_intent
    assert result.requires_immediate_escalation is True


@pytest.mark.parametrize("text,expected_intent", [
    ("이번 달 요금이 얼마예요?", Intent.BILLING_INQUIRY),
    ("요금제 변경하고 싶어요", Intent.PLAN_CHANGE),
    ("상담사 연결해줘", Intent.AGENT_CONNECT),
])
def test_non_escalation_intent_clears_flag(
    classifier: IntentClassifier, ctx: SessionContext, text: str, expected_intent: Intent
):
    """기타 의도 → requires_immediate_escalation=False.
    Validates: Requirements 2.7
    """
    result = classifier.classify(text, ctx)
    assert result.primary_intent == expected_intent
    assert result.requires_immediate_escalation is False


# ---------------------------------------------------------------------------
# 4.4 복합 의도 분류 단위 테스트
# Validates: Requirements 2.4
# ---------------------------------------------------------------------------

def test_comparison_relation_detected(classifier: IntentClassifier, ctx: SessionContext):
    """COMPARISON 관계 탐지: "지난달 요금이랑 이번달 요금 비교해줘".
    Validates: Requirements 2.4
    """
    result = classifier.classify("지난달 요금이랑 이번달 요금 비교해줘", ctx)
    relation_types = [r.relation_type for r in result.intent_relations]
    assert RelationType.COMPARISON in relation_types


def test_sequential_relation_detected(classifier: IntentClassifier, ctx: SessionContext):
    """SEQUENTIAL 관계 탐지: "요금 확인하고 요금제 변경해줘".
    Validates: Requirements 2.4
    """
    result = classifier.classify("요금 확인하고 요금제 변경해줘", ctx)
    relation_types = [r.relation_type for r in result.intent_relations]
    assert RelationType.SEQUENTIAL in relation_types


def test_conditional_relation_detected(classifier: IntentClassifier, ctx: SessionContext):
    """CONDITIONAL 관계 탐지: "더 싼 요금제 있으면 변경해줘".
    Validates: Requirements 2.4
    """
    result = classifier.classify("더 싼 요금제 있으면 변경해줘", ctx)
    relation_types = [r.relation_type for r in result.intent_relations]
    assert RelationType.CONDITIONAL in relation_types


def test_no_relation_for_simple_utterance(classifier: IntentClassifier, ctx: SessionContext):
    """단순 발화에는 intent_relations가 비어있다.
    Validates: Requirements 2.4
    """
    result = classifier.classify("이번 달 요금이 얼마예요?", ctx)
    assert result.intent_relations == []


# ---------------------------------------------------------------------------
# 기본 의도 분류 테스트
# Validates: Requirements 2.1, 2.2
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected_intent", [
    ("이번 달 요금이 얼마예요?", Intent.BILLING_INQUIRY),
    ("납부 확인해줘", Intent.PAYMENT_CHECK),
    ("요금제 변경하고 싶어요", Intent.PLAN_CHANGE),
    ("요금제 조회해줘", Intent.PLAN_INQUIRY),
    ("상담사 연결해줘", Intent.AGENT_CONNECT),
    ("불만이 있어요", Intent.COMPLAINT),
    ("해지하고 싶어요", Intent.CANCELLATION),
    ("전화 종료해줘", Intent.END_CALL),
    ("빠르게 말해줘", Intent.SPEED_CONTROL),
    ("다시 말해줘", Intent.REPEAT_REQUEST),
    ("잠깐만요", Intent.WAIT_REQUEST),
    # Phase C 추가
    ("데이터 잔여량 알려줘", Intent.DATA_USAGE_INQUIRY),
    ("잔여 데이터 확인해줘", Intent.DATA_USAGE_INQUIRY),
    ("부가서비스 해지해줘", Intent.ADDON_CANCEL),
    ("부가 해지하고 싶어요", Intent.ADDON_CANCEL),
])
def test_keyword_based_intent_classification(
    classifier: IntentClassifier, ctx: SessionContext, text: str, expected_intent: Intent
):
    """키워드 기반 의도 분류 정확성.
    Validates: Requirements 2.1, 2.2
    """
    result = classifier.classify(text, ctx)
    assert result.primary_intent == expected_intent


def test_classify_returns_classification_result(classifier: IntentClassifier, ctx: SessionContext):
    """classify()는 ClassificationResult를 반환한다."""
    from callbot.nlu.models import ClassificationResult
    result = classifier.classify("이번 달 요금이 얼마예요?", ctx)
    assert isinstance(result, ClassificationResult)


def test_classify_confidence_in_valid_range(classifier: IntentClassifier, ctx: SessionContext):
    """confidence는 0.0~1.0 범위이다."""
    result = classifier.classify("이번 달 요금이 얼마예요?", ctx)
    assert 0.0 <= result.confidence <= 1.0
