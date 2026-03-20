# Callbot FastAPI 서버 (접착제 코드) 구현 계획

## 구현 원칙
- TDD 사이클: Red → Green → Refactor
- Tidy First: 구조적 변경과 행위적 변경을 분리
- 구조적 변경 먼저, 행위적 변경은 그 다음
- 각 커밋은 구조적 또는 행위적 중 하나만 포함

## 요구사항 추적 매트릭스

| 요구사항 ID | 요구사항 요약 | 관련 태스크 |
|-------------|-------------|-------------|
| FR-001 | FastAPI 앱 생성 + 라우터 마운트 | TASK-001, TASK-002, TASK-003 |
| FR-002 | Startup/Shutdown 라이프사이클 | TASK-004, TASK-005, TASK-006, TASK-007 |
| FR-003 | REST POST /api/v1/turn | TASK-008, TASK-009, TASK-010, TASK-011 |
| FR-005 | 환경변수 기반 설정 | TASK-004, TASK-005 |
| FR-006 | Dockerfile | TASK-017, TASK-018 |
| FR-007 | pyproject.toml | TASK-001 |
| FR-009 | 에러 핸들링 미들웨어 | TASK-012, TASK-013 |
| FR-010 | __main__.py 엔트리포인트 | TASK-014, TASK-015 |
| FR-004 | WebSocket API | TASK-019, TASK-020, TASK-021 |
| FR-008 | 구조화된 로깅 | TASK-022, TASK-023 |
| NFR-001 | 응답 시간 | 인프라(ALB) + TASK-009 (pipeline) |
| NFR-002 | 동시 접속 제한 | TASK-015a, TASK-015b |
| NFR-003 | 가용성 | 인프라(ECS desired=2) |
| NFR-004 | 보안 | 인프라(WAF, KMS, Secrets Manager) |
| NFR-005 | 관측성 | TASK-022, TASK-023, 인프라(CloudWatch) |
| NFR-006 | 기존 테스트 호환성 | TASK-001 (전체 테스트 통과 확인) |

## 구현 순서 개요

Phase A (핵심 서버):
1. 패키지 구조 + pyproject.toml (Structural)
2. Config 모듈 (Red→Green)
3. FastAPI 앱 + health 마운트 (Red→Green)
4. Startup/Shutdown 라이프사이클 (Red→Green)
5. Pipeline 조합 (Red→Green)
6. REST /api/v1/turn (Red→Green)
7. 에러 핸들링 (Red→Green)
8. __main__.py (Red→Green)
9. Dockerfile + docker-compose (Structural)

Phase B (WebSocket + 로깅):
10. WebSocket /api/v1/ws (Red→Green)
11. 구조화 로깅 (Red→Green)

## 태스크 목록

### TASK-001: pyproject.toml + 패키지 구조 설정
- **변경 유형**: Structural
- **TDD 단계**: Setup
- **설명**: pyproject.toml 생성, callbot을 패키지로 정의, server/ 디렉토리 생성
- **구현**:
  - `pyproject.toml` — name, version, python>=3.12, dependencies (fastapi, uvicorn[standard], boto3, psycopg2-binary, redis, pydantic), dev dependencies (pytest, httpx, pytest-asyncio)
  - `callbot/server/__init__.py` 빈 파일
- **의존성**: 없음
- **관련 요구사항**: FR-007, NFR-006
- **완료 기준**: `uv sync` 성공, 기존 66개 테스트 100% 통과
- **커밋 메시지 예시**: "structural: add pyproject.toml and server package"

### TASK-002: FastAPI 앱 팩토리 — 테스트
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: create_app() 팩토리 함수의 테스트 작성
- **테스트**:
  - `test_create_app_returns_fastapi_instance`
  - `test_health_router_is_mounted` — GET /health/live → 200
  - `test_cors_middleware_is_added`
