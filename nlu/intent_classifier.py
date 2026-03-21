"""callbot.nlu.intent_classifier — 의도 분류기

고객 발화에서 의도(Intent)와 엔티티(Entity)를 추출한다.
LLM 서비스에 의존하지 않는 독립 경량 모델(BERT 계열) 추상화 인터페이스를 제공하며,
Phase A에서는 키워드 기반 Mock 구현체를 사용한다.

Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9
"""
from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from callbot.nlu.enums import Intent, RelationType
from callbot.nlu.models import ClassificationResult, IntentRelation
from callbot.nlu.patterns import _PATTERN_RULES

logger = logging.getLogger(__name__)

# 확신도 임계값 범위
_THRESHOLD_MIN = 0.5
_THRESHOLD_MAX = 0.9
_THRESHOLD_DEFAULT = 0.7


# ---------------------------------------------------------------------------
# SessionContext
# ---------------------------------------------------------------------------

@dataclass
class SessionContext:
    """의도 분류기에 전달되는 세션 컨텍스트."""
    session_id: str
    turn_count: int = 0


# ---------------------------------------------------------------------------
# 추상 인터페이스
# ---------------------------------------------------------------------------

@dataclass
class _RawPrediction:
    """모델 원시 예측 결과."""
    intent: Intent
    confidence: float
    secondary_intents: list[Intent] = field(default_factory=list)


class IntentClassifierBase(ABC):
    """의도 분류 모델 추상 인터페이스.

    BERT 계열 경량 모델 선정 후 이 인터페이스를 구현한다.
    Phase A에서는 MockIntentClassifier를 사용한다.
    """

    @abstractmethod
    def predict(self, text: str) -> _RawPrediction:
        """텍스트에서 의도와 확신도를 예측한다."""
        ...


# ---------------------------------------------------------------------------
# 키워드 규칙 정의
# ---------------------------------------------------------------------------

# (키워드 목록, 매핑 의도) — 순서 중요: 더 구체적인 규칙이 앞에 위치
_KEYWORD_RULES: list[tuple[list[str], Intent]] = [
    (["요금제 변경"], Intent.PLAN_CHANGE),
    (["요금제"], Intent.PLAN_INQUIRY),
    (["요금"], Intent.BILLING_INQUIRY),
    (["납부"], Intent.PAYMENT_CHECK),
    (["데이터", "잔여"], Intent.DATA_USAGE_INQUIRY),
    (["부가서비스 해지", "부가 해지"], Intent.ADDON_CANCEL),
    (["상담사"], Intent.AGENT_CONNECT),
    (["불만"], Intent.COMPLAINT),
    (["해지"], Intent.CANCELLATION),
    (["종료", "끊"], Intent.END_CALL),
    (["빠르게", "느리게", "속도"], Intent.SPEED_CONTROL),
    (["다시", "반복"], Intent.REPEAT_REQUEST),
    (["잠깐", "대기"], Intent.WAIT_REQUEST),
]

# 복합 의도 관계 키워드
_RELATION_RULES: list[tuple[list[str], RelationType]] = [
    (["비교"], RelationType.COMPARISON),
    (["하고", "그리고"], RelationType.SEQUENTIAL),
    (["있으면", "이면"], RelationType.CONDITIONAL),
]


# ---------------------------------------------------------------------------
# Mock 구현체 (Phase A 테스트용)
# ---------------------------------------------------------------------------

class MockIntentClassifier(IntentClassifierBase):
    """키워드 기반 규칙 의도 분류기 (Phase A Mock).

    BERT 모델 선정 전 테스트 및 개발에 사용한다.
    """

    def __init__(self, confidence: float = 0.9) -> None:
        """
        Args:
            confidence: 키워드 매칭 시 반환할 고정 확신도 (기본값 0.9)
        """
        self._confidence = confidence

    def predict(self, text: str) -> _RawPrediction:
        """키워드 규칙으로 의도를 예측한다."""
        primary = self._match_primary_intent(text)
        secondary = self._match_secondary_intents(text, primary)
        return _RawPrediction(
            intent=primary,
            confidence=self._confidence,
            secondary_intents=secondary,
        )

    def _match_primary_intent(self, text: str) -> Intent:
        # Phase E: 정규식 패턴 우선 매칭
        for patterns, intent in _PATTERN_RULES:
            if any(p.search(text) for p in patterns):
                return intent
        # 폴백: 기존 키워드 매칭
        for keywords, intent in _KEYWORD_RULES:
            if any(kw in text for kw in keywords):
                return intent
        return Intent.UNCLASSIFIED

    def _match_secondary_intents(self, text: str, primary: Intent) -> list[Intent]:
        """복합 발화에서 추가 의도를 탐지한다."""
        secondary: list[Intent] = []
        for keywords, intent in _KEYWORD_RULES:
            if intent == primary:
                continue
            if any(kw in text for kw in keywords):
                secondary.append(intent)
        return secondary


