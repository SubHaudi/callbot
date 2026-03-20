# Callbot FastAPI 서버 (접착제 코드) 기능정의서

## 1. 개요
- 기존 callbot 비즈니스 로직 모듈들을 FastAPI 서버로 조립하여 HTTP/WebSocket API로 노출
- 핵심 가치: 이미 구현된 164개 파이썬 모듈(NLU, LLM, 세션, 비즈니스, 보안 등)을 ECS Fargate에서 실행 가능한 웹 서비스로 전환

## 2. 배경 및 목적
- **해결하려는 문제**: callbot의 모든 비즈니스 로직이 구현되어 있으나, 이를 실행하는 서버 엔트리포인트와 API 레이어가 없음
- **As-Is**: 단위 테스트로만 검증 가능한 라이브러리 코드 상태 (66개 테스트, 164개 .py 파일)
- **To-Be**: ALB를 통해 HTTP REST + WebSocket으로 접근 가능한 서비스
- **비즈니스 임팩트**: E2E 테스트 환경 구축 + 향후 Amazon Connect 연동의 전제 조건

## 3. 용어 정의

| 용어 | 정의 |
|------|------|
| Turn | 고객 한 번의 발화(입력)와 시스템 응답 1쌍 |
| process_turn() | ConversationOrchestrator의 핵심 메서드. PIF FilterResult를 받아 OrchestratorAction 반환 |
| PIF | Prompt Injection Filter. STT 직후 고객 입력의 인젝션 패턴 탐지 |
| FilterResult | PIF 처리 결과 (is_safe, original_text 등) |
| OrchestratorAction | process_turn() 반환값 (action_type, target_component, context) |
| SessionContext | 세션 상태 객체 (Redis 저장, TTL 20분) |
| 접착제 코드 | 기존 모듈들을 연결하고 서버로 실행하는 진입점/초기화/API 코드 |
| Foundation | Terraform 인프라 레이어 (VPC, IAM, ECR) |
| Application | Terraform 앱 레이어 (ECS, Aurora, ElastiCache, WAF, Monitoring) |

## 4. 사용자 스토리

- **US-001**: As a 개발자, I want callbot을 docker run으로 실행할 수 있게, So that 로컬/ECS에서 동일하게 테스트 가능
- **US-002**: As a E2E 테스터, I want REST API로 텍스트를 보내고 응답을 받을 수 있게, So that Connect 없이 전체 파이프라인 검증 가능
- **US-003**: As a 운영자, I want /health 엔드포인트로 DB/Redis 연결 상태를 확인할 수 있게, So that ALB 헬스체크와 모니터링 가능
- **US-004**: As a 개발자, I want WebSocket으로 실시간 턴 교환이 가능하게, So that 향후 음성 스트리밍 연동 대비
- **US-005**: As a CI/CD 파이프라인, I want Docker 이미지를 ECR에 push하면 ECS가 자동 배포하게, So that 수동 배포 불필요

## 5. 기능 요구사항

### FR-001: FastAPI 앱 생성 및 라우터 마운트 (P0, US-001)
- FastAPI 인스턴스 생성
- 기존 `health/router.py`의 `/health`, `/health/live` 라우터 마운트
- CORS 미들웨어 (dev: allow all origins)

### FR-002: 앱 Startup/Shutdown 라이프사이클 (P0, US-001, US-003)
- startup 시: PostgreSQL 커넥션 풀 생성 (`PostgreSQLConnection`), Redis 클라이언트 생성 (`RedisSessionStore.from_env()`), BedrockService 초기화 (`BedrockConfig.from_env()`)
- health router에 PG/Redis 의존성 주입 (`configure_health_dependencies()`)
- shutdown 시: PG 풀 close, Redis close
- 초기화 실패 시 로그 출력 + 서버는 시작하되 /health에서 503 반환 (graceful degradation)