- **의존성**: TASK-001
- **관련 요구사항**: FR-001
- **완료 기준**: 테스트 작성, 실행 시 FAIL 확인
- **커밋 메시지 예시**: "behavioral(red): add tests for FastAPI app factory"

### TASK-003: FastAPI 앱 팩토리 — 구현
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: `server/app.py`에 create_app() 구현
- **구현**:
  - `create_app()` → FastAPI 인스턴스 생성, health router 마운트, CORS 미들웨어 추가
  - 모듈 레벨 `app = create_app()` (uvicorn 엔트리포인트용)
- **의존성**: TASK-002
- **관련 요구사항**: FR-001
- **완료 기준**: TASK-002 테스트 전부 PASS
- **커밋 메시지 예시**: "behavioral(green): implement FastAPI app factory"

### TASK-004: Config 모듈 — 테스트
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: 환경변수 기반 설정 객체 테스트
- **테스트**:
  - `test_config_reads_required_env_vars` — DATABASE_URL, REDIS_HOST, BEDROCK_MODEL_ID 설정 시 정상 로드
  - `test_config_fails_on_missing_required_vars` — DATABASE_URL 또는 BEDROCK_MODEL_ID 누락 시 ValueError
  - `test_config_uses_defaults_for_optional_vars` — LOG_LEVEL 미설정 시 "INFO", REDIS_PORT 미설정 시 6379
- **의존성**: TASK-001
- **관련 요구사항**: FR-005
- **완료 기준**: 테스트 FAIL 확인
- **커밋 메시지 예시**: "behavioral(red): add tests for server config"

### TASK-005: Config 모듈 — 구현
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: `server/config.py`에 ServerConfig dataclass 구현
- **구현**:
  - `ServerConfig` dataclass: database_url, redis_host, redis_port, bedrock_model_id, bedrock_region, environment, log_level
  - `ServerConfig.from_env()` classmethod: os.environ에서 읽기, 필수 변수 누락 시 ValueError
- **의존성**: TASK-004
- **관련 요구사항**: FR-005
- **완료 기준**: TASK-004 테스트 PASS
- **커밋 메시지 예시**: "behavioral(green): implement server config"

### TASK-006: Startup/Shutdown 라이프사이클 — 테스트
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: 앱 lifespan 이벤트 테스트
- **테스트**:
  - `test_startup_initializes_dependencies` — app startup 후 app.state에 pg_connection, redis_store, bedrock_service 존재
  - `test_startup_configures_health_dependencies` — health router에 PG/Redis 주입됨
  - `test_startup_failure_sets_unhealthy_state` — DB 연결 실패 시 app.state.healthy = False
  - `test_shutdown_closes_connections` — shutdown 후 PG 풀 close 호출됨
- **의존성**: TASK-003, TASK-005
- **관련 요구사항**: FR-002
- **완료 기준**: 테스트 FAIL 확인
- **커밋 메시지 예시**: "behavioral(red): add tests for app lifespan"

### TASK-007: Startup/Shutdown 라이프사이클 — 구현
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: FastAPI lifespan context manager 구현
- **구현**:
  - `server/app.py`에 lifespan async context manager
  - startup: ServerConfig.from_env() → PG pool → Redis client → Bedrock service → app.state에 저장 → configure_health_dependencies()
  - 초기화 실패 시 로그 + app.state.healthy = False (서버는 시작)
  - shutdown: PG pool close, Redis close
- **의존성**: TASK-006
- **관련 요구사항**: FR-002
- **완료 기준**: TASK-006 테스트 PASS
- **커밋 메시지 예시**: "behavioral(green): implement app lifespan"

### TASK-008: Pipeline 조합 모듈 — 테스트
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: PIF → Orchestrator → LLM/Business 파이프라인 테스트
- **테스트**:
  - `test_pipeline_processes_safe_input` — 안전한 입력 → PROCESS_BUSINESS → LLM 응답
  - `test_pipeline_handles_injection` — 인젝션 탐지 → SYSTEM_CONTROL 응답
  - `test_pipeline_creates_session_when_missing` — session_id 없으면 새 세션 생성
  - `test_pipeline_wraps_sync_calls_in_executor` — PG 호출이 run_in_executor로 래핑됨
  - `test_pipeline_handles_escalation` — 상담원 전환 조건 → ESCALATE 응답
