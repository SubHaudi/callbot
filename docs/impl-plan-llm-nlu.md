# LLM 기반 NLU 구현 계획

## 구현 원칙
- TDD 사이클: Red → Green → Refactor
- Tidy First: 구조적 변경 먼저, 행위적 변경은 그 다음
- 기존 `IntentClassifierBase` 인터페이스 변경 없음 (NFR-004)
- 기존 테스트 100% 통과 유지

## 요구사항 추적 매트릭스
| 요구사항 ID | 요구사항 요약 | 관련 태스크 |
|-------------|-------------|-------------|
| FR-001 | LLMIntentClassifier | TASK-02, TASK-03 |
| FR-002 | NLU 전용 프롬프트 | TASK-01, TASK-03 |
| FR-003 | 복합 인텐트 JSON 추출 | TASK-03, TASK-04 |
| FR-004 | 폴백 메커니즘 | TASK-05, TASK-06 |
| FR-005 | Pipeline DI 교체 | TASK-07, TASK-08 |
| FR-006 | LRU 캐싱 | TASK-09, TASK-10 |
| NFR-003 | 테스트 커버리지 | 전체 |
| NFR-004 | 인터페이스 호환 | TASK-01 |
| NFR-001 | 응답시간 P95 ≤ 2초 | TASK-03 (timeout=3s) |
| NFR-002 | 폴백 전환 5초 이내 | TASK-06, TASK-11 |

## 태스크 목록

### TASK-01: NLU 프롬프트 모듈 (Structural)
- **설명**: `nlu/prompts.py` 생성. 15개 인텐트 정의 + 분류 규칙 + JSON 형식 지시를 포함한 시스템 프롬프트 텍스트 상수.
- **의존성**: 없음
- **완료 기준**: 파일 존재, import 가능, 기존 테스트 통과
- **커밋**: "structural: add NLU prompt template in nlu/prompts.py"

### TASK-02: LLMIntentClassifier 테스트 (Red)
- **설명**: `nlu/tests/test_llm_intent_classifier.py` 생성. Bedrock 호출을 Mock하여:
  - 정상 JSON 반환 → `_RawPrediction` 매핑 검증
  - 복합 인텐트(secondary_intents) 추출 검증
  - 잘못된 JSON → Exception 발생 검증
  - 존재하지 않는 인텐트명 → UNCLASSIFIED 처리 검증
  - 타임아웃 → Exception 발생 검증
- **의존성**: TASK-01
- **완료 기준**: 테스트가 실패하는 상태 (Red)
- **커밋**: "behavioral(red): add LLMIntentClassifier tests"

### TASK-03: LLMIntentClassifier 구현 (Green)
- **설명**: `nlu/llm_intent_classifier.py` 생성. `IntentClassifierBase`를 구현:
  - `__init__(bedrock_service, model_id, timeout)` — Bedrock 서비스 DI
  - `predict(text) → _RawPrediction` — 프롬프트 조합 → Bedrock 호출 → JSON 파싱 → Enum 매핑
  - JSON 파싱 실패 시 ValueError raise
  - 미매칭 인텐트 → UNCLASSIFIED, confidence=0.0
- **의존성**: TASK-02
- **완료 기준**: TASK-02 테스트 전부 통과 (Green)
- **커밋**: "behavioral(green): implement LLMIntentClassifier"

### TASK-04: LLMIntentClassifier 리팩토링 (Refactor)
- **설명**: JSON 파싱 로직 분리, 에러 처리 정리, 로깅 추가
- **의존성**: TASK-03
- **완료 기준**: 모든 테스트 통과, 코드 품질 개선
- **커밋**: "structural: refactor LLMIntentClassifier JSON parsing"

### TASK-05: FallbackIntentClassifier 테스트 (Red)
- **설명**: `test_llm_intent_classifier.py`에 추가:
  - LLM 성공 → LLM 결과 반환
  - LLM 실패(Exception) → Mock 결과 반환
  - LLM + Mock 모두 실패 → UNCLASSIFIED 반환
