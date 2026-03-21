# Phase E: NLU 고도화 구현 계획

## 구현 원칙
- TDD 사이클: Red → Green → Refactor
- Tidy First: 구조적 변경과 행위적 변경을 분리
- 구조적 변경 먼저, 행위적 변경은 그 다음
- 각 커밋은 구조적 또는 행위적 중 하나만 포함

## 요구사항 추적 매트릭스

| 요구사항 ID | 요구사항 요약 | 관련 태스크 |
|-------------|-------------|-------------|
| FR-001 | 인텐트별 구어체 패턴 5개+ | TASK-003, TASK-004 |
| FR-002 | 조사 변형 정규식 처리 | TASK-003, TASK-004 |
| FR-003 | 줄임말/약어 패턴 | TASK-003, TASK-004 |
| FR-004 | pending_intent 중 새 인텐트 → 전환 확인 | TASK-007, TASK-008 |
| FR-005 | 전환 확인 "네" → 기존 취소 + 새 인텐트 | TASK-009, TASK-010 |
| FR-006 | 전환 확인 "아니" → 기존 유지 | TASK-009, TASK-010 |
| FR-007 | 시스템 인텐트 즉시 처리 (전환 확인 없음) | TASK-011, TASK-012 |
| FR-008 | UNCLASSIFIED 50% 감소 | TASK-013, TASK-014 |
| NFR-001 | NLU 분류 5ms 이내 | TASK-015 |
| NFR-002 | 전환 시 세션 상태 완전 정리 | TASK-009, TASK-010 |
| NFR-003 | 기존 테스트 회귀 없음 | 전체 |
| NFR-004 | ReDoS 취약점 없음 | TASK-015 |

## 구현 순서 개요

### E-1: 구어체 패턴 인프라 (TASK-001~004)
1. Structural: nlu/patterns.py 패턴 정의 파일 생성
2. Structural: MockIntentClassifier에 정규식 매칭 인터페이스 준비
3. Red: 구어체 발화 분류 실패 테스트
4. Green: _PATTERN_RULES 구현 + 정규식 매칭

### E-2: MockIntentClassifier 패턴 통합 (TASK-005~006)
5. Red: 기존 키워드 + 새 패턴 통합 테스트
6. Green: _match_primary_intent() 정규식 우선 매칭 구현

### E-3: 인텐트 전환 핸들러 (TASK-007~012)
7. Structural: SessionContext에 pending_switch_intent 필드 추가
8. Red: 다단계 플로우 중 새 인텐트 감지 → 전환 확인 테스트
9. Green: _handle_intent_switch() 구현
10. Red: 전환 확인 Yes/No 처리 테스트
11. Green: 전환 확인 응답 처리 구현
12. Red: 시스템 인텐트 즉시 처리 테스트
13. Green: 시스템 인텐트 예외 분기 구현

### E-4: 검증 + 벤치마크 (TASK-013~015)
14. Red: 구어체 테스트셋 30개 발화 인식률 테스트
15. Green: 패턴 튜닝으로 80% 달성
16. Behavioral: NLU 성능 벤치마크 (5ms, ReDoS)

## 태스크 목록

### TASK-001: 패턴 정의 파일 생성
- **변경 유형**: Structural
- **설명**: `nlu/patterns.py` 파일 생성. 인텐트별 정규식 패턴을 `_PATTERN_RULES` 리스트로 정의
- **의존성**: 없음
- **관련 요구사항**: FR-001, FR-002, FR-003
- **완료 기준**: 파일 존재, import 가능, 기존 테스트 통과
- **커밋 메시지**: "structural: create nlu/patterns.py with _PATTERN_RULES"

### TASK-002: MockIntentClassifier 정규식 인터페이스 준비
- **변경 유형**: Structural
- **설명**: `_match_primary_intent()`에서 `_PATTERN_RULES`를 import하고 매칭할 준비. 아직 동작 변경 없음.
- **의존성**: TASK-001
- **완료 기준**: 기존 테스트 통과 (동작 변경 없음)
- **커밋 메시지**: "structural: prepare regex matching interface in MockIntentClassifier"

### TASK-003: 구어체 분류 테스트 (Red)
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **테스트**: 구어체 발화 ("요금 좀 알려줘", "그거 얼마야", "데이터 남은거", "부가 좀 빼줘", "요금제 바꿀래") → 올바른 인텐트 분류 확인. 현재 UNCLASSIFIED로 분류됨 → 실패
- **의존성**: TASK-002
- **관련 요구사항**: FR-001, FR-002, FR-003
- **커밋 메시지**: "behavioral(red): add colloquial utterance classification tests"

### TASK-004: 구어체 패턴 매칭 구현 (Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **구현**: `_match_primary_intent()`에서 `_PATTERN_RULES` 정규식을 먼저 매칭, 실패 시 기존 `_KEYWORD_RULES` 폴백
- **의존성**: TASK-003
- **관련 요구사항**: FR-001, FR-002, FR-003
- **완료 기준**: TASK-003 테스트 통과 + 기존 테스트 통과
- **커밋 메시지**: "behavioral(green): implement regex pattern matching for colloquial utterances"

### TASK-005: 키워드+패턴 통합 테스트 (Red)
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **테스트**: 기존 키워드 발화와 구어체 발화가 모두 올바르게 분류되는지 통합 확인. 엣지 케이스 (조사 변형, 줄임말) 포함
- **의존성**: TASK-004
- **커밋 메시지**: "behavioral(red): add keyword+pattern integration tests"

### TASK-006: 통합 매칭 최적화 (Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **구현**: 패턴 우선순위 조정, 오매칭 수정
- **의존성**: TASK-005
- **커밋 메시지**: "behavioral(green): optimize integrated pattern matching"