- **의존성**: TASK-005
- **관련 요구사항**: FR-003
- **완료 기준**: 테스트 FAIL 확인
- **커밋 메시지 예시**: "behavioral(red): add tests for turn pipeline"

### TASK-009: Pipeline 조합 모듈 — 구현
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: `server/pipeline.py`에 TurnPipeline 클래스 구현
- **구현**:
  - `TurnPipeline.__init__(pif, orchestrator, session_manager, llm_engine)`
  - `async process(session_id, caller_id, text) → TurnResult`
  - 동기 PG 호출을 `loop.run_in_executor(executor, ...)` 래핑
  - ThreadPoolExecutor(max_workers=20)
- **의존성**: TASK-008
- **관련 요구사항**: FR-003
- **완료 기준**: TASK-008 테스트 PASS
- **커밋 메시지 예시**: "behavioral(green): implement turn pipeline"

### TASK-010: REST /api/v1/turn — 테스트
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: REST 엔드포인트 테스트 (httpx AsyncClient 사용)
- **테스트**:
  - `test_turn_endpoint_returns_response` — POST /api/v1/turn → 200 + TurnResponse
  - `test_turn_endpoint_creates_session` — session_id 없이 요청 → 응답에 session_id 포함
  - `test_turn_endpoint_invalid_body` — text 누락 → 422
  - `test_turn_endpoint_when_unhealthy` — 의존성 미초기화 → 503
- **의존성**: TASK-009
- **관련 요구사항**: FR-003
- **완료 기준**: 테스트 FAIL 확인
- **커밋 메시지 예시**: "behavioral(red): add tests for REST turn endpoint"

### TASK-011: REST /api/v1/turn — 구현
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: `server/routes.py`에 REST 라우터 구현
- **구현**:
  - `POST /api/v1/turn` → TurnRequest 파싱 → TurnPipeline.process() → TurnResponse
  - 의존성 미초기화 시 503 반환
  - Pydantic 모델: TurnRequest, TurnResponse
- **의존성**: TASK-010
- **관련 요구사항**: FR-003
- **완료 기준**: TASK-010 테스트 PASS
- **커밋 메시지 예시**: "behavioral(green): implement REST turn endpoint"

### TASK-012: 에러 핸들링 미들웨어 — 테스트
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: 전역 에러 핸들러 테스트
- **테스트**:
  - `test_session_not_found_returns_404` — SessionNotFoundError → 404
  - `test_unexpected_error_returns_500_without_details` — RuntimeError → 500 + generic message
  - `test_error_response_no_pii_leak` — 에러 응답에 DB URL 미포함
- **의존성**: TASK-011
- **관련 요구사항**: FR-009
- **완료 기준**: 테스트 FAIL 확인
- **커밋 메시지 예시**: "behavioral(red): add tests for error handling middleware"

### TASK-013: 에러 핸들링 미들웨어 — 구현
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: FastAPI exception_handler 등록
- **구현**:
  - SessionNotFoundError → 404
  - ValueError → 400
  - 나머지 Exception → 500 + `{"detail": "Internal server error"}`
- **의존성**: TASK-012
- **관련 요구사항**: FR-009
- **완료 기준**: TASK-012 테스트 PASS
- **커밋 메시지 예시**: "behavioral(green): implement error handling middleware"

### TASK-014: __main__.py — 테스트
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: 엔트리포인트 테스트
- **테스트**:
  - `test_main_calls_uvicorn_run` — __main__.py 실행 시 uvicorn.run() 호출 확인 (mock)
  - `test_main_respects_env_port` — PORT 환경변수 설정 시 해당 포트 사용
