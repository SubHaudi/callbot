# Phase D: 모니터링 및 운영 안정성 구현 계획

## 구현 원칙
- TDD 사이클: Red → Green → Refactor
- Tidy First: 구조적 변경과 행위적 변경을 분리
- 구조적 변경 먼저, 행위적 변경은 그 다음
- 각 커밋은 구조적 또는 행위적 중 하나만 포함

## 요구사항 추적 매트릭스

| 요구사항 ID | 요구사항 요약 | 관련 태스크 |
|-------------|-------------|-------------|
| FR-001 | MetricsCollector Protocol | TASK-001, TASK-002 |
| FR-002 | CloudWatch EMF 구현체 | TASK-005, TASK-006 |
| FR-003 | InMemory 구현체 | TASK-003, TASK-004 |
| FR-004 | 파이프라인 타이밍 메트릭 | TASK-007, TASK-008, TASK-009, TASK-010 |
| FR-005 | 비즈니스 메트릭 | TASK-011, TASK-012 |
| FR-006 | 보안 메트릭 | TASK-013, TASK-014 |
| FR-007 | LLM 메트릭 | TASK-015, TASK-016 |
| FR-008 | 세션 메트릭 | TASK-017, TASK-017b, TASK-018 |
| FR-009 | CloudWatch 알람 | TASK-029, TASK-030 |
| FR-010 | Redis PG fallback | TASK-021, TASK-022 |
| FR-011 | PG turn_count | TASK-019, TASK-020 |
| FR-012 | 입력 validation | TASK-023, TASK-024 |
| FR-013 | 구조화 로깅 | TASK-025, TASK-026 |
| FR-014 | 헬스체크 메트릭 | TASK-027, TASK-028 |
| NFR-001 | 메트릭 오버헤드 ≤ 5ms | TASK-010 (벤치마크) |
| NFR-002 | DI 주입 | TASK-001, TASK-007 |
| NFR-003 | EMF fire-and-forget | TASK-006 |
| NFR-004 | Redis fallback ≤ 100ms | TASK-022, TASK-022b |
| NFR-005 | 422 에러 응답 | TASK-024 |
| NFR-006 | 메트릭 코드 테스트 가능 80%+ | TASK-003, TASK-004 |
| NFR-007 | 기존 테스트 통과 | 전체 |

## 구현 순서 개요

```
D-1 메트릭 인프라:
  TASK-001(S) → TASK-002(B:Red) → TASK-003(B:Red) → TASK-004(B:Green)
  → TASK-005(S) → TASK-006(B:Red→Green)

D-2 파이프라인 계측:
  TASK-007(S) → TASK-008(B:Red) → TASK-009(B:Green) → TASK-010(B:Green+벤치)

D-3 보안/LLM/비즈니스/세션 메트릭:
  TASK-011(B:Red) → TASK-012(B:Green)
  TASK-013(B:Red) → TASK-014(B:Green)
  TASK-015(B:Red) → TASK-016(B:Green)
  TASK-017(S:DI) → TASK-017b(B:Red) → TASK-018(B:Green)

D-4 운영 안정성 (병렬):
  TASK-019(B:Red) → TASK-020(B:Green)    [PG turn_count]
  TASK-021(B:Red) → TASK-022(B:Green)    [Redis fallback]
  TASK-023(S) → TASK-024(B:Red→Green)    [입력 validation]

D-5 구조화 로깅:
  TASK-025(S) → TASK-026(B:Red→Green)

D-6 헬스체크/알람:
  TASK-027(B:Red) → TASK-028(B:Green)    [헬스체크 메트릭]
  TASK-029(S) → TASK-030(B)              [알람 정의]
```

## 태스크 목록

