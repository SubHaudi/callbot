# LLM 기반 NLU 기능정의서

## 1. 개요
- 기존 패턴/키워드 기반 NLU(`MockIntentClassifier`)를 LLM 기반 인텐트 분류기로 업그레이드
- 핵심 가치: 패턴에 없는 자연어 표현도 정확하게 인텐트를 분류하여 대화 품질 향상

## 2. 배경 및 목적
- **문제**: `MockIntentClassifier`는 정규식 패턴 매칭 기반으로, 패턴에 등록되지 않은 표현은 `UNCLASSIFIED`로 분류됨. 새 표현을 지원하려면 패턴을 수동 추가해야 함.
- **As-Is**: `patterns.py`에 13개 인텐트의 정규식 패턴 정의 (전체 15개 인텐트 중 GENERAL_INQUIRY, UNCLASSIFIED 제외) → `MockIntentClassifier._match_primary_intent()`에서 순차 매칭 → 미매칭 시 키워드 규칙 폴백
- **To-Be**: `LLMIntentClassifier`가 Bedrock Claude를 호출하여 인텐트+엔티티를 JSON으로 추출. 기존 `IntentClassifierBase` 인터페이스를 구현하여 DI로 교체.
- **비즈니스 임팩트**: 인텐트 정확도 향상, 미분류 발화 감소, 패턴 유지보수 비용 제거

## 3. 용어 정의

| 용어 | 정의 |
|------|------|
| NLU | Natural Language Understanding. 사용자 발화에서 의도와 엔티티를 추출하는 처리 |
| LLM NLU | LLM(Large Language Model)을 사용한 NLU 처리 |
| IntentClassifierBase | 인텐트 분류 모델의 추상 인터페이스. `predict(text) → _RawPrediction` |
| MockIntentClassifier | 현재 사용 중인 패턴/키워드 기반 분류기 |
| LLMIntentClassifier | 새로 구현할 LLM 기반 분류기 |
| _RawPrediction | 분류 결과 데이터: intent, confidence, secondary_intents |
| 인텐트 | 15개 정의: BILLING_INQUIRY, PAYMENT_CHECK, PLAN_CHANGE, PLAN_INQUIRY, AGENT_CONNECT, GENERAL_INQUIRY, COMPLAINT, CANCELLATION, DATA_USAGE_INQUIRY, ADDON_CANCEL, END_CALL, SPEED_CONTROL, REPEAT_REQUEST, WAIT_REQUEST, UNCLASSIFIED |
| 폴백 | LLM 호출 실패 시 기존 MockIntentClassifier로 자동 전환하는 안전장치 |

## 4. 사용자 스토리

- **US-001**: 고객으로서, "이번 달 요금 좀 알려줄래요?"처럼 자연스러운 표현을 해도 AI가 정확히 의도를 파악했으면 좋겠다
- **US-002**: 고객으로서, "요금제 바꾸고 싶은데 데이터도 확인해줘"처럼 복합 요청도 처리됐으면 좋겠다
- **US-003**: 시스템 운영자로서, LLM 호출이 실패해도 기존 패턴 기반 분류로 서비스가 계속 동작했으면 좋겠다

## 5. 기능 요구사항

| ID | 요구사항 | 우선순위 | 관련 US |
|----|---------|---------|---------|
| FR-001 | `LLMIntentClassifier` 클래스: `IntentClassifierBase`를 구현하고, Bedrock Claude를 호출하여 인텐트+confidence를 반환 | P0 | US-001 |
| FR-002 | NLU 전용 프롬프트: 15개 인텐트 정의와 분류 기준을 포함한 시스템 프롬프트. JSON 형식으로 `{intent, confidence, secondary_intents}` 반환 요구 | P0 | US-001, US-002 |
| FR-003 | 복합 인텐트 처리: LLM JSON 응답의 `intent`(primary) + `secondary_intents`를 추출하여 `_RawPrediction`에 매핑 | P0 | US-002 |
| FR-004 | 폴백 메커니즘: LLM 호출 실패(타임아웃, API 에러, JSON 파싱 실패) 시 `MockIntentClassifier`로 자동 전환 | P0 | US-003 |
| FR-005 | Pipeline DI 교체: `server/pipeline.py`의 기본 classifier를 `LLMIntentClassifier`(폴백 포함)로 변경 | P0 | US-001 |
| FR-006 | 캐싱: 동일 발화에 대한 LLM 호출을 방지하는 인메모리 LRU 캐시 (최대 256항목, 서버 프로세스 수명 동안 유지) | P1 | US-003 |

## 6. 비기능 요구사항

| ID | 요구사항 | 기준 |
|----|---------|------|
| NFR-001 | LLM NLU 응답 시간 | P95 ≤ 2초 (Bedrock Claude Sonnet 4 기준) |
| NFR-002 | 폴백 전환 시간 | LLM 타임아웃 3초 → 폴백 포함 총 5초 이내 |
| NFR-003 | 테스트 커버리지 | 새 코드 80% 이상, 기존 테스트 100% 통과 |
| NFR-004 | 기존 인터페이스 호환 | `IntentClassifierBase.predict()` 시그니처 변경 없음 |

