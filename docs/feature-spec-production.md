# Callbot Phase C-E 기능정의서: 프로덕션 로드맵 (R3)

## 1. 개요
기존 callbot MVP (REST + WebSocket + CI/CD)를 프로덕션 수준으로 확장.
3단계로 나눠 진행: 비즈니스 로직 → 모니터링 → 음성 처리.

## 2. 배경 및 목적
- **As-Is**: 텍스트 입력 → LLM 응답만 가능. 실제 업무 처리(요금조회 등) 불가. 모니터링 미검증. 음성 미지원.
- **To-Be**: 더미 API 기반 5대 업무 처리 + CloudWatch 모니터링 + faster-whisper STT / Polly TTS 음성 파이프라인
- **용도**: 데모/포트폴리오용 E2E 시스템

## 3. 용어 정의

| 용어 | 정의 |
|------|------|
| Tier1 | 콜센터 인입량 기준 상위 5개 업무 (요금조회, 잔여데이터, 납부확인, 요금제변경, 부가서비스해지) |
| 더미 API | 실제 BSS/OSS 대신 현실적 응답을 반환하는 Mock 서버 |
| PII | 개인식별정보 (전화번호, 주민번호, 이름, 이메일, 계좌번호 등) |
| Circuit Breaker | 외부 API 장애 시 빠른 실패 반환 패턴 (failure_threshold 초과 시 OPEN) |
| VAD | Voice Activity Detection — 음성 구간과 묵음 구간을 구분하는 알고리즘 |
| Barge-in | TTS 재생 중 사용자가 말하면 중단하고 새 입력 처리 |
| faster-whisper | CTranslate2 기반 Whisper 최적화 런타임 (INT8 양자화, 2~4배 빠름) |

## 4. 사용자 스토리

- **US-010**: As a 데모 참관자, I want "내 요금 알려줘"라고 하면 실제 요금 데이터가 나오게, So that 실제 서비스처럼 보임
- **US-011**: As a 데모 참관자, I want "잔여 데이터 확인"하면 남은 데이터를 알려주게, So that 업무 처리 능력 확인
- **US-012**: As a 데모 참관자, I want "이번 달 납부 확인"하면 납부 상태를 보여주게, So that 납부 관련 처리 확인
- **US-013**: As a 데모 참관자, I want "요금제 변경하고 싶어"라고 하면 추천+변경 플로우가 진행되게, So that 복잡 업무도 처리 가능
- **US-014**: As a 데모 참관자, I want "부가서비스 해지해줘"라고 하면 해지 플로우가 진행되게, So that 해지 업무 처리 확인
- **US-015**: As a 운영자, I want CloudWatch 대시보드에서 실시간 메트릭을 볼 수 있게, So that 서비스 상태 한눈에 파악
- **US-016**: As a 데모 참관자, I want 음성으로 말하면 음성으로 답하게, So that 실제 콜센터처럼 체험

## 5. Phase 간 의존성

```
Phase C (비즈니스 로직) ──→ Phase D (모니터링) ──→ 프로덕션
       │                      ↑ (FR-021 Terraform은 C와 병렬 가능)
       └──────────────────→ Phase E (음성)
                              (C의 텍스트 파이프라인 인터페이스 필요)
```
- **D → C**: 비즈니스 메트릭(FR-020)은 C의 핸들러 완료 후 계측. 단, 대시보드 Terraform(FR-021)은 C와 병렬 가능.
- **E → C**: 음성 파이프라인은 C의 텍스트 파이프라인을 래핑. C 완료가 선행 필수.
- **D ↔ E**: 독립적. 병렬 가능.

---

# Phase C: 비즈니스 로직 실체화

## 6. 기능 요구사항

### FR-010: 더미 API 서버 + OpenAPI 계약 (P0, US-010~014)
- FastAPI 기반 별도 Mock 서버 (`mock_api/`)
- **OpenAPI 3.0 spec (`mock_api/openapi.yaml`)** — 모든 엔드포인트의 request/response JSON schema 정의. 향후 실제 API 교체 시 이 계약 준수.
- 5대 업무별 엔드포인트:
  - `GET /api/billing/{customer_id}` → 요금 정보
  - `GET /api/data-usage/{customer_id}` → 잔여 데이터
  - `GET /api/payment/{customer_id}` → 납부 상태
  - `POST /api/plan-change/{customer_id}` → 요금제 변경
  - `POST /api/addon-cancel/{customer_id}` → 부가서비스 해지