### FR-003: REST API — POST /api/v1/turn (P0, US-002)
- Request Body: `{ "session_id": str (optional), "caller_id": str, "text": str }`
- session_id 미제공 시 SessionManager.create_session()으로 새 세션 생성
- 파이프라인: PIF.filter() → process_turn() → action_type에 따라 분기:
  - PROCESS_BUSINESS → LLMEngine.generate() → 응답 텍스트
  - SYSTEM_CONTROL → 오케스트레이터 직접 처리 → 시스템 메시지
  - ESCALATE → 상담원 전환 메시지
- psycopg2 동기 호출은 `asyncio.get_event_loop().run_in_executor()`로 래핑하여 이벤트 루프 블로킹 방지
- 의존성 미초기화 상태에서 요청 시 503 Service Unavailable 반환
- Response: `{ "session_id": str, "response_text": str, "action_type": str, "context": dict }`
- 에러 시 HTTP 4xx/5xx + JSON 에러 응답

### FR-004: WebSocket API — WS /api/v1/ws (P1, US-004)
- 연결 시 session_id 쿼리 파라미터 (optional)
- 메시지 포맷: `{ "type": "turn", "text": str }` → 응답: `{ "type": "response", "response_text": str, "action_type": str }`
- 세션 종료: `{ "type": "end" }` → 연결 close
- 연결 끊김 시 세션 유지 (TTL 만료까지)
- Heartbeat: 30초 ping/pong

### FR-005: 환경변수 기반 설정 (P0, US-001)
- `DATABASE_URL`: Aurora 접속 URL (Secrets Manager에서 주입)
- `REDIS_HOST`, `REDIS_PORT`: ElastiCache 엔드포인트
- `BEDROCK_MODEL_ID`: Bedrock 모델 ARN
- `BEDROCK_REGION`: ap-northeast-2
- `ENVIRONMENT`: dev / staging / prod
- `LOG_LEVEL`: DEBUG / INFO / WARNING
- 필수 변수 (`DATABASE_URL`, `REDIS_HOST`, `BEDROCK_MODEL_ID`): 누락 시 서버 시작 실패 (명확한 에러 메시지 출력)
- 선택 변수 (`LOG_LEVEL`, `ENVIRONMENT`, `REDIS_PORT`, `BEDROCK_REGION`): 누락 시 기본값 적용 (INFO, dev, 6379, ap-northeast-2)

### FR-006: Dockerfile (P0, US-001, US-005)
- Base: python:3.12-slim
- 의존성 설치: uv 사용
- EXPOSE 8000
- CMD: uvicorn callbot.server.app:app --host 0.0.0.0 --port 8000
- 헬스체크: HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')" || exit 1
- 프로덕션 빌드 시 `uv sync --no-dev`로 dev 의존성 제외

### FR-007: pyproject.toml (P0, US-001)
- 프로젝트 메타데이터 (name, version, python >=3.12)
- 의존성: fastapi, uvicorn[standard], boto3, psycopg2-binary, redis, pydantic
- dev 의존성: pytest, httpx (FastAPI TestClient용)
- 엔트리포인트: `callbot.server.app:app`

### FR-008: 구조화된 로깅 (P1, US-001)
- JSON 포맷 로그 (structlog 또는 표준 logging + JSON formatter)
- 요청별 correlation_id (X-Request-ID 헤더 또는 자동 생성)
- 턴 처리 시 session_id, caller_id, action_type 로그 포함

### FR-009: 에러 핸들링 미들웨어 (P0, US-002)
- 예상 에러 (SessionNotFoundError 등) → 적절한 HTTP status + JSON
- 예상치 못한 에러 → 500 + generic message (상세는 로그에만)
- PII 유출 방지: 에러 응답에 DB URL, 내부 경로 등 노출 금지

### FR-010: __main__.py 엔트리포인트 (P0, US-001)
- `python -m callbot` 실행 시 uvicorn 서버 시작
- 호스트/포트 환경변수 오버라이드 가능 (기본 0.0.0.0:8000)

## 6. 비기능 요구사항

