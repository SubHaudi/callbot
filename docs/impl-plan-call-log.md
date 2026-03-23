# 통화 기록 + 분석 구현 계획

## 구현 원칙
- TDD 사이클: Red → Green → Refactor
- Tidy First: 구조적 변경과 행위적 변경을 분리
- 각 커밋은 구조적 또는 행위적 중 하나만 포함

## 요구사항 추적 매트릭스
| 요구사항 ID | 요구사항 요약 | 관련 태스크 |
|-------------|-------------|-------------|
| FR-001 | 통화 종료 시 end_time, end_reason, resolution 자동 기록 | TASK-003, TASK-004, TASK-013 |
| FR-002 | LLM 대화 요약 자동 생성 (최대 200자) | TASK-005, TASK-006, TASK-013 |
| FR-003 | GET /api/v1/admin/calls — 통화 목록 조회 API | TASK-008, TASK-009 |
| FR-004 | GET /api/v1/admin/calls/{session_id} — 통화 상세 조회 API | TASK-008, TASK-009 |
| FR-005 | GET /api/v1/admin/stats — 통계 API | TASK-010, TASK-011 |
| FR-006 | GET /api/v1/admin/stats/intents — 인텐트별 분포 API | TASK-010, TASK-011 |
| FR-007 | 관리자 대시보드 HTML (/admin) | TASK-012 |
| FR-008 | 대시보드 검색 (caller_id, 요약 텍스트) | TASK-008, TASK-009, TASK-012 |
| FR-009 | 대시보드 일별 통화 차트 (최근 30일) | TASK-012 |
| FR-010 | resolution 자동 판정 (end_reason 기반) | TASK-003, TASK-004 |
| NFR-001 | 요약 생성 비동기, 사용자 응답 지연 없음 | TASK-005, TASK-013 |
| NFR-002 | Admin API p95 < 500ms | TASK-009, TASK-011 |
| NFR-003 | SPA 프레임워크 없이, Chart.js CDN 허용 | TASK-012 |
| NFR-004 | 기존 데모와 동일 스타일 | TASK-012 |
| NFR-005 | 기존 파이프라인 변경 최소화 | TASK-002, TASK-007 |

## 태스크 목록

### TASK-001: DB 스키마 확장 (Structural)
- **변경 유형**: Structural
- **설명**: conversation_sessions 테이블에 resolution, call_summary, primary_intent, summary_generated_at 컬럼 추가. 인덱스 3개 추가. `_ensure_schema()` 함수에 ALTER TABLE + CREATE INDEX 추가.
- **완료 기준**: 스키마 확장 SQL이 `_ensure_schema()`에 포함, 기존 테스트 통과
- **커밋 메시지**: `structural: extend conversation_sessions schema — resolution, call_summary, primary_intent columns + indexes`

### TASK-002: CallLogger 인터페이스 정의 (Structural)
- **변경 유형**: Structural
- **의존성**: TASK-001
- **설명**: `server/call_logger.py` 파일 생성. `CallLogger` 클래스 스켈레톤 — `__init__(pg_conn, llm_engine)`, `finalize_session(session_id, turns, end_reason)` 메서드 시그니처만 정의 (pass body).
- **완료 기준**: 파일 생성, import 가능, 기존 테스트 통과
- **커밋 메시지**: `structural: add CallLogger skeleton with finalize_session interface`

### TASK-003: resolution 자동 판정 로직 — 테스트 (Behavioral/Red)
- **변경 유형**: Behavioral
- **의존성**: TASK-002
- **설명**: `server/tests/test_call_logger.py` 생성. resolution 판정 테스트:
  - end_reason='transfer' → 'escalated'
  - end_reason='timeout' → 'abandoned'
  - end_reason='disconnect' → 'abandoned'
  - end_reason이 정상 종료(normal/completed)이고 마지막 턴의 action_type이 PROCESS_BUSINESS → 'resolved'
  - 그 외 → 'unresolved'
  - primary_intent: 마지막 비-null 인텐트 추출 → DB 저장
- **테스트**: 6개 테스트 케이스 (위 5개 + primary_intent 추출), 모두 실패 (Red)
- **관련 요구사항**: FR-001, FR-010
- **완료 기준**: 5개 테스트 작성, 모두 FAIL
- **커밋 메시지**: `behavioral(red): add resolution judgment tests`