### TASK-001: MetricsCollector Protocol 정의
- **변경 유형**: Structural
- **TDD 단계**: Setup
- **설명**: `monitoring/collector.py`에 `MetricsCollector` Protocol 정의. `increment(name, value=1, dimensions=None)`, `observe(name, value, dimensions=None)`, `set_gauge(name, value, dimensions=None)` 메서드.
- **의존성**: 없음
- **관련 요구사항**: FR-001, NFR-002
- **완료 기준**: Protocol 클래스 존재, 기존 테스트 통과
- **커밋 메시지 예시**: "structural: define MetricsCollector protocol"

### TASK-002: MetricsCollector Protocol 타입 검증 테스트
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: InMemoryCollector가 Protocol을 만족하는지 검증하는 테스트 작성. InMemoryCollector가 아직 구현되지 않았으므로 실패.
- **테스트**: `test_inmemory_conforms_to_metrics_collector_protocol` — Protocol 메서드 시그니처 + structural subtyping 검증
- **의존성**: TASK-001
- **관련 요구사항**: FR-001
- **완료 기준**: 테스트 작성, 실패 확인
- **커밋 메시지 예시**: "behavioral(red): add MetricsCollector protocol conformance tests"

### TASK-003: InMemoryCollector 실패 테스트
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: `InMemoryCollector`의 동작 검증 테스트 작성. increment → 카운터 증가, observe → 값 기록, set_gauge → 현재값 설정, dimensions 지원.
- **테스트**: `test_inmemory_increment`, `test_inmemory_observe`, `test_inmemory_set_gauge`, `test_inmemory_dimensions`
- **의존성**: TASK-001
- **관련 요구사항**: FR-003, NFR-006
- **완료 기준**: 테스트 작성, 실패 확인
- **커밋 메시지 예시**: "behavioral(red): add InMemoryCollector tests"

### TASK-004: InMemoryCollector 구현
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: `monitoring/in_memory.py`에 `InMemoryCollector` 구현. TASK-002, TASK-003 테스트 통과.
- **구현**: Counter는 dict 누적, Observe는 list append, Gauge는 단일값 저장. Dimensions는 frozenset 키.
- **의존성**: TASK-002, TASK-003
- **관련 요구사항**: FR-003, NFR-006
- **완료 기준**: TASK-002 + TASK-003 테스트 전부 통과
- **커밋 메시지 예시**: "behavioral(green): implement InMemoryCollector"

### TASK-005: CloudWatchCollector 모듈 스캐폴딩
- **변경 유형**: Structural
- **TDD 단계**: Setup
- **설명**: `monitoring/cloudwatch.py` 파일 생성. EMF JSON 포맷 출력 클래스 스켈레톤. stdout 직접 출력 방식 (RISK-001 완화 — SDK 대신 직접 EMF JSON).
- **의존성**: TASK-001
- **관련 요구사항**: FR-002
- **완료 기준**: 파일 존재, import 가능, 기존 테스트 통과
- **커밋 메시지 예시**: "structural: scaffold CloudWatchCollector module"

### TASK-006: CloudWatchCollector EMF 출력 구현 + 테스트
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: CloudWatchCollector가 EMF JSON을 stdout으로 출력. 테스트는 stdout 캡처로 검증. fire-and-forget 패턴: 출력 실패 시 예외 삼킴 (NFR-003).
- **테스트**: `test_cloudwatch_emf_format`, `test_cloudwatch_fire_and_forget`, `test_cloudwatch_dimensions`
- **의존성**: TASK-005
- **관련 요구사항**: FR-002, NFR-003
- **완료 기준**: EMF JSON 포맷 정확, 실패 시 예외 없음
- **커밋 메시지 예시**: "behavioral: implement CloudWatchCollector with EMF stdout output"

### TASK-007: TurnPipeline에 MetricsCollector DI 추가
- **변경 유형**: Structural
- **TDD 단계**: Setup
- **설명**: `TurnPipeline.__init__`에 `metrics_collector: Optional[MetricsCollector] = None` 파라미터 추가. 기존 동작 변경 없음.
- **의존성**: TASK-001
- **관련 요구사항**: FR-004, NFR-002
- **완료 기준**: 기존 765+ 테스트 전부 통과 (metrics_collector=None이 기본)
- **커밋 메시지 예시**: "structural: add metrics_collector DI param to TurnPipeline"