- 더미 데이터 5명: 정상 2명 + 예외 케이스 3명 (미납고객, 요금제변경불가, 해지불가)
- 랜덤 지연 (100~500ms) + 간헐적 에러 (5%, CB threshold 미만으로 조정)
- 간단한 API Key 인증 (`X-API-Key` 헤더) — 실제 API 교체 대비
- Docker Compose로 callbot 서버와 함께 실행

### FR-011: 비즈니스 핸들러 5종 (P0, US-010~014)
- 공통 인터페이스: `BaseBusinessHandler` ABC
  ```python
  class BaseBusinessHandler(ABC):
      async def handle(self, intent: str, context: SessionContext) -> HandlerResult
  ```
- `HandlerResult` DTO: `{success: bool, response_text: str, data: dict, error_code: str | None}`
- 각 핸들러: NLU 의도 → 더미 API 호출 → LLM으로 자연어 응답 생성
- `BillingHandler` — 요금 조회
- `DataUsageHandler` — 잔여 데이터 확인
- `PaymentHandler` — 납부 확인
- `PlanChangeHandler` — 요금제 변경 (다단계, FR-015)
- `AddonCancelHandler` — 부가서비스 해지 (다단계, FR-015)

### FR-012: NLU 의도 분류 — Function Calling 통합 (P0, US-010~014)
- **의도 분류 + 응답 생성을 function calling으로 통합** (Bedrock Claude 3 Haiku)
  - Round-trip 1: LLM이 의도 분류 + tool_use로 API 호출 요청
  - 서버가 API 호출 후 tool_result 반환
  - Round-trip 2: LLM이 tool_result 기반 자연어 응답 생성
  - **최대 2 LLM round-trip/턴** (tool_call + final response). 단순 상담(tool 불필요)은 1 round-trip.
- 5개 의도: `BILLING_INQUIRY`, `DATA_USAGE_INQUIRY`, `PAYMENT_INQUIRY`, `PLAN_CHANGE`, `ADDON_CANCEL`
- 의도 미분류 시 → 일반 상담 응답 (fallback)

### FR-013: ExternalAPIWrapper 연동 + CB 정책 (P0, US-010~014)
- 기존 `business/api_wrapper.py`의 `ExternalAPIWrapper` + `CircuitBreaker` 활용
- **CircuitBreaker 설정**:
  - `failure_threshold`: 10회 / 60초 윈도우
  - `reset_timeout`: 30초 (half-open 전환)
  - half-open: 1회 시험 호출 → 성공 시 CLOSED, 실패 시 OPEN 유지
- Retry: 최대 2회, exponential backoff (1초, 2초)
- Timeout: 3초
- **OPEN 상태 시 응답**: "현재 시스템 점검 중입니다. 잠시 후 다시 시도해주세요. 급한 문의는 고객센터(1234)로 연락해주세요."

### FR-014: PII 마스킹 미들웨어 (P1, 전체)
- **마스킹 대상 (로그)**:

  | PII 유형 | 패턴 | 마스킹 결과 |
  |---------|------|-----------|
  | 전화번호 | `010-XXXX-XXXX` | `010-****-****` |
  | 주민번호 | `XXXXXX-XXXXXXX` | `******-*******` |
  | 계좌번호 | 10~16자리 숫자 | `****-****-**1234` |
  | 이메일 | `user@domain` | `u***@domain` |
  | 이름 | API 응답 내 name 필드 | `김**` (API 응답 필드 기반만 마스킹, 자유텍스트 NER 미적용) |

- 구조화 로깅(JsonFormatter)에 통합
- **LLM 프롬프트 내 PII 정책**: 고객에게 응답 시 전화번호/주민번호는 마스킹된 형태로만 전달. LLM system prompt에 "주민번호, 전화번호를 전체 노출하지 마라" 가드레일 추가.
- 응답 본문 후처리: 주민번호/전화번호 정규식 필터 적용 (LLM이 실수로 노출해도 차단)

### FR-015: 다단계 대화 플로우 (P1, US-013~014)
- 요금제 변경, 부가서비스 해지는 다단계:
  1. 의도 확인 → 2. 현재 상태 조회 → 3. 옵션 제시 → 4. 확인 → 5. 처리