- **의존성**: TASK-04
- **완료 기준**: 폴백 테스트가 실패 (Red)
- **커밋**: "behavioral(red): add FallbackIntentClassifier tests"

### TASK-06: FallbackIntentClassifier 구현 (Green)
- **설명**: `nlu/llm_intent_classifier.py`에 `FallbackIntentClassifier(IntentClassifierBase)` 추가:
  - `__init__(primary: IntentClassifierBase, fallback: IntentClassifierBase)`
  - `predict(text)` → try primary → except → fallback → except → UNCLASSIFIED
  - 폴백 시 warning 로그
- **의존성**: TASK-05
- **완료 기준**: 폴백 테스트 통과 (Green)
- **커밋**: "behavioral(green): implement FallbackIntentClassifier"

### TASK-07: Pipeline DI 교체 테스트 (Red)
- **설명**: `server/tests/test_pipeline.py`에 추가:
  - Pipeline 기본 생성 시 classifier가 FallbackIntentClassifier 타입인지 확인
  - 기존 DI 주입 테스트는 그대로 유지
- **의존성**: TASK-06
- **완료 기준**: 새 테스트 실패 (Red)
- **커밋**: "behavioral(red): add pipeline default classifier test"

### TASK-08: Pipeline DI 교체 구현 (Green)
- **설명**: `server/pipeline.py`의 `intent_classifier is None` 분기를 수정:
  - `LLMIntentClassifier` + `MockIntentClassifier` → `FallbackIntentClassifier`로 래핑
  - BedrockService는 기존 `llm_engine`에서 재사용하거나 새로 생성
- **의존성**: TASK-07
- **완료 기준**: 전체 테스트 통과 (Green)
- **커밋**: "behavioral(green): wire FallbackIntentClassifier into pipeline"

### TASK-09: LRU 캐시 테스트 (Red)
- **설명**: `test_llm_intent_classifier.py`에 추가:
  - 동일 발화 2회 호출 → Bedrock 1회만 호출 검증
  - 다른 발화 → 각각 Bedrock 호출 검증
  - strip/lower 정규화 동작 검증
- **의존성**: TASK-08
- **완료 기준**: 캐시 테스트 실패 (Red)
- **커밋**: "behavioral(red): add LLM NLU cache tests"

### TASK-10: LRU 캐시 구현 (Green)
- **설명**: `LLMIntentClassifier`에 dict 기반 커스텀 LRU 캐시 적용:
  - `predict()` 내부에서 정규화(strip+lower) → `self._cache` dict 조회
  - 캐시 히트 시 Bedrock 호출 건너뜀
  - `collections.OrderedDict` 기반, maxsize=256 초과 시 oldest eviction
  - `self` 인스턴스에 귀속되어 GC 안전
- **의존성**: TASK-09
- **완료 기준**: 전체 테스트 통과 (Green)
- **커밋**: "behavioral(green): add LRU cache to LLMIntentClassifier"

### TASK-11: 전체 검증 + 배포 (Behavioral)
- **설명**: 
  1. 전체 pytest 실행 → 통과 확인
  2. Git push
  3. deploy.sh 배포
- **의존성**: TASK-10
- **커밋**: "chore: deploy LLM NLU feature"

## 태스크 의존성 그래프
```
TASK-01 → TASK-02 → TASK-03 → TASK-04
                                    ↓
              TASK-05 → TASK-06 → TASK-07 → TASK-08
                                                ↓
                              TASK-09 → TASK-10 → TASK-11
```

## 테스트 전략
- **단위 테스트**: LLMIntentClassifier (Bedrock Mock), FallbackIntentClassifier, 캐싱
- **통합 테스트**: Pipeline에서 FallbackIntentClassifier 동작
- **기존 테스트**: 100% 통과 유지 (서버 변경은 DI 기본값만)