### TASK-008: 파이프라인 타이밍 메트릭 테스트 (Red)
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: TurnPipeline.process()에서 InMemoryCollector에 pif_duration_ms, nlu_duration_ms, total_duration_ms 등이 기록되는지 검증.
- **테스트**: `test_pipeline_records_pif_timing`, `test_pipeline_records_nlu_timing_with_intent_dimension`, `test_pipeline_records_llm_step_timing`, `test_pipeline_records_external_api_timing`, `test_pipeline_records_pii_masking_timing`, `test_pipeline_records_total_timing`
- **의존성**: TASK-004, TASK-007
- **관련 요구사항**: FR-004
- **완료 기준**: 테스트 작성, 실패 확인
- **커밋 메시지 예시**: "behavioral(red): add pipeline timing metric tests"

### TASK-009: 파이프라인 타이밍 메트릭 구현 (Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: TurnPipeline.process() 각 단계에 time.perf_counter() 계측 추가. metrics_collector가 None이면 스킵.
- **구현**: `_record_timing(name, start, end, dimensions)` 헬퍼. PIF/NLU/LLM스텝/외부API/PII/전체 6개 지점.
- **의존성**: TASK-008
- **관련 요구사항**: FR-004
- **완료 기준**: TASK-008 테스트 통과 + 기존 테스트 통과
- **커밋 메시지 예시**: "behavioral(green): instrument pipeline timing metrics"

### TASK-010: 파이프라인 메트릭 오버헤드 벤치마크
- **변경 유형**: Behavioral
- **TDD 단계**: Green (검증)
- **설명**: InMemoryCollector 사용 시 process() 호출 오버헤드가 5ms 이하인지 벤치마크.
- **테스트**: `test_metrics_overhead_under_5ms` — 1000회 호출 P99 측정
- **의존성**: TASK-009
- **관련 요구사항**: NFR-001
- **완료 기준**: 벤치마크 통과
- **커밋 메시지 예시**: "behavioral: add metrics overhead benchmark (NFR-001)"

### TASK-011: 비즈니스 메트릭 테스트 (Red)
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: intent_requests_total, intent_success_total, intent_failure_total 메트릭 기록 검증.
- **테스트**: `test_intent_request_counter`, `test_intent_success_with_action_type`, `test_intent_failure_with_error_type`
- **의존성**: TASK-009
- **관련 요구사항**: FR-005
- **완료 기준**: 테스트 실패
- **커밋 메시지 예시**: "behavioral(red): add business metrics tests"

### TASK-012: 비즈니스 메트릭 구현 (Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: TurnPipeline에서 인텐트 분류 후 increment("intent_requests_total", dimensions={"intent": ...}). 성공/실패 시 각각 기록.
- **의존성**: TASK-011
- **관련 요구사항**: FR-005
- **완료 기준**: TASK-011 테스트 통과
- **커밋 메시지 예시**: "behavioral(green): implement business metrics"

### TASK-013: 보안 메트릭 테스트 (Red)
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: pii_detected_total(dimension: pii_type), injection_blocked_total(dimension: pattern_name) 기록 검증.
- **테스트**: `test_pii_detection_counter`, `test_injection_block_counter`
- **의존성**: TASK-009
- **관련 요구사항**: FR-006
- **완료 기준**: 테스트 실패
- **커밋 메시지 예시**: "behavioral(red): add security metrics tests"

### TASK-014: 보안 메트릭 구현 (Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: PII 마스킹 시 탐지된 타입별 카운터 증가. PIF 차단 시 패턴명 카운터 증가.
- **의존성**: TASK-013
- **관련 요구사항**: FR-006
- **완료 기준**: TASK-013 테스트 통과
- **커밋 메시지 예시**: "behavioral(green): implement security metrics"

