# Phase D: 모니터링 및 운영 안정성 기능정의서

## 1. 개요
- Callbot 시스템의 운영 가시성 확보 및 프로덕션 안정성 향상을 위한 모니터링 인프라 구축
- 핵심 가치: 장애 사전 탐지, 성능 병목 식별, 비즈니스 지표 추적, 운영 이상 자동 알람

## 2. 배경 및 목적

### 해결하려는 문제
Phase C에서 파이프라인 재설계(인텐트 라우팅, 다단계 플로우, PII 마스킹, 프롬프트 인젝션 필터)를 완료했으나, 운영 환경에서의 가시성이 전무하다:
- 파이프라인 각 단계별 처리 시간을 알 수 없음
- 인텐트별 호출 빈도, 성공/실패율을 추적할 수 없음
- PII 마스킹 동작 여부, 인젝션 차단 빈도를 확인할 방법이 없음
- LLM 호출 비용/지연을 측정할 수 없음
- Redis/PG 장애 시 graceful degradation이 없음
- 입력 validation이 없어 잘못된 요청이 파이프라인까지 진입함

### As-Is
- `monitoring/` 디렉터리: `__init__.py`만 존재 (빈 스텁)
- `health/router.py`: 헬스체크 엔드포인트 존재하나 메트릭 연동 없음
- 각 모듈에 `logging` import는 있으나 구조화된 로깅 미적용
- Redis TTL 만료 시 PG fallback 없음 (M-17)
- PG turn_count 미갱신 — 항상 0 (M-18)
- 서버 입력 validation 없음 (M-24)

### To-Be
- 구조화된 메트릭 수집 (Counter, Histogram, Gauge) — CloudWatch EMF 포맷
- 파이프라인 단계별 지연 시간 계측 (P50/P95/P99)
- 비즈니스 메트릭 대시보드 (인텐트별 호출, 성공/실패, PII 탐지, 인젝션 차단)
- CloudWatch 알람 (에러율, 지연, LLM 비용)
- Redis 장애 시 PG fallback + 자동 재캐싱
- PG turn_count 정확한 갱신
- Pydantic 기반 입력 검증

### 비즈니스 임팩트
- 장애 MTTD(Mean Time to Detect) 30분 → 5분 이내
- 장애 MTTR(Mean Time to Resolve) 2시간 → 30분 이내
- LLM 비용 이상 증가 시 즉시 알람
- 인텐트 분류 정확도 추적으로 NLU 개선 근거 확보

## 3. 용어 정의

| 용어 | 정의 |
|------|------|
| EMF | Embedded Metric Format — CloudWatch에 구조화된 메트릭을 로그로 전송하는 포맷 |
| Metric Namespace | CloudWatch 메트릭의 논리적 그룹 (`Callbot/Pipeline`, `Callbot/Business` 등) |
| Dimension | 메트릭을 세분화하는 키-값 쌍 (예: `intent=요금_조회`) |
| Counter | 단조 증가하는 누적 값 (요청 수, 에러 수) |
| Histogram | 값의 분포를 기록 (지연 시간의 P50/P95/P99) |
| Gauge | 현재 상태 값 (활성 세션 수, 큐 깊이) |
| PIF | Prompt Injection Filter — 프롬프트 인젝션 탐지 모듈 |
| Fallback | 주 시스템 장애 시 대체 경로로 전환하는 메커니즘 |
| Graceful Degradation | 부분 장애 시 전체 서비스는 유지하되 기능을 축소하여 운영 |

## 4. 사용자 스토리