### TASK-004: resolution 자동 판정 로직 — 구현 (Behavioral/Green)
- **변경 유형**: Behavioral
- **의존성**: TASK-003
- **설명**: `CallLogger._determine_resolution(end_reason, turns)` 구현 + `finalize_session`에서 resolution 판정 + primary_intent 추출 (마지막 비-null 인텐트) + DB UPDATE (resolution, primary_intent, end_time)
- **관련 요구사항**: FR-001, FR-010
- **완료 기준**: TASK-003 테스트 6개 모두 PASS
- **커밋 메시지**: `behavioral(green): implement resolution judgment logic`

### TASK-005: 대화 요약 생성 — 테스트 (Behavioral/Red)
- **변경 유형**: Behavioral
- **의존성**: TASK-004
- **설명**: `test_call_logger.py`에 요약 생성 테스트 추가:
  - fake LLM으로 요약 생성 → call_summary가 200자 이내
  - 요약 생성 실패 시 → call_summary=None, 세션 기록은 유지
  - summary_generated_at 타임스탬프 설정
- **테스트**: 3개 테스트, 모두 실패 (Red)
- **관련 요구사항**: FR-002, NFR-001
- **완료 기준**: 3개 테스트 FAIL
- **커밋 메시지**: `behavioral(red): add call summary generation tests`

### TASK-006: 대화 요약 생성 — 구현 (Behavioral/Green)
- **변경 유형**: Behavioral
- **의존성**: TASK-005
- **설명**: `CallLogger._generate_summary(turns)` 구현. LLM에 턴 이력 전달 → 200자 요약 반환. 200자 초과 시 truncate. 실패 시 None 반환 (예외 삼키기). DB UPDATE로 call_summary, summary_generated_at 저장.
- **관련 요구사항**: FR-002
- **완료 기준**: TASK-005 테스트 3개 모두 PASS
- **커밋 메시지**: `behavioral(green): implement call summary generation with LLM`

### TASK-007: Admin API Router 스켈레톤 (Structural)
- **변경 유형**: Structural
- **의존성**: TASK-001
- **설명**: `server/admin_routes.py` 생성. FastAPI APIRouter 정의 (`prefix="/api/v1/admin"`). `server/app.py`의 `create_app`에 admin_router include. Static files 서빙 설정 (/admin → admin.html).
- **완료 기준**: 라우터 등록 완료, /admin 경로 접근 가능 (빈 페이지), 기존 테스트 통과
- **커밋 메시지**: `structural: add admin API router skeleton + static file serving`

### TASK-008: 통화 목록/상세 API — 테스트 (Behavioral/Red)
- **변경 유형**: Behavioral
- **의존성**: TASK-007
- **설명**: `server/tests/test_admin_routes.py` 생성. TestClient 사용:
  - GET /api/v1/admin/calls → 200, calls 배열 + total + pagination
  - GET /api/v1/admin/calls?resolution=resolved → 필터 동작
  - GET /api/v1/admin/calls?search=010 → caller_id 검색 동작
  - GET /api/v1/admin/calls?search=요금 → 요약 텍스트 검색 동작
  - GET /api/v1/admin/calls/{session_id} → 200, session + turns + call_summary
  - GET /api/v1/admin/calls/{invalid_id} → 404
- **테스트**: 6개 테스트, 모두 실패 (Red)
- **관련 요구사항**: FR-003, FR-004
- **완료 기준**: 4개 테스트 FAIL
- **커밋 메시지**: `behavioral(red): add admin calls list/detail API tests`

### TASK-009: 통화 목록/상세 API — 구현 (Behavioral/Green)
- **변경 유형**: Behavioral
- **의존성**: TASK-008
- **설명**: `admin_routes.py`에 `list_calls()` + `get_call_detail()` 엔드포인트 구현. psycopg2로 DB 조회. 페이지네이션 (page, per_page), 필터 (date_from, date_to, resolution, search).
- **관련 요구사항**: FR-003, FR-004, FR-008
- **완료 기준**: TASK-008 테스트 6개 모두 PASS
- **커밋 메시지**: `behavioral(green): implement admin calls list/detail API with pagination and filters`

### TASK-010: 통계 API — 테스트 (Behavioral/Red)
- **변경 유형**: Behavioral
- **의존성**: TASK-009
- **설명**: `test_admin_routes.py`에 통계 테스트 추가:
  - GET /api/v1/admin/stats → 200, total_calls, resolution_rate, avg_turns, avg_duration_seconds, daily 배열
  - GET /api/v1/admin/stats/intents → 200, intents 배열 (intent, count, resolved, resolution_rate)
- **테스트**: 2개 테스트, 모두 실패 (Red)
- **관련 요구사항**: FR-005, FR-006
- **완료 기준**: 2개 테스트 FAIL
- **커밋 메시지**: `behavioral(red): add admin stats/intents API tests`