### TASK-015: LLM 메트릭 테스트 (Red)
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: llm_requests_total, llm_duration_ms, llm_input_tokens, llm_output_tokens, llm_estimated_cost_usd, llm_errors_total 기록 검증.
- **테스트**: `test_llm_request_counter`, `test_llm_duration`, `test_llm_token_tracking`, `test_llm_cost_estimation`, `test_llm_error_counter_with_error_type`, `test_llm_metrics_include_model_dimension`
- **의존성**: TASK-009
- **관련 요구사항**: FR-007
- **완료 기준**: 테스트 실패
- **커밋 메시지 예시**: "behavioral(red): add LLM metrics tests"

### TASK-016: LLM 메트릭 구현 (Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: LLM 호출 전후 타이밍 + 응답에서 토큰 수 추출 + 모델별 단가표로 비용 추정. 모든 메트릭에 `dimensions={"model": model_name}` 포함. `llm_errors_total`은 추가로 `error_type` dimension 포함.
- **구현**: `_LLM_COST_PER_TOKEN = {"sonnet-4": {"input": 0.003/1000, "output": 0.015/1000}, ...}` 설정.
- **의존성**: TASK-015
- **관련 요구사항**: FR-007
- **완료 기준**: TASK-015 테스트 통과
- **커밋 메시지 예시**: "behavioral(green): implement LLM metrics with cost estimation"

### TASK-017: SessionManager에 MetricsCollector DI 추가
- **변경 유형**: Structural
- **TDD 단계**: Setup
- **설명**: `SessionManager.__init__`에 `metrics_collector: Optional[MetricsCollector] = None` 파라미터 추가. 기존 동작 변경 없음.
- **의존성**: TASK-004
- **관련 요구사항**: FR-008, NFR-002
- **완료 기준**: 기존 테스트 통과 (metrics_collector=None이 기본)
- **커밋 메시지 예시**: "structural: add metrics_collector DI param to SessionManager"

### TASK-017b: 세션 메트릭 테스트 (Red)
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: active_sessions gauge, session_created_total, session_ended_total 카운터 기록 검증.
- **테스트**: `test_session_created_counter`, `test_session_ended_counter`, `test_active_sessions_gauge`
- **의존성**: TASK-017
- **관련 요구사항**: FR-008
- **커밋 메시지 예시**: "behavioral(red): add session metrics tests"

### TASK-018: 세션 메트릭 구현 (Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: SessionManager에 MetricsCollector DI. create_session에서 increment + gauge 증가, 세션 종료 시 gauge 감소.
- **의존성**: TASK-017b
- **관련 요구사항**: FR-008
- **완료 기준**: TASK-017b 테스트 통과
- **커밋 메시지 예시**: "behavioral(green): implement session metrics"

### TASK-019: PG turn_count 갱신 테스트 (Red)
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: insert_turn 후 turn_count가 증가하는지 InMemoryDB로 테스트.
- **테스트**: `test_turn_count_increments_after_insert_turn`
- **의존성**: 없음
- **관련 요구사항**: FR-011
- **완료 기준**: 테스트 실패 (현재 turn_count 항상 0)
- **커밋 메시지 예시**: "behavioral(red): add PG turn_count increment test"

### TASK-020: PG turn_count 갱신 구현 (Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: `repository.py`의 `insert_turn` 메서드에 `UPDATE sessions SET turn_count = turn_count + 1 WHERE session_id = %s` 추가.
- **의존성**: TASK-019
- **관련 요구사항**: FR-011
- **완료 기준**: TASK-019 테스트 통과
- **커밋 메시지 예시**: "behavioral(green): implement PG turn_count increment"