| ID | As a | I want | So that |
|----|------|--------|---------|
| US-001 | 운영자 | 파이프라인 단계별 지연 시간을 CloudWatch 대시보드에서 확인 | 성능 병목을 즉시 식별할 수 있다 |
| US-002 | 운영자 | 에러율이 임계치를 초과하면 알람을 받고 싶다 | 장애를 5분 이내에 인지하고 대응할 수 있다 |
| US-003 | 비즈니스 분석가 | 인텐트별 호출 빈도와 성공률을 추적 | NLU 개선 우선순위를 결정할 수 있다 |
| US-004 | 운영자 | Redis 장애 시에도 세션이 유지되길 원한다 | 단일 장애점(SPOF) 없이 서비스를 운영할 수 있다 |
| US-005 | 개발자 | 잘못된 API 요청이 파이프라인에 진입하기 전에 거부 | 불필요한 리소스 소모와 예측 불가능한 에러를 방지할 수 있다 |
| US-006 | 운영자 | LLM 토큰 사용량을 실시간으로 추적하고 모델별 단가 기반 비용을 추정 | 비용 이상 증가를 즉시 탐지하고 예산을 관리할 수 있다 |
| US-007 | 운영자 | PII 마스킹 및 인젝션 차단 빈도를 모니터링 | 보안 위협 트렌드를 파악하고 대응할 수 있다 |
| US-008 | 운영자 | 세션별 대화 턴 수를 정확히 추적하고 싶다 | 세션 데이터 정합성을 보장하고 분석에 활용할 수 있다 |

## 5. 기능 요구사항

| ID | 요구사항 | 우선순위 | 관련 US |
|----|----------|----------|---------|
| FR-001 | 메트릭 수집기 (MetricsCollector) 인터페이스 정의 — Counter, Histogram, Gauge 지원 | P0 | US-001 |
| FR-002 | CloudWatch EMF 기반 MetricsCollector 구현체 | P0 | US-001, US-002 |
| FR-003 | InMemory MetricsCollector 구현체 (테스트/로컬 개발용) | P0 | US-001 |
| FR-004 | TurnPipeline 각 단계에 타이밍 메트릭 계측 주입 — PIF(pif_duration_ms), NLU(nlu_duration_ms — Dimension: intent), LLM 스텝(llm_step_duration_ms — 전후처리 포함), 외부API(external_api_duration_ms — Dimension: operation), PII마스킹(pii_masking_duration_ms), 전체(total_duration_ms — Dimension: intent) | P0 | US-001 |
| FR-005 | 비즈니스 메트릭: 인텐트별 호출 카운터(intent_requests_total), 성공 카운터(intent_success_total — Dimension: intent, action_type), 실패 카운터(intent_failure_total — Dimension: intent, error_type) | P0 | US-003 |
| FR-006 | 보안 메트릭: PII 탐지 카운터(pii_detected_total, Dimension: pii_type), 인젝션 차단 카운터(injection_blocked_total, Dimension: pattern_name) | P0 | US-007 |
| FR-007 | LLM 메트릭: 호출 카운터(llm_requests_total), 지연(llm_duration_ms), 토큰 수(llm_input_tokens, llm_output_tokens), 추정 비용(llm_estimated_cost_usd — 모델별 단가 × 토큰 수), 에러(llm_errors_total) | P1 | US-006 |
| FR-008 | 세션 메트릭: 활성 세션 Gauge(active_sessions), 세션 생성/종료 카운터 | P1 | US-004 |
| FR-009 | CloudWatch 알람 정의: 에러율 > 5% (5분간), P95 지연 > 3000ms, LLM 에러율 > 10%, LLM 비용 이상 증가(llm_estimated_cost_usd 시간당 > 임계치 TBD) | P1 | US-002, US-006 |
| FR-010 | Redis 장애 시 PG fallback — `load()` miss 시 PG 조회 → Redis 재캐싱 (M-17) | P0 | US-004 |
| FR-011 | PG turn_count 갱신 — `insert_turn` 후 `UPDATE SET turn_count = turn_count + 1` (M-18) | P0 | US-008 |
| FR-012 | Pydantic 입력 validation — `/turn` 엔드포인트에 요청 모델 적용, text 필수/최대 2000자, session_id UUID 형식 검증 (M-24) | P0 | US-005 |
| FR-013 | 구조화된 JSON 로깅 — 기존 logging을 structlog 기반으로 전환, 요청별 correlation_id 포함 | P1 | US-001, US-002 |
| FR-014 | 헬스체크 메트릭 연동 — `/health/ready`, `/health/live` 응답에 PG/Redis 상태 + 연결 시간 메트릭 포함 | P1 | US-004 |