### TASK-011: 통계 API — 구현 (Behavioral/Green)
- **변경 유형**: Behavioral
- **의존성**: TASK-010
- **설명**: `admin_routes.py`에 `get_stats()` + `get_intent_stats()` 구현. SQL 집계 쿼리 (COUNT, AVG, GROUP BY). 기간 필터 (days 파라미터, 기본 30일).
- **관련 요구사항**: FR-005, FR-006
- **완료 기준**: TASK-010 테스트 2개 모두 PASS
- **커밋 메시지**: `behavioral(green): implement admin stats/intents API with SQL aggregation`

### TASK-012: 관리자 대시보드 HTML (Behavioral)
- **변경 유형**: Behavioral
- **의존성**: TASK-011
- **설명**: `server/static/admin.html` 생성. 단일 HTML 파일:
  - 기존 데모와 동일 warm editorial 스타일 (cream 배경, terracotta 포인트, Outfit + Noto Sans KR)
  - Overview 탭: KPI 카드 4개 + Chart.js 일별 차트 + 인텐트 분포 차트
  - Call Logs 탭: 검색 바 + 필터 + 테이블 + 페이지네이션
  - 상세 모달: 턴 이력 + 요약
  - fetch()로 Admin API 호출
- **관련 요구사항**: FR-007, FR-008, FR-009, NFR-003, NFR-004
- **완료 기준**: /admin 접근 시 대시보드 표시, API 연동 동작
- **커밋 메시지**: `behavioral: add admin dashboard — overview stats, call logs, detail modal`

### TASK-013: Pipeline 훅 연결 (Behavioral)
- **변경 유형**: Behavioral
- **의존성**: TASK-006
- **설명**: 기존 통화 종료 흐름에 CallLogger.finalize_session() 호출 추가. voice_ws.py 또는 pipeline.py의 세션 종료 지점에서 `asyncio.to_thread()`로 동기 CallLogger를 별도 스레드에서 실행 (이벤트 루프 블로킹 방지).
- **관련 요구사항**: FR-001, FR-002, NFR-001
- **완료 기준**: 통화 종료 시 resolution + summary 자동 기록, 기존 테스트 통과
- **커밋 메시지**: `behavioral: hook CallLogger into session finalization — async summary generation`

### TASK-014: 전체 통합 테스트 (Behavioral)
- **변경 유형**: Behavioral
- **의존성**: TASK-013
- **설명**: E2E 테스트 — 통화 시작 → 턴 처리 → 세션 종료 → CallLogger 실행 → Admin API로 조회 확인
- **관련 요구사항**: 전체
- **완료 기준**: 통합 테스트 PASS, 전체 테스트 스위트 PASS
- **커밋 메시지**: `behavioral: add call log E2E integration test`

### TASK-015: 서버 무변경 검증 (Verification)
- **변경 유형**: Verification
- **의존성**: TASK-014
- **설명**: git diff로 기존 핵심 파일(pipeline.py, voice_ws.py 등) 변경이 최소임을 확인. 신규 파일이 별도 모듈로 분리되었는지 확인.
- **관련 요구사항**: NFR-005
- **완료 기준**: 기존 핵심 파일 변경이 훅 추가만
- **커밋 메시지**: N/A (검증만)

## 태스크 의존성 그래프
```
TASK-001 (스키마 확장)
  ├→ TASK-002 (CallLogger 스켈레톤)
  │    ├→ TASK-003 (resolution 테스트/Red)
  │    │    └→ TASK-004 (resolution+primary_intent 구현/Green)
  │    │         └→ TASK-005 (요약 테스트/Red)
  │    │              └→ TASK-006 (요약 구현/Green)
  │    │                   └→ TASK-013 (Pipeline 훅 — asyncio.to_thread)
  └→ TASK-007 (Admin Router 스켈레톤)
       ├→ TASK-008 (목록/상세 테스트/Red)
       │    └→ TASK-009 (목록/상세 구현/Green)
       │         └→ TASK-010 (통계 테스트/Red)
       │              └→ TASK-011 (통계 구현/Green)
       │                   └→ TASK-012 (대시보드 HTML)
  TASK-012 + TASK-013 → TASK-014 (통합 테스트) → TASK-015 (검증)
```

## 테스트 전략
- **단위 테스트**: CallLogger (resolution 판정, 요약 생성), Admin API (목록/상세/통계)
- **통합 테스트**: 통화→종료→기록→API 조회 E2E
- **수동 테스트**: 대시보드 UI, 차트, 검색, 모달
- **테스트 커버리지**: 신규 코드 80% 이상