- **의존성**: TASK-003
- **관련 요구사항**: FR-010
- **완료 기준**: 테스트 FAIL 확인
- **커밋 메시지 예시**: "behavioral(red): add tests for __main__ entrypoint"

### TASK-015: __main__.py — 구현
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: `callbot/__main__.py` 구현
- **구현**:
  - `uvicorn.run("callbot.server.app:app", host=HOST, port=PORT, ws_ping_interval=30, ws_ping_timeout=30)`
  - HOST 기본 0.0.0.0, PORT 기본 8000, 환경변수 오버라이드
- **의존성**: TASK-014
- **관련 요구사항**: FR-010
- **완료 기준**: TASK-014 테스트 PASS
- **커밋 메시지 예시**: "behavioral(green): implement __main__ entrypoint"

### TASK-016: Phase A 리팩토링
- **변경 유형**: Structural
- **TDD 단계**: Refactor
- **설명**: Phase A 코드 전체 리팩토링 — 중복 제거, 네이밍 개선, import 정리
- **의존성**: TASK-013, TASK-015a
- **관련 요구사항**: 전체
- **완료 기준**: 전체 테스트 PASS, 코드 품질 향상
- **커밋 메시지 예시**: "structural: refactor Phase A server code"

### TASK-015a: 동시접속 제한 미들웨어 — 테스트
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: NFR-002 동시접속 제한 테스트
- **테스트**:
  - `test_concurrent_rest_limit` — 동시 REST 20개 초과 시 503
  - `test_concurrent_ws_limit` — 동시 WebSocket 10개 초과 시 연결 거부
- **의존성**: TASK-011
- **관련 요구사항**: NFR-002
- **완료 기준**: 테스트 FAIL 확인
- **커밋 메시지 예시**: "behavioral(red): add tests for concurrency limit middleware"

### TASK-015b: 동시접속 제한 미들웨어 — 구현
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: asyncio.Semaphore 기반 동시접속 제한
- **구현**:
  - REST: Semaphore(20), 초과 시 503
  - WebSocket: Semaphore(10), 초과 시 연결 close(1013)
  - create_app()에 미들웨어로 등록
- **의존성**: TASK-015a
- **관련 요구사항**: NFR-002
- **완료 기준**: TASK-015a 테스트 PASS
- **커밋 메시지 예시**: "behavioral(green): implement concurrency limit middleware"
- **완료 기준**: 전체 테스트 PASS, 코드 품질 향상
- **커밋 메시지 예시**: "structural: refactor Phase A server code"

### TASK-017: Dockerfile 작성
- **변경 유형**: Structural
- **TDD 단계**: Setup
- **설명**: Dockerfile + .dockerignore 작성
- **구현**:
  - `Dockerfile`: python:3.12-slim, uv 설치, COPY + uv sync --no-dev, EXPOSE 8000, HEALTHCHECK python urllib, CMD uvicorn
  - `.dockerignore`: .git, __pycache__, tests/, .pytest_cache/
- **의존성**: TASK-016
- **관련 요구사항**: FR-006
- **완료 기준**: `docker build` 성공
- **커밋 메시지 예시**: "structural: add Dockerfile and .dockerignore"

### TASK-018: docker-compose.yml (로컬 테스트용)
- **변경 유형**: Structural
- **TDD 단계**: Setup
- **설명**: 로컬 개발용 docker-compose (app + postgres + redis)
- **구현**:
  - callbot-api: Dockerfile, ports 8000, env vars
  - postgres: postgres:16-alpine, POSTGRES_DB=callbot
  - redis: redis:7-alpine, port 6379
- **의존성**: TASK-017
- **관련 요구사항**: FR-006
- **완료 기준**: `docker compose up` 후 /health/live 200 응답
- **커밋 메시지 예시**: "structural: add docker-compose for local development"