### TASK-021: Redis PG fallback 테스트 (Red)
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: Redis에서 세션 없을 때 PG에서 조회 → Redis 재캐싱. Redis 장애(연결 실패) 시에도 PG 직접 조회로 서비스 유지.
- **테스트**: `test_redis_miss_falls_back_to_pg`, `test_redis_failure_falls_back_to_pg`, `test_redis_recache_after_pg_fallback`
- **의존성**: 없음
- **관련 요구사항**: FR-010, NFR-004
- **완료 기준**: 테스트 실패
- **커밋 메시지 예시**: "behavioral(red): add Redis PG fallback tests"

### TASK-022: Redis PG fallback 구현 (Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: `redis_session_store.py`의 `load()` 수정. Redis miss/에러 시 PG repository에서 조회 → 성공하면 Redis에 재캐싱.
- **구현**: `try: redis.get() → except: pg_repository.get_session()` + `redis.set(ttl=...)` 재캐싱.
- **의존성**: TASK-021
- **관련 요구사항**: FR-010, NFR-004
- **완료 기준**: TASK-021 테스트 통과
- **커밋 메시지 예시**: "behavioral(green): implement Redis PG fallback with recaching"

### TASK-022b: Redis fallback 지연 벤치마크
- **변경 유형**: Behavioral
- **TDD 단계**: Green (검증)
- **설명**: Redis fallback 시 추가 지연이 100ms 이하(P95)인지 벤치마크. InMemory PG mock으로 측정.
- **테스트**: `test_redis_fallback_latency_under_100ms`
- **의존성**: TASK-022
- **관련 요구사항**: NFR-004
- **완료 기준**: 벤치마크 통과
- **커밋 메시지 예시**: "behavioral: add Redis fallback latency benchmark (NFR-004)"

### TASK-023: 입력 validation Pydantic 모델 스캐폴딩
- **변경 유형**: Structural
- **TDD 단계**: Setup
- **설명**: `server/schemas.py` 생성. `TurnRequest` Pydantic BaseModel 정의 (text: str, session_id: Optional[str], caller_id: Optional[str]).
- **의존성**: 없음
- **관련 요구사항**: FR-012
- **완료 기준**: 파일 존재, import 가능
- **커밋 메시지 예시**: "structural: create server/schemas.py with TurnRequest model"

### TASK-024: 입력 validation 구현 + 테스트
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: `/turn` 엔드포인트에 TurnRequest 적용. text 필수/1~2000자, session_id UUID 형식, caller_id 최대 20자. 422 에러 응답.
- **테스트**: `test_empty_text_returns_422`, `test_text_over_2000_returns_422`, `test_invalid_session_id_returns_422`, `test_valid_request_passes`
- **의존성**: TASK-023
- **관련 요구사항**: FR-012, NFR-005
- **완료 기준**: validation 테스트 통과 + 기존 테스트 통과
- **커밋 메시지 예시**: "behavioral: implement input validation with Pydantic TurnRequest"

### TASK-025: structlog 설정 스캐폴딩
- **변경 유형**: Structural
- **TDD 단계**: Setup
- **설명**: `monitoring/logging.py` 생성. structlog 설정 함수 `configure_logging()` — JSON 포맷, correlation_id 프로세서.
- **의존성**: 없음
- **관련 요구사항**: FR-013
- **완료 기준**: 파일 존재, import 가능, 기존 테스트 통과
- **커밋 메시지 예시**: "structural: scaffold structlog configuration module"

### TASK-026: 구조화 로깅 구현 + 테스트
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: structlog JSON 출력 검증. TurnPipeline에서 요청 시 correlation_id 바인딩. 로그에 correlation_id, intent, session_id 포함.
- **테스트**: `test_structured_log_json_format`, `test_correlation_id_in_log`
- **의존성**: TASK-025
- **관련 요구사항**: FR-013
- **완료 기준**: JSON 로그 출력 + correlation_id 포함 검증
- **커밋 메시지 예시**: "behavioral: implement structured JSON logging with correlation_id"