### NFR-001: 응답 시간 (US-002)
- REST /api/v1/turn P95 응답시간 ≤ 5초 (Bedrock LLM 호출 포함)
- /health P95 ≤ 200ms

### NFR-002: 동시 접속 (US-004)
- 동시 REST 요청 20개 처리 가능 (uvicorn workers=1, async + run_in_executor)
- 동시 WebSocket 연결 10개
- ThreadPoolExecutor max_workers=20 명시 설정
- 용량 초과 시 503 Service Unavailable 반환

### NFR-003: 가용성
- ECS desired=2, min=2 → 단일 태스크 장애 시에도 서비스 유지
- ALB 헬스체크 실패 시 자동 태스크 교체

### NFR-004: 보안
- PII 암호화: KMS CMK 사용 (security/pii_encryptor.py 기존 구현 활용)
- DB 비밀번호: Secrets Manager (Terraform에서 이미 설정)
- HTTPS: ALB 레벨 (ACM 인증서)

### NFR-005: 관측성
- CloudWatch Logs: JSON 구조화 로그 → /ecs/callbot-dev
- X-Ray: 트레이싱 (IAM 권한 이미 설정)
- 11개 CloudWatch Alarms (Terraform 이미 배포)

### NFR-006: 기존 테스트 호환성
- 기존 66개 테스트 100% 통과 유지
- 새 코드에 대한 추가 테스트 작성

## 7. 기술 설계

### 아키텍처 개요
```
Client → ALB(:80/443) → ECS Fargate(:8000) → FastAPI App
                                                ├── /health → PG/Redis 체크
                                                ├── /api/v1/turn → REST adapter
                                                └── /api/v1/ws → WebSocket adapter
                                                         │
                                                    ┌────┴────┐
                                                    │ Pipeline │
                                                    └────┬────┘
                                              PIF → Orchestrator → LLM/Business
                                                         │
                                                ┌────────┼────────┐
                                                PG(Aurora)  Redis   Bedrock
```

### 주요 컴포넌트와 역할

| 컴포넌트 | 파일 | 역할 |
|----------|------|------|
| App Factory | `server/app.py` | FastAPI 앱 생성, 라이프사이클, 미들웨어 |
| Config | `server/config.py` | 환경변수 → 설정 객체 |
| REST Routes | `server/routes.py` | POST /api/v1/turn |
| WS Routes | `server/ws.py` | WS /api/v1/ws |
| Pipeline | `server/pipeline.py` | PIF → Orchestrator → LLM/Business 조합 |
| Health | `health/router.py` | 기존 코드 그대로 사용 |

### 기술 스택
- Python 3.12, FastAPI, uvicorn
- psycopg2-binary (PG), redis-py (Redis), boto3 (Bedrock)
- Docker (python:3.12-slim base)

## 8. 데이터 모델
- 기존 모델 그대로 사용 (`session/models.py`, `orchestrator/models.py`, `nlu/models.py`)
- 새로 추가하는 DB 테이블 없음
- API 요청/응답용 Pydantic 모델만 신규 정의

### API Pydantic 모델

```python
class TurnRequest(BaseModel):
    session_id: str | None = None
    caller_id: str
    text: str

class TurnResponse(BaseModel):
    session_id: str
    response_text: str
    action_type: str  # PROCESS_BUSINESS | SYSTEM_CONTROL | ESCALATE
    context: dict = {}
```

## 9. API 설계

### REST

| Method | Path | Request | Response | Status |
|--------|------|---------|----------|--------|
| POST | /api/v1/turn | TurnRequest | TurnResponse | 200 |
| GET | /health | - | HealthCheckResult | 200/503 |
| GET | /health/live | - | LivenessResult | 200 |

### WebSocket

| Path | 방향 | 메시지 |
|------|------|--------|
| /api/v1/ws?session_id=xxx | Client→Server | `{"type":"turn","text":"..."}` |
| | Server→Client | `{"type":"response","response_text":"...","action_type":"..."}` |
| | Client→Server | `{"type":"end"}` → 연결 종료 |

