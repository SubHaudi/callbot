# 테스트 전략 Gap 해소 구현 계획

## 구현 원칙
- TDD 사이클: Red → Green → Refactor
- Tidy First: 구조적 변경과 행위적 변경을 분리
- 구조적 변경 먼저, 행위적 변경은 그 다음
- 각 커밋은 구조적 또는 행위적 중 하나만 포함

## 요구사항 추적 매트릭스

| 요구사항 ID | 요구사항 요약 | 관련 태스크 |
|-------------|-------------|-------------|
| FR-001 | _lifespan fail-fast | TASK-004A, TASK-004B, TASK-004C |
| FR-002 | bootstrap.py 분리 | TASK-001, TASK-002, TASK-003, TASK-004A, TASK-005, TASK-006, TASK-006A |
| FR-003 | routes.py pipeline None 방어 | TASK-007, TASK-008 |
| FR-004 | handle_text fallback 가드 제거 + WS pipeline 방어 | TASK-009, TASK-010 |
| FR-005 | Wiring test 신설 | TASK-005, TASK-006, TASK-008, TASK-010 |
| FR-006 | CI smoke job | TASK-011 |
| FR-007 | 배포 후 smoke script | TASK-012 |
| FR-008 | PR 체크리스트 | TASK-013 |

## 구현 순서 개요

1. Structural: bootstrap.py 파일 생성 + 조립 함수 껍데기
2. Behavioral: assemble_pipeline 구현 + 테스트
3. Structural: _lifespan에서 bootstrap 호출로 리팩토링
4. Behavioral: fail-fast (raise) + 테스트
5. Behavioral: assemble_voice_server + 테스트
6. Behavioral: wiring 통합 테스트 (조립 전체 경로)
7. Behavioral: routes.py pipeline None → 503 + 테스트
8. Behavioral: handle_text fallback 가드 제거 + WS pipeline 방어 + 테스트
9. Structural: CI smoke job
10. Structural: smoke_test.sh + PR template

## 태스크 목록

### TASK-001: bootstrap.py 파일 생성 — 함수 시그니처만
- **변경 유형**: Structural
- **TDD 단계**: Setup
- **설명**: `server/bootstrap.py` 생성. `assemble_pipeline`, `assemble_voice_server`, `init_stt_engine`, `init_tts_engine` 함수 시그니처와 docstring만 작성. 구현은 `raise NotImplementedError`.
- **의존성**: 없음
- **관련 요구사항**: FR-002
- **완료 기준**: 파일 존재, import 가능, 기존 테스트 전체 통과
- **커밋 메시지 예시**: "structural: add bootstrap.py with function signatures"

### TASK-002: assemble_pipeline 테스트 작성 (Red)
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: `server/tests/test_wiring.py` 생성. 3개 테스트 케이스:
  1. `test_raises_when_pg_is_none` — DB None → RuntimeError
  2. `test_assembles_with_mock_db` — mock DB → Pipeline 생성 + 내부 컴포넌트 실제 객체
  3. `test_pipeline_process_is_async` — process가 async 함수인지
- **테스트**: NotImplementedError로 실패 예상
- **의존성**: TASK-001
- **관련 요구사항**: FR-002, FR-005
- **완료 기준**: 3개 테스트 작성, 모두 FAIL
- **커밋 메시지 예시**: "behavioral(red): add assemble_pipeline wiring tests"

### TASK-003: assemble_pipeline 구현 (Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: `assemble_pipeline(pg_connection, redis_store, bedrock_service)` 구현.
  - pg_connection None → RuntimeError("PostgreSQL connection required")
  - PIF, Repository, SessionStore, SessionManager, Orchestrator, TurnPipeline 조립
  - bedrock_service를 llm_engine으로 주입
- **구현**: TASK-002 테스트를 통과시키는 최소 코드
- **의존성**: TASK-002
- **관련 요구사항**: FR-002, FR-001
- **완료 기준**: TASK-002 테스트 3개 PASS + 기존 테스트 전체 통과
- **커밋 메시지 예시**: "behavioral(green): implement assemble_pipeline"