## 6. 비기능 요구사항

| ID | 요구사항 | 기준 | 관련 FR |
|----|----------|------|---------|
| NFR-001 | 메트릭 수집으로 인한 파이프라인 지연 증가 ≤ 5ms (P99) | 계측 전/후 벤치마크 | FR-001~FR-008 |
| NFR-002 | MetricsCollector는 DI로 주입, 파이프라인 코드에서 구현체 직접 참조 금지 | 코드 리뷰 | FR-001 |
| NFR-003 | CloudWatch EMF 전송 실패 시 파이프라인 처리에 영향 없음 (fire-and-forget) | 장애 주입 테스트 | FR-002 |
| NFR-004 | Redis fallback 시 응답 지연 추가 ≤ 100ms (P95) | 장애 주입 벤치마크 | FR-010 |
| NFR-005 | 입력 validation 실패 시 명확한 에러 메시지 + 422 HTTP 상태코드 반환 | API 테스트 | FR-012 |
| NFR-006 | 모든 메트릭 코드는 테스트 가능 — InMemory 구현체로 단위 테스트 작성 | 테스트 커버리지 80%+ | FR-003 |
| NFR-007 | 기존 765 테스트 깨지지 않음 | CI 통과 | 전체 |

## 7. 기술 설계

### 아키텍처 개요

```
┌─────────────────────────────────────────────────────┐
│                   TurnPipeline                       │
│  ┌──────┐  ┌─────┐  ┌──────┐  ┌─────┐  ┌────────┐  │
│  │ PIF  │→│ NLU │→│ LLM  │→│ Ext │→│Response│  │
│  └──┬───┘  └──┬──┘  └──┬───┘  └──┬──┘  └────────┘  │
│     │         │        │        │                   │
│     ▼         ▼        ▼        ▼                   │
│  ┌─────────────────────────────────────┐            │
│  │        MetricsCollector (DI)        │            │
│  └───────────────┬─────────────────────┘            │
└──────────────────┼──────────────────────────────────┘
                   │
    ┌──────────────┼──────────────┐
    │              │              │
    ▼              ▼              ▼
┌────────┐  ┌──────────┐  ┌──────────┐
│InMemory│  │CloudWatch│  │ Future:  │
│(test)  │  │  (EMF)   │  │Prometheus│
└────────┘  └──────────┘  └──────────┘
```

### 주요 컴포넌트

| 컴포넌트 | 역할 | 위치 |
|----------|------|------|
| `MetricsCollector` (Protocol) | 메트릭 수집 인터페이스 | `monitoring/collector.py` |
| `CloudWatchCollector` | EMF 포맷으로 CloudWatch 전송 | `monitoring/cloudwatch.py` |
| `InMemoryCollector` | 테스트용 메트릭 저장소 | `monitoring/in_memory.py` |
| `PipelineInstrumentation` | 파이프라인 단계별 타이밍 계측 (TurnPipeline 내 인라인 헬퍼) | `server/pipeline.py` 내 `_record_timing()` |
| `RequestValidator` | Pydantic 입력 검증 모델 | `server/schemas.py` |
| `StructuredLogger` | structlog 기반 JSON 로거 설정 | `monitoring/logging.py` |

### 기술 스택

| 기술 | 용도 | 버전 |
|------|------|------|
| structlog | 구조화된 JSON 로깅 | ≥23.0 |
| aws-embedded-metrics | CloudWatch EMF SDK (선택적 — 직접 EMF JSON stdout 출력으로 대체 가능, RISK-001 완화) | ≥3.0 |
| pydantic | 입력 검증 (이미 FastAPI에서 사용 중) | ≥2.0 |
| pytest-benchmark | 성능 벤치마크 (NFR-001 검증) | ≥4.0 |

### 시스템 간 연동