### TASK-007: SessionContext pending_switch_intent 필드 추가
- **변경 유형**: Structural
- **설명**: `session/models.py` SessionContext에 `pending_switch_intent: Optional[Intent]` 필드 추가 (기본값 None). `Intent` enum 타입 사용.
- **의존성**: 없음 (E-1과 병렬 가능)
- **관련 요구사항**: FR-004
- **완료 기준**: 기존 테스트 통과
- **커밋 메시지**: "structural: add pending_switch_intent field to SessionContext"

### TASK-008: 인텐트 전환 감지 테스트 (Red)
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **테스트**: pending_intent="PLAN_CHANGE_SELECT" 상태에서 "부가서비스 해지해줘" 발화 → 전환 확인 메시지 반환 확인
- **의존성**: TASK-007, TASK-004
- **관련 요구사항**: FR-004
- **커밋 메시지**: "behavioral(red): add intent switch detection tests"

### TASK-008b: 인텐트 전환 감지 구현 (Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **구현**: `TurnPipeline._handle_intent_switch()` — pending_intent 상태에서 NLU 분류 실행, 새 인텐트 감지 시 전환 확인 메시지 반환. `pending_switch_intent`에 새 인텐트 저장.
- **의존성**: TASK-008
- **관련 요구사항**: FR-004
- **완료 기준**: TASK-008 테스트 통과
- **커밋 메시지**: "behavioral(green): implement intent switch detection"

### TASK-009: 전환 확인 응답 테스트 (Red)
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **테스트**: 전환 확인 상태에서 "네"/"맞아" → 기존 플로우 취소 + 새 인텐트 시작. "아니"/"계속" → 기존 플로우 유지. 세션 상태 정리 검증 (pending_intent=None, retry=0)
- **의존성**: TASK-008b
- **관련 요구사항**: FR-005, FR-006, NFR-002
- **커밋 메시지**: "behavioral(red): add intent switch confirmation response tests"

### TASK-010: 전환 확인 응답 구현 (Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **구현**: `_handle_switch_confirm()` — Yes("네","맞아") → 기존 상태 정리 + 새 인텐트 시작. No("아니","아니오","계속") → 기존 플로우 복귀.
- **의존성**: TASK-009
- **관련 요구사항**: FR-005, FR-006, NFR-002
- **완료 기준**: TASK-009 테스트 통과
- **커밋 메시지**: "behavioral(green): implement intent switch confirmation handler"

### TASK-011: 시스템 인텐트 즉시 처리 테스트 (Red)
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **테스트**: pending_intent 상태에서 "통화 종료" → 전환 확인 없이 즉시 END_CALL 처리
- **의존성**: TASK-010
- **관련 요구사항**: FR-007
- **커밋 메시지**: "behavioral(red): add system intent bypass tests"

### TASK-012: 시스템 인텐트 즉시 처리 구현 (Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **구현**: `_handle_intent_switch()`에서 `SYSTEM_CONTROL_INTENTS` 체크 → 확인 없이 즉시 처리
- **의존성**: TASK-011
- **관련 요구사항**: FR-007
- **커밋 메시지**: "behavioral(green): implement system intent immediate processing"

### TASK-013: 구어체 인식률 테스트 (Red)
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **테스트**: 30개 구어체 발화 테스트셋 → 24/30 이상 정확 분류 (80%), UNCLASSIFIED ≤ 9/30
- **의존성**: TASK-006
- **관련 요구사항**: FR-008
- **커밋 메시지**: "behavioral(red): add colloquial recognition rate benchmark test"

### TASK-014: 패턴 튜닝 (Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **구현**: 테스트셋 기준 미달 패턴 추가/수정
- **의존성**: TASK-013
- **관련 요구사항**: FR-008
- **커밋 메시지**: "behavioral(green): tune patterns to achieve 80% recognition rate"

### TASK-015: NLU 성능 벤치마크
- **변경 유형**: Behavioral
- **설명**: 정규식 매칭 1000회 반복 P99 ≤ 5ms 확인 + 1000자 입력 ReDoS 테스트 100ms 이내
- **의존성**: TASK-014
- **관련 요구사항**: NFR-001, NFR-004
- **커밋 메시지**: "behavioral: add NLU performance benchmark (5ms P99, ReDoS)"

### TASK-016: E2E 파이프라인 통합 테스트
- **변경 유형**: Behavioral
- **설명**: `TurnPipeline.process()` 경유 E2E 테스트 — 구어체 발화 분류 + 인텐트 전환 + 시스템 인텐트 즉시 처리를 파이프라인 전체 경로로 검증
- **의존성**: TASK-012, TASK-014
- **관련 요구사항**: NFR-003, FR-004, FR-007
- **커밋 메시지**: "behavioral: add Phase E E2E pipeline integration tests"

## 태스크 의존성 그래프

```
TASK-001 → TASK-002 → TASK-003 → TASK-004 → TASK-005 → TASK-006
                                       ↓                    ↓
TASK-007 ──────────────────→ TASK-008 → TASK-008b → TASK-009 → TASK-010 → TASK-011 → TASK-012
                                                                                        ↓
                    TASK-006 → TASK-013 → TASK-014 → TASK-015 ──→ TASK-016 ←── TASK-012
```

E-1 (001-006)과 E-3 전반 (007) 병렬 가능.

## 테스트 전략
- 단위 테스트: 패턴 매칭, 인텐트 전환 로직
- 통합 테스트: TurnPipeline.process() 경유 E2E
- 벤치마크: 성능/보안 (NFR-001, NFR-004)
- 테스트 커버리지: 신규 코드 90% 이상