# ---------------------------------------------------------------------------
# ModelLoadError
# ---------------------------------------------------------------------------

class ModelLoadError(Exception):
    """BERT 모델 로드 실패 시 발생하는 예외."""


# ---------------------------------------------------------------------------
# BertIntentClassifier
# ---------------------------------------------------------------------------

class BertIntentClassifier(IntentClassifierBase):
    """BERT 계열 경량 모델 기반 의도 분류기.

    파일 기반 초기화: __init__(model_path)
    테스트용 메모리 주입: from_components(model, tokenizer, ...)
    """

    def __init__(self, model_path: str) -> None:
        # Lazy imports to avoid hard dependency when torch/transformers not installed
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:
            raise ModelLoadError(f"필수 패키지 로드 실패 (torch/transformers): {exc}") from exc

        model_dir = Path(model_path)
        if not model_dir.exists():
            raise ModelLoadError(f"모델 경로가 존재하지 않습니다: {model_path}")

        # Load tokenizer and model
        try:
            tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
            model = AutoModelForSequenceClassification.from_pretrained(str(model_dir))
        except Exception as exc:
            raise ModelLoadError(f"모델 로드 실패: {exc}") from exc

        # Read model_info.json
        info_path = model_dir / "model_info.json"
        model_version = "unknown"
        if info_path.exists():
            try:
                info = json.loads(info_path.read_text(encoding="utf-8"))
                model_version = info.get("version", "unknown")
                raw_labels = info.get("label_order")
                if raw_labels is not None:
                    valid_values = {i.value for i in Intent}
                    invalid = [v for v in raw_labels if v not in valid_values]
                    if invalid:
                        raise ModelLoadError(
                            f"model_info.json의 label_order에 유효하지 않은 Intent 값이 있습니다: {invalid}"
                        )
                    intent_labels: list[Intent] = [Intent(v) for v in raw_labels]
                else:
                    logger.warning(
                        "model_info.json에 label_order가 없습니다. Intent 열거형 선언 순서를 fallback으로 사용합니다."
                    )
                    intent_labels = [i for i in Intent]
            except ModelLoadError:
                raise
            except Exception as exc:
                logger.warning("model_info.json 파싱 실패, fallback 사용: %s", exc)
                intent_labels = [i for i in Intent]
        else:
            logger.warning(
                "model_info.json이 없습니다. Intent 열거형 선언 순서를 fallback으로 사용합니다."
            )
            intent_labels = [i for i in Intent]

        model.eval()

        self._model = model
        self._tokenizer = tokenizer
        self._intent_labels: list[Intent] = intent_labels
        self._model_path: str = str(model_path)
        self._model_version: str = model_version
        self._loaded_at: str = datetime.now(timezone.utc).isoformat()

        # Warmup inference to eliminate cold-start latency on first predict()
        with torch.no_grad():
            dummy = tokenizer("워밍업", return_tensors="pt", truncation=True, max_length=16)
            model(**dummy)

    def predict(self, text: str) -> _RawPrediction:
        import torch
        # 빈 문자열 → UNCLASSIFIED 즉시 반환
        if not text:
            return _RawPrediction(Intent.UNCLASSIFIED, 0.0, [])

        inputs = self._tokenizer(text, return_tensors="pt", truncation=True, max_length=128)
        with torch.no_grad():
            outputs = self._model(**inputs)
        logits = outputs.logits  # shape: [1, num_classes]
        probs = torch.softmax(logits, dim=-1)[0]  # shape: [num_classes]

        intent_idx = int(torch.argmax(probs).item())
        confidence = float(probs[intent_idx].item())
        intent = self._intent_labels[intent_idx]

        # secondary candidates: top-k excluding primary, threshold >= 0.1
        k = min(3, len(self._intent_labels))
        top_values, top_indices = torch.topk(probs, k=k)
        secondary: list[Intent] = []
        for val, idx in zip(top_values.tolist(), top_indices.tolist()):
            if idx != intent_idx and val >= 0.1:
                secondary.append(self._intent_labels[idx])

        return _RawPrediction(intent=intent, confidence=confidence, secondary_intents=secondary)

    def get_model_info(self) -> dict:
        return {
            "model_path": self._model_path,
            "model_version": self._model_version,
            "loaded_at": self._loaded_at,
        }

    @classmethod
    def validate_training_data(cls, path: str) -> bool:
        """JSONL 파일을 읽어 학습 데이터 형식을 검증한다.

        Args:
            path: JSONL 파일 경로

        Returns:
            유효하면 True, 파일 없음/파싱 오류/형식 오류 시 False
        """
        try:
            records = []
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    records.append(json.loads(line))
            return cls._validate_data(records)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return False

    @classmethod
    def from_components(
        cls,
        model,
        tokenizer,
        intent_labels: list[Intent],
        model_path: str = "<injected>",
        model_version: str = "test",
    ) -> "BertIntentClassifier":
        """파일 I/O 없이 모델 컴포넌트를 직접 주입하여 인스턴스를 생성한다 (테스트용)."""
        instance = cls.__new__(cls)
        instance._model = model
        instance._tokenizer = tokenizer
        instance._intent_labels = intent_labels
        instance._model_path = model_path
        instance._model_version = model_version
        instance._loaded_at = datetime.now(timezone.utc).isoformat()
        return instance

    @staticmethod
    def _validate_data(records: list[dict]) -> bool:
        """메모리 기반 학습 데이터 검증 (property test용).

        Args:
            records: 각 레코드는 {"text": ..., "intent": ...} 형식

        Returns:
            유효하면 True, 형식 오류 또는 의도별 최소 건수 미달 시 False
        """
        try:
            valid_intent_values = {i.value for i in Intent}
            counts: dict[str, int] = {i.value: 0 for i in Intent}

            for record in records:
                if "text" not in record or "intent" not in record:
                    return False
                intent_val = record["intent"]
                if intent_val not in valid_intent_values:
                    return False
                counts[intent_val] += 1

            # 모든 의도가 최소 40건 이상이어야 함
            for intent_val in valid_intent_values:
                if counts[intent_val] < 40:
                    return False

            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# IntentClassifier