### TASK-027: 헬스체크 메트릭 테스트 (Red)
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: `/health/ready` 및 `/health/live` 응답에 PG/Redis 연결 시간 메트릭이 포함되는지 검증.
- **테스트**: `test_health_ready_includes_connection_times`, `test_health_live_includes_status`
- **의존성**: TASK-004
- **관련 요구사항**: FR-014
- **완료 기준**: 테스트 실패
- **커밋 메시지 예시**: "behavioral(red): add health check metrics test"

### TASK-028: 헬스체크 메트릭 구현 (Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: `health/router.py`의 readiness/liveness 체크에 PG/Redis 연결 시간 측정 추가. 응답에 `connection_times` 필드.
- **의존성**: TASK-027
- **관련 요구사항**: FR-014
- **완료 기준**: TASK-027 테스트 통과
- **커밋 메시지 예시**: "behavioral(green): implement health check connection time metrics"

### TASK-029: CloudWatch 알람 정의 스캐폴딩
- **변경 유형**: Structural
- **TDD 단계**: Setup
- **설명**: `monitoring/alarms.py` — 알람 설정 dataclass + CloudFormation/JSON 출력 헬퍼. 에러율 >5%, P95 >3000ms, LLM 에러율 >10%, LLM 비용 임계치.
- **의존성**: TASK-009, TASK-016
- **관련 요구사항**: FR-009
- **완료 기준**: 파일 존재, 알람 설정 정의
- **커밋 메시지 예시**: "structural: define CloudWatch alarm configurations"

### TASK-030: CloudWatch 알람 JSON 출력 테스트
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: 알람 설정을 CloudFormation JSON으로 변환하는 함수 테스트 및 구현.
- **테스트**: `test_alarm_json_includes_error_rate`, `test_alarm_json_includes_llm_cost`
- **의존성**: TASK-029
- **관련 요구사항**: FR-009
- **완료 기준**: 알람 JSON 생성 검증
- **커밋 메시지 예시**: "behavioral: implement CloudWatch alarm JSON export"

## 태스크 의존성 그래프

```
TASK-001 (Protocol)
  ├→ TASK-002 (Protocol test)
  ├→ TASK-003 (InMemory Red) → TASK-004 (InMemory Green)
  │     ├→ TASK-017 (Session DI) → TASK-017b (Session Red) → TASK-018 (Session Green)
  │     └→ TASK-027 (Health Red) → TASK-028 (Health Green)
  ├→ TASK-005 (CW scaffold) → TASK-006 (CW impl)
  └→ TASK-007 (Pipeline DI) → TASK-008 (Timing Red) → TASK-009 (Timing Green) → TASK-010 (Bench)
        ├→ TASK-011 (Biz Red) → TASK-012 (Biz Green)
        ├→ TASK-013 (Sec Red) → TASK-014 (Sec Green)
        └→ TASK-015 (LLM Red) → TASK-016 (LLM Green) → TASK-029 → TASK-030

독립 (D-5):
  TASK-025 (Logging scaffold) → TASK-026 (Logging impl)

독립 (D-4):
  TASK-019 (turn_count Red) → TASK-020 (turn_count Green)
  TASK-021 (Redis fb Red) → TASK-022 (Redis fb Green) → TASK-022b (Redis fb bench)
  TASK-023 (Schema scaffold) → TASK-024 (Validation impl)

D-6:
  TASK-029 (Alarm scaffold) → TASK-030 (Alarm impl)
```

## 테스트 전략
- **단위 테스트**: MetricsCollector 구현체, PII/보안/LLM/세션 메트릭 기록, 알람 JSON 생성, 입력 validation
- **통합 테스트**: TurnPipeline + InMemoryCollector E2E 메트릭 흐름, Redis fallback + PG 연동
- **벤치마크**: 메트릭 오버헤드 ≤ 5ms (NFR-001)
- **테스트 커버리지 목표**: monitoring/ 80% 이상