### TASK-019: WebSocket 라우트 — 테스트
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: WebSocket 엔드포인트 테스트
- **테스트**:
  - `test_ws_turn_exchange` — 연결 → turn 메시지 → response 수신
  - `test_ws_end_message_closes` — end 메시지 → 연결 종료
  - `test_ws_creates_session` — session_id 없이 연결 → 세션 자동 생성
- **의존성**: TASK-009
- **관련 요구사항**: FR-004
- **완료 기준**: 테스트 FAIL 확인
- **커밋 메시지 예시**: "behavioral(red): add tests for WebSocket endpoint"

### TASK-020: WebSocket 라우트 — 구현
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: `server/ws.py`에 WebSocket 라우터 구현
- **구현**:
  - `WS /api/v1/ws` — accept → session 생성/조회 → 메시지 루프 → TurnPipeline.process()
  - `{"type":"end"}` → graceful close
  - 연결 끊김 시 세션 유지 (Redis TTL)
  - 30초 ping/pong heartbeat (uvicorn 기본 WebSocket ping 활용)
- **의존성**: TASK-019
- **관련 요구사항**: FR-004
- **완료 기준**: TASK-019 테스트 PASS
- **커밋 메시지 예시**: "behavioral(green): implement WebSocket endpoint"

### TASK-021: WebSocket 라우터 앱 마운트
- **변경 유형**: Structural
- **TDD 단계**: Setup
- **설명**: WS 라우터를 create_app()에 마운트
- **의존성**: TASK-020
- **관련 요구사항**: FR-004
- **완료 기준**: 전체 테스트 PASS
- **커밋 메시지 예시**: "structural: mount WebSocket router in app factory"

### TASK-022: 구조화 로깅 — 테스트
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: JSON 로깅 + correlation_id 테스트
- **테스트**:
  - `test_request_has_correlation_id` — 응답 헤더에 X-Request-ID 포함
  - `test_log_output_is_json` — 로그 출력이 JSON 파싱 가능
  - `test_log_includes_session_context` — 턴 처리 로그에 session_id 포함
- **의존성**: TASK-011
- **관련 요구사항**: FR-008
- **완료 기준**: 테스트 FAIL 확인
- **커밋 메시지 예시**: "behavioral(red): add tests for structured logging"

### TASK-023: 구조화 로깅 — 구현
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: 미들웨어 + logging 설정
- **구현**:
  - RequestID 미들웨어: X-Request-ID 헤더 읽기 또는 UUID 생성
  - JSON Formatter: 표준 logging + dictConfig
  - 턴 처리 시 session_id, caller_id, action_type 로그
- **의존성**: TASK-022
- **관련 요구사항**: FR-008
- **완료 기준**: TASK-022 테스트 PASS
- **커밋 메시지 예시**: "behavioral(green): implement structured logging"

## 태스크 의존성 그래프

```
TASK-001 (pyproject.toml)
├── TASK-002 → TASK-003 (app factory)
│   ├── TASK-006 → TASK-007 (lifespan)
│   │   └── (uses TASK-005)
│   └── TASK-014 → TASK-015 (__main__)
├── TASK-004 → TASK-005 (config)
└── TASK-008 → TASK-009 (pipeline)
    ├── TASK-010 → TASK-011 (REST routes)
    │   ├── TASK-012 → TASK-013 (error handling)
    │   └── TASK-022 → TASK-023 (logging)
    └── TASK-019 → TASK-020 → TASK-021 (WebSocket)

TASK-015 → TASK-016 (refactor) → TASK-017 (Dockerfile) → TASK-018 (docker-compose)
```

## 테스트 전략
- **단위 테스트**: Config, Pipeline, 각 라우트 핸들러 (mock 기반)
- **통합 테스트**: httpx AsyncClient로 FastAPI 앱 전체 테스트
- **E2E 테스트**: docker-compose up 후 curl/httpx로 /health + /api/v1/turn
- **테스트 커버리지 목표**: server/ 디렉토리 80% 이상
- **기존 테스트**: 66개 전부 통과 유지