### TASK-004A: _lifespan 리팩토링 — bootstrap 호출로 전환 (구조적만)
- **변경 유형**: Structural
- **TDD 단계**: Refactor
- **설명**: `server/app.py`의 `_lifespan`에서 인라인 Pipeline 조립 코드를 `bootstrap.assemble_pipeline()` 호출로 교체. except 블록은 기존 동작 유지 (이 태스크에서는 변경하지 않음).
- **의존성**: TASK-003
- **관련 요구사항**: FR-002
- **완료 기준**: 기존 테스트 전체 통과, _lifespan이 bootstrap 함수를 호출, except 동작 미변경
- **커밋 메시지 예시**: "structural: refactor _lifespan to use bootstrap.assemble_pipeline"

### TASK-004B: fail-fast 테스트 (Red)
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: `test_wiring.py`에 1개 테스트 추가:
  - `test_lifespan_raises_on_db_failure` — DB 초기화 실패 시 _lifespan이 예외를 전파하는지 검증 (삼키지 않음)
  - `_init_pg`를 mock하여 Exception raise → lifespan이 propagate하는지 확인
- **테스트**: 현재 except에서 삼키므로 FAIL 예상
- **의존성**: TASK-004A
- **관련 요구사항**: FR-001
- **완료 기준**: 1개 테스트 FAIL
- **커밋 메시지 예시**: "behavioral(red): add fail-fast lifespan test"

### TASK-004C: fail-fast 구현 (Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: `_lifespan`의 except 블록에서 `raise` 적용. `logger.critical(...)` 후 예외 재발생.
- **의존성**: TASK-004B
- **관련 요구사항**: FR-001
- **완료 기준**: TASK-004B 테스트 PASS + 기존 테스트 전체 통과
- **커밋 메시지 예시**: "behavioral(green): apply fail-fast raise in _lifespan"

### TASK-005: assemble_voice_server 테스트 작성 (Red)
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: `test_wiring.py`에 3개 테스트 추가:
  1. `test_voice_server_without_stt_tts` — STT/TTS 없이 생성
  2. `test_voice_server_with_all_engines` — 전체 엔진으로 생성 + 속성 확인
  3. `test_voice_server_can_create_session` — 세션 생성 가능
- **테스트**: NotImplementedError로 실패 예상
- **의존성**: TASK-003
- **관련 요구사항**: FR-002, FR-005
- **완료 기준**: 3개 테스트 FAIL
- **커밋 메시지 예시**: "behavioral(red): add assemble_voice_server wiring tests"

### TASK-006: assemble_voice_server + init_stt/tts 구현 (Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: 
  - `assemble_voice_server(pipeline, stt_engine, tts_engine)` — VoiceServer 생성 (background cleanup은 호출자 책임)
  - `init_stt_engine()` — TranscribeSTTEngine 생성, 실패 시 None + 로그
  - `init_tts_engine()` — PollyTTSEngine 생성, 실패 시 None + 로그
- **의존성**: TASK-005
- **관련 요구사항**: FR-002
- **완료 기준**: TASK-005 테스트 3개 PASS + 기존 테스트 전체 통과
- **커밋 메시지 예시**: "behavioral(green): implement assemble_voice_server + init engines"

### TASK-006A: _lifespan VoiceServer 조립을 bootstrap 호출로 교체
- **변경 유형**: Structural
- **TDD 단계**: Refactor
- **설명**: `_lifespan`에서 인라인 VoiceServer/STT/TTS 초기화 코드를 `bootstrap.assemble_voice_server()`, `init_stt_engine()`, `init_tts_engine()` 호출로 교체.
- **의존성**: TASK-006
- **관련 요구사항**: FR-002
- **완료 기준**: 기존 테스트 전체 통과, _lifespan이 bootstrap 함수를 호출
- **커밋 메시지 예시**: "structural: refactor _lifespan VoiceServer init to use bootstrap"

### TASK-007: routes.py pipeline None 방어 테스트 (Red)
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: `test_wiring.py`에 1개 테스트 추가:
  - `test_turn_returns_503_when_pipeline_missing` — pipeline 미설정 시 503 반환
  - FastAPI app을 lifespan 없이 생성, router만 include, POST /api/v1/turn → 503
- **테스트**: 현재 healthy=False 가드에 걸려 503이 나올 수 있으므로, pipeline 속성 자체의 방어를 확인
- **의존성**: TASK-004C
- **관련 요구사항**: FR-003, FR-005
- **완료 기준**: 1개 테스트 작성. 응답 body에 `"Pipeline not initialized"` 메시지를 검증하여 Red 보장 (기존 healthy 가드의 503 메시지와 구별)
- **커밋 메시지 예시**: "behavioral(red): add pipeline None defense test"