- `TurnPipeline` → `MetricsCollector`: DI로 주입, 각 단계에서 `increment()`, `observe()`, `set_gauge()` 호출
- `MetricsCollector` → CloudWatch: EMF 포맷으로 stdout 출력 → CloudWatch Agent가 수집
- `SessionStore` → PG: Redis miss 시 PG 조회 fallback 경로 추가
- `FastAPI` → `RequestValidator`: 엔드포인트에서 Pydantic 모델로 요청 검증

## 8. 데이터 모델

### 메트릭 데이터

| Namespace | Metric Name | Type | Dimensions | Unit |
|-----------|-------------|------|------------|------|
| Callbot/Pipeline | pif_duration_ms | Histogram | - | ms |
| Callbot/Pipeline | nlu_duration_ms | Histogram | intent | ms |
| Callbot/Pipeline | llm_step_duration_ms | Histogram | - | ms |
| Callbot/Pipeline | external_api_duration_ms | Histogram | operation | ms |
| Callbot/Pipeline | pii_masking_duration_ms | Histogram | - | ms |
| Callbot/Pipeline | total_duration_ms | Histogram | intent | ms |
| Callbot/Business | intent_requests_total | Counter | intent | Count |
| Callbot/Business | intent_success_total | Counter | intent, action_type | Count |
| Callbot/Business | intent_failure_total | Counter | intent, error_type | Count |
| Callbot/Security | pii_detected_total | Counter | pii_type | Count |
| Callbot/Security | injection_blocked_total | Counter | pattern_name | Count |
| Callbot/LLM | llm_requests_total | Counter | model | Count |
| Callbot/LLM | llm_duration_ms | Histogram | model | ms |
| Callbot/LLM | llm_input_tokens | Counter | model | Count |
| Callbot/LLM | llm_output_tokens | Counter | model | Count |
| Callbot/LLM | llm_errors_total | Counter | model, error_type | Count |
| Callbot/LLM | llm_estimated_cost_usd | Counter | model | USD |
| Callbot/Session | active_sessions | Gauge | - | Count |
| Callbot/Session | session_created_total | Counter | - | Count |
| Callbot/Session | session_ended_total | Counter | - | Count |

### PG 스키마 변경 (M-18)

```sql
-- 기존 insert_turn 프로시저에 추가
UPDATE sessions SET turn_count = turn_count + 1 WHERE session_id = %s;
```

## 9. API 설계

### 기존 엔드포인트 변경

**POST /turn** — 입력 검증 추가 (FR-012)

Request Model:
```python
class TurnRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = Field(None, pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
    caller_id: Optional[str] = Field(None, max_length=20)
```

실패 응답 (422):
```json
{
  "detail": [
    {"loc": ["body", "text"], "msg": "ensure this value has at most 2000 characters", "type": "value_error"}
  ]
}
```

### 새 엔드포인트 없음
기존 `/health/ready`, `/health/live` 엔드포인트는 이미 존재. 메트릭 데이터 추가만.

## 10. UI/UX 고려사항

### CloudWatch 대시보드 레이아웃

```
┌─────────────────────────────────────────────┐
│            Callbot Operations               │
├──────────────────┬──────────────────────────┤
│ Total Requests   │ Error Rate (%)           │
│ [Counter widget] │ [Line chart widget]      │
├──────────────────┼──────────────────────────┤
│ P95 Latency (ms) │ Active Sessions          │
│ [Line chart]     │ [Gauge widget]           │
├──────────────────┴──────────────────────────┤
│        Pipeline Stage Latency (stacked)     │
│ [Stacked area: PIF|NLU|LLM|Ext|PII]        │
├─────────────────────────────────────────────┤
│     Intent Distribution (pie chart)         │
├──────────────────┬──────────────────────────┤
│ PII Detections   │ Injection Blocks         │
│ [Counter]        │ [Counter]                │
├──────────────────┴──────────────────────────┤
│        LLM Cost & Token Tracking             │
│ [Token usage + estimated cost line chart]    │
└─────────────────────────────────────────────┘
```

대시보드 정의는 CloudFormation/Terraform IaC로 관리 (구현 범위 외 — 수동 생성 후 추후 IaC 전환).