- **상태 머신**:
  ```
  IDLE → INTENT_CONFIRMED → DATA_FETCHED → OPTIONS_PRESENTED → ACTION_CONFIRMED → COMPLETED
                                                                       ↓
                                                                   CANCELLED
  ```
- 세션 컨텍스트에 `flow_state` 저장 (Redis)
- **TTL**: 10분 (만료 시 "이전 요청이 만료되었습니다. 다시 말씀해주세요.")
- **동시 플로우**: 사용자당 1개. 새 플로우 시작 시 기존 플로우 취소.
- 중간에 다른 질문 → 플로우 일시중단 → "진행 중인 요청이 있습니다. 계속할까요?" 복귀 프롬프트

---

# Phase D: 모니터링 강화

## 7. 기능 요구사항

### FR-020: 비즈니스 메트릭 발행 (P0, US-015)
- CloudWatch Custom Metrics:

  | 메트릭명 | Unit | Period | Statistic |
  |---------|------|--------|-----------|
  | `IntentClassificationCount` | Count | 1분 | Sum |
  | `APICallSuccess` | Count | 1분 | Sum |
  | `APICallFailure` | Count | 1분 | Sum |
  | `TurnResponseTime` | Milliseconds | 1분 | P95, Average |
  | `FallbackRate` | Percent | 5분 | Average |
  | `ActiveSessionCount` | Count | 1분 | Maximum |

- Namespace: `Callbot/Business`
- 발행: 매 턴 처리 시 (boto3 `put_metric_data`)

### FR-021: CloudWatch 대시보드 (P0, US-015)
- Terraform으로 대시보드 리소스 생성 (`modules/monitoring/dashboard.tf`)
- 위젯: 의도 분류 분포, API 호출 성공률, P95 응답시간, 에러율, 활성 세션 수
- 기존 알람 리소스도 같은 모듈에서 Terraform 관리

### FR-022: 알람 트리거 테스트 (P1)
- 기존 11개 알람 목록 (callbot-infra 참조):
  - ECS CPU/Memory 높음, 태스크 수 부족, ALB 5xx, ALB 응답지연
  - Aurora CPU, 커넥션 수, ElastiCache CPU/Memory/Eviction, WAF 차단률
- 각 알람별 트리거 방법:

  | 알람 | 트리거 방법 |
  |------|-----------|
  | ECS CPU 높음 | `stress --cpu 4 --timeout 60` |
  | ALB 5xx | 더미 API 강제 500 응답 |
  | Aurora 커넥션 | 커넥션 풀 고갈 스크립트 |
  | Redis 메모리 | 대량 키 삽입 |

- SNS → 이메일 정상 발송 확인, 결과 문서 기록

### FR-023: 요청 추적 강화 (P1, US-015)
- X-Ray 트레이싱 활성화
- 세그먼트: ECS → NLU → ExternalAPI → LLM → 응답
- 병목 구간 식별용 서브세그먼트 설정

---

# Phase E: 음성 처리

## 8. 기능 요구사항

### FR-030: faster-whisper STT 서버 (P0, US-016)
- **모델: `faster-whisper` small (INT8 양자화)**
  - CPU 추론 벤치마크 목표: 10초 오디오 → 3~5초 처리
  - 메모리: ~1GB (small INT8)
  - 정확도: 한국어 WER ~15% (데모 허용 범위)
- FastAPI WebSocket 엔드포인트: 오디오 청크 수신 → 텍스트 반환
- `language="ko"` 고정
- **ECS 배포**: 별도 서비스 `callbot-stt`, desired=1 (데모 규모 SPOF 허용)
- 헬스체크: `/health` 엔드포인트, interval 30초, grace period 60초
- 음성 불가 시 → 텍스트 채널 폴백 안내: "음성 서비스가 일시 중단되었습니다. 텍스트로 문의해주세요."
- 환경변수로 모델 크기 전환 가능 (`WHISPER_MODEL=small|medium`)

### FR-031: Amazon Polly TTS 연동 (P0, US-016)
- Neural 한국어 음성 (Seoyeon) — AWS 문서에서 Neural 지원 확인 후 확정, 미지원 시 Standard + SSML
- 텍스트 → SSML 변환 → Polly API → 오디오 스트림
- WebSocket으로 오디오 청크 클라이언트에 스트리밍 (문장 단위 분할)
- **예상 비용**: Neural $16/1M 문자. 데모 규모 (월 1만 턴 × 평균 100자) ≈ $1.6/mo