## 7. 기술 설계

### 아키텍처
- `LLMIntentClassifier(IntentClassifierBase)`: Bedrock Claude 호출 → JSON 파싱 → `_RawPrediction` 반환
- 기존 `LLMEngine`의 `BedrockService`를 재사용하여 Bedrock 호출
- `FallbackIntentClassifier(IntentClassifierBase)`: primary=LLM, fallback=Mock 래핑

### 변경 대상 파일
1. `nlu/llm_intent_classifier.py` — 신규: LLMIntentClassifier + FallbackIntentClassifier
2. `nlu/prompts.py` — 신규: NLU 전용 프롬프트 텍스트
3. `server/pipeline.py` — 수정: 기본 classifier를 FallbackIntentClassifier로 변경
4. `nlu/tests/test_llm_intent_classifier.py` — 신규: 테스트

### LLM NLU 프롬프트 설계
- 시스템 프롬프트: 15개 인텐트 정의 + 분류 규칙 + JSON 출력 형식
- 사용자 메시지: 고객 발화 텍스트
- 응답 형식: `{"intent": "BILLING_INQUIRY", "confidence": 0.95, "secondary_intents": ["PLAN_INQUIRY"]}`
- 인텐트 값은 반드시 영문 Enum name (`BILLING_INQUIRY` 등)으로 반환하도록 프롬프트에 지시

### FallbackIntentClassifier 흐름
1. `LLMIntentClassifier.predict(text)` 시도
2. 성공 → 결과 반환
3. 실패(Exception) → 로그 + `MockIntentClassifier.predict(text)` 폴백
4. 폴백도 실패 → `UNCLASSIFIED` confidence=0.0 반환

### 캐싱 (P1)
- `functools.lru_cache` 또는 dict 기반 LRU
- 키: 발화 텍스트 (정규화: strip + lower)
- 최대 256항목, 서버 프로세스 수명 동안 유지 (재시작 시 초기화)

## 8. 데이터 모델
- 변경 없음. 기존 `_RawPrediction`, `ClassificationResult` 그대로 사용.
- LLM 응답 JSON → `_RawPrediction` 매핑만 추가.

## 9. API 설계
- 외부 API 변경 없음.
- 내부: `LLMIntentClassifier.predict(text: str) → _RawPrediction`
- Bedrock 호출: 기존 `BedrockService.invoke()` 재사용

## 10. UI/UX 고려사항
- 사용자 화면 변경 없음
- 관리자 대시보드에서 인텐트 분류 결과 확인 가능 (기존 통화 기록에 포함)

## 11. 마일스톤 및 일정

| Phase | 내용 | 포함 FR | 예상 기간 |
|-------|------|---------|----------|
| 1 | LLMIntentClassifier + 프롬프트 + 폴백 + 테스트 | FR-001~005 | 60분 |
| 2 | LRU 캐시 + 성능 최적화 | FR-006 | 20분 |

## 12. 리스크 및 완화 방안

| ID | 리스크 | 확률 | 영향 | 완화 |
|----|--------|------|------|------|
| RISK-001 | LLM 응답 지연으로 전체 응답시간 증가 | M | M | 타임아웃 3초 + 폴백 자동 전환 |
| RISK-002 | LLM이 잘못된 JSON 형식 반환 | M | L | JSON 파싱 실패 시 폴백 + 프롬프트에 strict format 지시 |
| RISK-003 | LLM이 존재하지 않는 인텐트 반환 | L | L | Enum validation + 미매칭 시 UNCLASSIFIED 처리 |
| RISK-004 | Bedrock API 비용 증가 | M | L | 캐싱(FR-006)으로 중복 호출 방지 |

## 13. 성공 지표

| KPI | 목표 | 측정 방법 |
|-----|------|----------|
| 인텐트 분류 정확도 | 기존 패턴 대비 향상 | 테스트 시나리오 (자연어 변형 포함) |
| 미분류(UNCLASSIFIED) 비율 | 기존 대비 50% 이상 감소 | 테스트 시나리오 |
| 폴백 발동률 | ≤ 5% | 로깅으로 모니터링 |
| 기존 테스트 통과율 | 100% | pytest 전체 실행 |

## 14. 의존성
- AWS Bedrock (Claude Sonnet 4) — 기존 `BedrockService` 인프라 재사용
- 기존 `IntentClassifierBase` 인터페이스
- 기존 `MockIntentClassifier` (폴백용)

## 15. 범위 제외 사항
- BERT/경량 모델 학습 — `BertIntentClassifier`는 별도 Phase
- 실시간 인텐트 정확도 모니터링 대시보드
- 인텐트 정의 변경 (기존 15개 유지)
- Few-shot 예시 최적화 (향후 튜닝)