## 11. 마일스톤 및 일정

| Phase | 산출물 | 예상 기간 | 의존성 |
|-------|--------|----------|--------|
| D-1: 메트릭 인프라 | MetricsCollector Protocol + InMemory + CloudWatch 구현체 | 1일 | 없음 |
| D-2: 파이프라인 계측 | TurnPipeline 단계별 타이밍 + 비즈니스 메트릭 | 1일 | D-1 |
| D-3: 보안/LLM 메트릭 | PII/인젝션/LLM 메트릭 | 0.5일 | D-1 |
| D-4: 운영 안정성 | Redis fallback, PG turn_count, 입력 validation | 1일 | 없음 (병렬 가능) |
| D-5: 구조화 로깅 | structlog 설정 + correlation_id | 0.5일 | D-1 |
| D-6: 알람 + 대시보드 | CloudWatch 알람 정의, 대시보드 JSON | 0.5일 | D-2, D-3 |

**총 예상: 4~5일**

## 12. 리스크 및 완화 방안

| ID | 리스크 | 확률 | 영향도 | 완화 전략 |
|----|--------|------|--------|-----------|
| RISK-001 | EMF SDK 의존성이 Lambda 전용으로 EC2에서 동작 이슈 | M | H | stdout EMF 포맷 직접 출력 fallback 구현 |
| RISK-002 | 메트릭 수집 오버헤드로 P95 지연 증가 | L | H | NFR-001 벤치마크로 검증, fire-and-forget 패턴 |
| RISK-003 | Redis fallback이 PG에 부하 집중 | M | M | 연결 풀 + rate limiting, Redis 복구 후 자동 재캐싱 |
| RISK-004 | structlog 전환 시 기존 로깅 포맷 호환성 | L | M | 점진적 전환, 기존 핸들러 유지 |

## 13. 성공 지표

| KPI | 목표값 | 측정 방법 | 측정 주기 |
|-----|--------|----------|----------|
| 장애 MTTD | ≤ 5분 | CloudWatch 알람 → 알림 수신 시간 | 장애 발생 시 |
| 장애 MTTR | ≤ 30분 | 알람 수신 → 복구 완료 시간 | 장애 발생 시 |
| 파이프라인 P95 지연 가시성 | 100% 단계별 분해 가능 | CloudWatch 대시보드 | 실시간 |
| 메트릭 수집 오버헤드 | ≤ 5ms (P99) | 벤치마크 테스트 | 배포 시 |
| 테스트 커버리지 (monitoring/) | ≥ 80% | pytest-cov | 배포 시 |
| Redis 장애 시 서비스 가용성 | 100% (degraded mode) | 장애 주입 테스트 | 분기 |

## 14. 의존성

| 의존성 | 유형 | 리스크 |
|--------|------|--------|
| AWS CloudWatch | 외부 서비스 | 낮음 — AWS 관리형 |
| structlog | 라이브러리 | 낮음 — 안정적, 널리 사용 |
| aws-embedded-metrics | 라이브러리 | 중간 — Lambda 최적화, EC2 호환성 확인 필요 |
| 기존 FastAPI/Pydantic | 프레임워크 | 낮음 — 이미 사용 중 |
| claw-dev-role IAM | 인프라 | 낮음 — CloudWatch PutMetricData 권한 필요 |

## 15. 범위 제외 사항

| 항목 | 향후 고려 |
|------|-----------|
| Prometheus/Grafana 연동 | Phase F 이후 — 현재 CloudWatch 우선 |
| APM (X-Ray 등) 분산 추적 | Phase F — 현재 단일 서비스이므로 불필요 |
| 알람 → PagerDuty/Slack 연동 | Phase D 이후 — 수동 SNS 알람으로 시작 |
| CloudWatch 대시보드 IaC | Phase D 이후 — 수동 생성 후 전환 |
| 비용 자동 제어 (LLM throttling) | Phase F — 현재 알람만 |
| 로그 보존 정책/아카이브 | Phase F — 기본 CloudWatch 보존 사용 |