### FR-032: 음성 대화 파이프라인 (P0, US-016)
- WebSocket 엔드포인트: `/api/v1/ws/voice`
- **오디오 포맷 흐름**:
  ```
  브라우저 (opus/webm 48kHz)
    → 서버: ffmpeg 변환 → PCM 16bit 16kHz
    → faster-whisper STT → 텍스트
    → 텍스트 파이프라인 (기존 Phase C)
    → Polly TTS → PCM 16bit 24kHz
    → 서버: opus 인코딩 → 브라우저
  ```
- VAD: 발화 끝 감지 (1.0초 침묵, 설정 가능 0.5~2.0초)
- **RTT 시간 예산 (P95 < 8초)**:

  | 단계 | 버짓 |
  |------|------|
  | VAD 대기 | 1.0초 |
  | ffmpeg 변환 | 0.2초 |
  | faster-whisper STT | ≤ 3.0초 |
  | LLM (tool_call + response) | ≤ 2.5초 |
  | Polly TTS | ≤ 0.8초 |
  | opus 인코딩 + 네트워크 | ≤ 0.5초 |
  | **합계** | **≤ 8.0초** |

### FR-033: Barge-in 지원 (P1, US-016) ← P2에서 승격
- TTS 재생 중 사용자 음성 감지 → TTS 스트리밍 즉시 중단 → 새 STT 시작
- WebSocket 메시지: `{"type": "interrupt"}` → TTS 스트림 중단
- **P1 단순 구현**: TTS 즉시 중단. 정교한 VAD 기반 감지는 후속.
- FR-032 설계 시 interrupt 훅 포인트 미리 포함

### FR-034: 음성 데모 클라이언트 (P1, US-016)
- 간단한 웹 페이지 (HTML + JS)
- **HTTPS 필수** (브라우저 마이크 접근 요구) — 기존 ALB 인증서 활용
- 브라우저 마이크 (MediaRecorder, opus) → WebSocket → 서버 → 스피커 재생 (AudioContext)
- 대화 내용 텍스트로도 표시 (자막)
- TTS 스킵 버튼 (barge-in 대안)

---

## 9. 비기능 요구사항

### NFR-010: 응답 시간
- 텍스트 턴: P95 < 3초 (최대 2 LLM round-trip + tool_use)
- 음성 턴 (STT+처리+TTS): P95 < 8초 (단계별 버짓은 FR-032 참조)

### NFR-011: 가용성
- 메인 API: ECS 태스크 2개 (기존)
- faster-whisper STT: ECS 태스크 1개 (별도 서비스)
- 헬스체크 실패 시 자동 교체

### NFR-012: 보안
- PII 로그 마스킹 + LLM 응답 필터링 (FR-014)
- WAF 규칙 유지 (기존)
- 더미 API는 VPC 내부만 접근 + API Key 인증

### NFR-013: 비용
- 현재 ~$280/mo
- Whisper STT 태스크 (2vCPU/4GB): ~$50/mo 추가
- Polly Neural: ~$2/mo (데모 규모)
- **예상 총합: ~$332/mo**

### NFR-014: ECS 태스크 구성

| 서비스 | 태스크 수 | CPU | 메모리 | 비고 |
|--------|----------|-----|--------|------|
| callbot-api | 2 | 0.5 vCPU | 1GB | 메인 + 더미 API (사이드카) |
| callbot-stt | 1 | 2 vCPU | 4GB | faster-whisper small |

---

## 10. 구현 우선순위

| Phase | 기간 | 핵심 산출물 | 선행 조건 |
|-------|------|------------|----------|
| **C: 비즈니스 로직** | 2-3주 | 더미 API + OpenAPI spec + 핸들러 5종 + PII 마스킹 | 없음 |
| **D: 모니터링** | 1-2주 | CloudWatch 대시보드 + 메트릭 + 알람 테스트 | C 완료 (Terraform은 병렬 가능) |
| **E: 음성** | 2-3주 | faster-whisper STT + Polly TTS + 데모 클라이언트 | C 완료 |

## 11. 범위 외 (Out of Scope)
- Amazon Connect 연동
- 실제 BSS/OSS API 연동
- 본인인증 (OTP/PASS)
- 다국어 지원
- 부하 테스트 (별도 페이즈)
- GPU 기반 STT (데모 규모에서 불필요)