### 인증/인가
- Auth Level 1 (현재): 인증 없음 (WAF + allowed_cidrs로 접근 제한)
- Auth Level 2 (향후): API Key 또는 IAM 기반 인증

## 10. UI/UX 고려사항
- UI 없음 (API 서비스)
- API 문서: FastAPI 자동 생성 Swagger UI (/docs)
- 향후 관리자 대시보드 고려 가능 (범위 외)

## 11. 마일스톤 및 일정

### Phase A: 핵심 서버 (착수 후 1일)
- FR-001 ~ FR-003, FR-005 ~ FR-007, FR-009 ~ FR-010
- Dockerfile + pyproject.toml
- REST /api/v1/turn 작동
- ECR push + ECS 배포

### Phase B: WebSocket + 관측성 (착수 후 2일)
- FR-004, FR-008
- WebSocket /api/v1/ws
- 구조화 로깅 + correlation_id

### Phase C: CI/CD (착수 후 3일)
- GitHub Actions 워크플로우
- main push → ECR → ECS 자동 배포

## 12. 리스크 및 완화 방안

### RISK-001: 기존 모듈 import 호환성
- **확률**: M, **영향**: H
- 기존 코드가 패키지 구조 없이 작성됨 (pyproject.toml 없음)
- **완화**: pyproject.toml에 packages 설정으로 callbot을 패키지화. import 경로 변경 최소화.

### RISK-002: psycopg2 동기 드라이버 + FastAPI async
- **확률**: H, **영향**: M
- 기존 PG 코드가 psycopg2 (동기). FastAPI는 async 기반.
- **완화**: run_in_executor로 동기 호출 래핑 (FR-003에 반영 완료). asyncpg 마이그레이션은 범위 외.

### RISK-003: Aurora Secrets Manager URL 포맷
- **확률**: M, **영향**: M
- `manage_master_user_password`로 생성된 시크릿의 값 형식이 DSN이 아닐 수 있음
- **완화**: 시크릿 값을 파싱하여 DSN 조합하는 유틸리티 작성

### RISK-004: Dockerfile HEALTHCHECK
- **확률**: L (FR-006에서 python urllib 기반으로 해결), **영향**: L
- **완화**: FR-006에 python 기반 HEALTHCHECK 반영 완료.

## 13. 성공 지표

| KPI | 목표값 | 측정 방법 | 주기 |
|-----|--------|-----------|------|
| /health 200 응답 | 99.9% uptime | ALB 헬스체크 | 실시간 |
| REST /api/v1/turn P95 | ≤ 5초 | CloudWatch ALB latency | 일간 |
| 기존 테스트 통과율 | 100% (66/66) | pytest CI | 커밋마다 |
| 신규 테스트 커버리지 | ≥ 80% | pytest-cov | 커밋마다 |

## 14. 의존성

| 의존성 | 유형 | 리스크 |
|--------|------|--------|
| Aurora Serverless v2 | 인프라 (Terraform 배포 완료) | L |
| ElastiCache Serverless Redis | 인프라 (배포 완료) | L |
| AWS Bedrock Claude | 외부 서비스 | M (throttling) |
| ECR + ECS Fargate | 인프라 (배포 완료) | L |
| 기존 callbot 모듈 164개 | 내부 코드 | M (import 호환성) |

## 15. 범위 제외 사항

| 항목 | 향후 고려 |
|------|-----------|
| Amazon Connect 연동 | 본 프로젝트 완료 이후 별도 프로젝트 |
| 음성 STT/TTS 실시간 스트리밍 | Connect 연동 시 |
| 관리자 대시보드 UI | 필요 시 |
| asyncpg 마이그레이션 | 성능 이슈 발생 시 |
| 멀티 테넌트 | 현재 단일 서비스 |
| API 인증/인가 | WAF + CIDRS로 충분. 필요 시 API Key 추가 |