### TASK-008: routes.py pipeline None → 503 구현 (Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: `routes.py`의 `turn_endpoint`에서 `getattr(request.app.state, "pipeline", None)` 체크 추가. None이면 503 + `{"detail": "Pipeline not initialized"}` 반환.
- **의존성**: TASK-007
- **관련 요구사항**: FR-003
- **완료 기준**: TASK-007 테스트 PASS + 기존 테스트 전체 통과
- **커밋 메시지 예시**: "behavioral(green): add pipeline None guard in routes.py"

### TASK-009: handle_text fallback 가드 제거 + WS pipeline 방어 테스트 (Red)
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **설명**: `voice_io/tests/` 또는 기존 테스트 파일에 테스트 추가:
  1. `test_handle_text_works_without_fallback_mode` — is_text_fallback=False 상태에서 텍스트 입력 성공
  2. `test_handle_text_returns_error_when_pipeline_none` — pipeline None 시 에러 응답
- **의존성**: TASK-006A
- **관련 요구사항**: FR-004, FR-005
- **완료 기준**: 테스트 FAIL (현재 fallback 가드가 차단)
- **커밋 메시지 예시**: "behavioral(red): add handle_text no-fallback-guard tests"

### TASK-010: handle_text fallback 가드 제거 + WS pipeline 방어 구현 (Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **설명**: 
  - `voice_server.py`의 `handle_text`에서 `is_text_fallback` 체크 제거
  - pipeline None 시 에러 JSON 응답 반환 추가
- **의존성**: TASK-009
- **관련 요구사항**: FR-004
- **완료 기준**: TASK-009 테스트 PASS + 기존 테스트 전체 통과
- **커밋 메시지 예시**: "behavioral(green): remove text fallback guard, add WS pipeline defense"

### TASK-011: CI smoke job 추가
- **변경 유형**: Structural
- **TDD 단계**: Setup
- **설명**: `.github/workflows/ci.yml`에 `smoke` job 추가.
  - `needs: test`
  - services: postgres:16 (health check), redis:7 (health check)
  - env: DATABASE_URL, REDIS_HOST, BEDROCK_MODEL_ID, CALLBOT_EXTERNAL_BACKEND=fake
  - uvicorn으로 서버 부팅 → sleep 5 → curl /health → curl /api/v1/turn
- **의존성**: TASK-004C
- **관련 요구사항**: FR-006
- **완료 기준**: CI workflow 파일 유효 (actionlint 통과)
- **커밋 메시지 예시**: "structural: add CI smoke job with PG+Redis services"

### TASK-012: 배포 후 smoke script
- **변경 유형**: Structural
- **TDD 단계**: Setup
- **설명**: `tests/smoke_test.sh` 생성. 실행 가능(chmod +x). Health check + Turn API + WebSocket 연결 확인. 실패 시 exit 1.
- **의존성**: 없음
- **관련 요구사항**: FR-007
- **완료 기준**: 스크립트 존재, shellcheck 통과
- **커밋 메시지 예시**: "structural: add post-deploy smoke test script"

### TASK-013: PR 체크리스트 템플릿
- **변경 유형**: Structural
- **TDD 단계**: Setup
- **설명**: `.github/PULL_REQUEST_TEMPLATE.md` 생성. 배포 안전 체크리스트 + mock 원칙 포함.
- **의존성**: 없음
- **관련 요구사항**: FR-008
- **완료 기준**: 파일 존재
- **커밋 메시지 예시**: "structural: add PR checklist template"

## 태스크 의존성 그래프

```
TASK-001 → TASK-002 → TASK-003 → TASK-004A → TASK-004B → TASK-004C → TASK-007 → TASK-008
                                       ↓                                    ↘ TASK-011
                                  TASK-005 → TASK-006 → TASK-006A → TASK-009 → TASK-010

TASK-012 (독립)
TASK-013 (독립)
```

## 테스트 전략
- **Wiring 테스트** (test_wiring.py): 7개 — mock 최소화, 실제 컴포넌트 조립 검증
- **기존 Unit 테스트**: 333+개 전체 통과 유지
- **기존 E2E WS 테스트**: 8개 전체 통과 유지
- **CI smoke**: 실 DB + 서버 부팅 → /health + /turn
- 테스트 커버리지 목표: 기존 수준 유지 (신규 코드 100%)