# ---------------------------------------------------------------------------

class IntentClassifier:
    """의도 분류기.

    classify(text, session_context) → ClassificationResult

    Args:
        model: 의도 분류 모델 (기본값: MockIntentClassifier)
        confidence_threshold: 확신도 임계값 (기본값 0.7, 범위 0.5~0.9)
    """

    @classmethod
    def from_env(cls) -> "IntentClassifier":
        """환경 변수 NLU_MODEL_PATH에 따라 적절한 모델을 선택하여 IntentClassifier를 반환한다.

        - NLU_MODEL_PATH 설정됨 → BertIntentClassifier(model_path) 사용
        - NLU_MODEL_PATH 미설정 → MockIntentClassifier() 사용 (기존 동작)

        Validates: Requirements 1.7, 6.3, 6.4
        """
        model_path = os.environ.get("NLU_MODEL_PATH")
        if model_path:
            return cls(model=BertIntentClassifier(model_path))
        return cls(model=MockIntentClassifier())

    def __init__(
        self,
        model: IntentClassifierBase | None = None,
        confidence_threshold: float = _THRESHOLD_DEFAULT,
    ) -> None:
        if not (_THRESHOLD_MIN <= confidence_threshold <= _THRESHOLD_MAX):
            raise ValueError(
                f"confidence_threshold must be in [{_THRESHOLD_MIN}, {_THRESHOLD_MAX}], "
                f"got {confidence_threshold}"
            )
        self._model = model or MockIntentClassifier()
        self.confidence_threshold = confidence_threshold

    def classify(self, text: str, session_context: SessionContext) -> ClassificationResult:
        """텍스트에서 의도와 엔티티를 추출한다.

        Args:
            text: PIF를 통과한 안전한 텍스트
            session_context: 활성 세션 컨텍스트

        Returns:
            ClassificationResult (불변 조건은 ClassificationResult.create()가 보장)
        """
        prediction = self._model.predict(text)
        intent_relations = self._detect_relations(text, prediction)

        return ClassificationResult.create(
            primary_intent=prediction.intent,
            confidence=prediction.confidence,
            secondary_intents=prediction.secondary_intents,
            intent_relations=intent_relations,
            entities=[],
            threshold=self.confidence_threshold,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _detect_relations(
        self, text: str, prediction: _RawPrediction
    ) -> list[IntentRelation]:
        """복합 의도 간 관계를 탐지한다."""
        relation_type = self._detect_relation_type(text)

        # 관계 키워드가 있고 secondary_intents가 없는 경우:
        # 동일 의도가 반복되는 복합 발화 (예: "지난달 요금이랑 이번달 요금 비교해줘")
        has_relation_keyword = any(
            any(kw in text for kw in keywords)
            for keywords, _ in _RELATION_RULES
        )

        if not prediction.secondary_intents:
            if has_relation_keyword:
                # 동일 의도 간 관계 (self-relation)
                return [
                    IntentRelation(
                        primary_intent=prediction.intent,
                        secondary_intent=prediction.intent,
                        relation_type=relation_type,
                    )
                ]
            return []

        relations: list[IntentRelation] = []
        for secondary in prediction.secondary_intents:
            relations.append(
                IntentRelation(
                    primary_intent=prediction.intent,
                    secondary_intent=secondary,
                    relation_type=relation_type,
                )
            )
        return relations

    def _detect_relation_type(self, text: str) -> RelationType:
        """텍스트에서 관계 유형을 탐지한다. 기본값은 SEQUENTIAL."""
        for keywords, relation_type in _RELATION_RULES:
            if any(kw in text for kw in keywords):
                return relation_type
        return RelationType.SEQUENTIAL
