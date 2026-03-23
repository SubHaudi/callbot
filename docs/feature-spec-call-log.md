# 통화 기록 + 분석 기능정의서

## 1. 개요
- 콜봇 통화 세션 기록을 자동 저장하고, 통화 요약을 LLM으로 생성하며, 관리자 대시보드에서 조회·분석하는 기능
- 핵심 가치: 운영 데이터 확보 → 서비스 품질 측정 → 데이터 기반 개선

## 2. 배경 및 목적
- **해결하려는 문제**: 현재 통화 세션 데이터가 DB에 저장되지만, 조회·분석 인터페이스가 없어 운영 현황 파악 불가
- **As-Is**: `conversation_sessions` + `conversation_turns` 테이블 존재하지만, 조회 API 없음. 통화 요약 없음. 대시보드 없음.
- **To-Be**: 통화 종료 시 자동 요약 생성, REST API로 기록 조회, 관리자 대시보드에서 통계·검색·상세 조회
- **비즈니스 임팩트**: 서비스 품질 KPI 측정, 인텐트별 해결률 분석, 에스컬레이션 패턴 파악

## 3. 용어 정의

| 용어 | 정의 |
|------|------|
| Call Log | 하나의 통화 세션의 전체 기록 (세션 메타데이터 + 턴 이력 + 요약) |
| Turn | 사용자 발화 1회 + 봇 응답 1회의 쌍 |
| Call Summary | LLM이 생성한 통화 요약 (목적, 결과, 핵심 내용) |
| Resolution | 통화 목적의 해결 상태 (unknown: 판정 전 초기값 / resolved: 해결 / unresolved: 미해결 / escalated: 상담원 전환 / abandoned: 중도 이탈) |
| Dashboard | 관리자용 웹 UI — 통화 목록, 통계, 상세 조회 |
| KPI | 핵심 성과 지표 (해결률, 평균 턴 수, 평균 통화 시간 등) |

## 4. 사용자 스토리

- **US-001**: 관리자로서, 최근 통화 목록을 날짜/상태별로 조회하여 운영 현황을 파악하고 싶다.
- **US-002**: 관리자로서, 개별 통화의 전체 대화 내역과 요약을 확인하여 서비스 품질을 점검하고 싶다.
- **US-003**: 관리자로서, 일별/주별 통화 통계(건수, 해결률, 평균 턴 수)를 보고 추세를 파악하고 싶다.
- **US-004**: 시스템으로서, 통화 종료 시 자동으로 대화 요약을 생성하여 관리자 검색·조회를 용이하게 하고 싶다.
- **US-005**: 관리자로서, 인텐트별 통화 분포와 해결률을 확인하여 개선 우선순위를 정하고 싶다.

## 5. 기능 요구사항

| ID | 요구사항 | 우선순위 | 관련 US |
|----|---------|---------|---------|
| FR-001 | 통화 종료 시 conversation_sessions에 end_time, end_reason, resolution 자동 기록 | P0 | US-004 |
| FR-002 | 통화 종료 시 LLM으로 대화 요약(call_summary) 자동 생성, DB 저장 (최대 200자) | P0 | US-004 |
| FR-003 | GET /api/v1/admin/calls — 통화 목록 조회 API (페이지네이션, 날짜 필터, 상태 필터) | P0 | US-001 |
| FR-004 | GET /api/v1/admin/calls/{session_id} — 통화 상세 조회 API (세션 + 턴 + 요약) | P0 | US-002 |
| FR-005 | GET /api/v1/admin/stats — 통계 API (일별 통화 건수, 해결률, 평균 턴 수, 평균 통화 시간) | P1 | US-003 |
| FR-006 | GET /api/v1/admin/stats/intents — 인텐트별 통화 분포·해결률 API | P1 | US-005 |
| FR-007 | 관리자 대시보드 HTML 페이지 (/admin) — 통화 목록, 통계 차트, 상세 보기 | P0 | US-001, US-002, US-003, US-005 |
| FR-008 | 대시보드 통화 목록에서 검색 (caller_id, 요약 텍스트 검색) | P1 | US-001 |
| FR-009 | 대시보드 통계에 일별 통화 건수 차트 (최근 30일) | P1 | US-003 |
| FR-010 | resolution 자동 판정: 마지막 인텐트 성공/실패 + end_reason 기반 (end_reason='transfer' → escalated, end_reason='timeout'/'disconnect' → abandoned, 인텐트 성공 → resolved, 그 외 → unresolved) | P0 | US-004 |

## 6. 비기능 요구사항

| ID | 요구사항 | 측정 기준 |
|----|---------|-----------|
| NFR-001 | 요약 생성은 통화 종료 후 비동기로 실행, 사용자 응답 지연 없음 | 통화 종료 응답 시간에 영향 없음 |
| NFR-002 | 관리자 API 응답 시간 500ms 이내 (100건 목록 조회) | p95 < 500ms |
| NFR-003 | 대시보드는 React/Vue 등 SPA 프레임워크 없이 구현. 경량 CDN 라이브러리(Chart.js)는 허용 | 기존 데모 패턴 유지 |
| NFR-004 | 대시보드 디자인은 기존 데모와 동일한 warm editorial 스타일 유지 | 색상 팔레트, 폰트 일관 |
| NFR-005 | 기존 통화 처리 파이프라인 변경 최소화 — 세션 종료 훅만 추가. 관리자 기능은 신규 모듈로 분리 | 기존 테스트 깨지지 않음 |

## 7. 기술 설계

### 아키텍처 개요
```
[통화 종료] → [Pipeline Hook] → [비동기 요약 생성] → [DB 저장]
[관리자] → [Dashboard HTML] → [Admin REST API] → [Aurora PostgreSQL]
```

### 주요 컴포넌트
1. **CallLogger** (`server/call_logger.py`): 통화 종료 시 resolution 판정 + 요약 생성 + DB 저장
2. **Admin API Router** (`server/admin_routes.py`): 관리자 REST API 엔드포인트
3. **Admin Dashboard** (`server/static/admin.html`): 순수 HTML/CSS/JS 대시보드
4. **Summary Generator**: fake/real LLM 백엔드 — 턴 이력 → 200자 요약

### 기술 스택
- Backend: 기존 FastAPI + psycopg2 (Aurora PostgreSQL)
- Frontend: 순수 HTML/CSS/JS (기존 데모와 동일 패턴)
- 차트: Canvas API 직접 그리기 또는 경량 라이브러리 (Chart.js CDN)
- LLM: 기존 Bedrock Sonnet (fake 모드 지원)

## 8. 데이터 모델

### 기존 테이블 확장

**conversation_sessions** (기존 + 추가 컬럼):
```sql
ALTER TABLE conversation_sessions ADD COLUMN IF NOT EXISTS
    resolution TEXT DEFAULT 'unknown',    -- unknown/resolved/unresolved/escalated/abandoned
    call_summary TEXT,                     -- LLM 생성 요약 (최대 200자)
    primary_intent TEXT,                   -- 주요 인텐트
    summary_generated_at TIMESTAMPTZ;      -- 요약 생성 시각
```

### 인덱스
```sql
CREATE INDEX IF NOT EXISTS idx_sessions_start_time ON conversation_sessions(start_time DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_resolution ON conversation_sessions(resolution);
CREATE INDEX IF NOT EXISTS idx_sessions_caller_id ON conversation_sessions(caller_id);
```

## 9. API 설계

### GET /api/v1/admin/calls
- Query: `page` (default 1), `per_page` (default 20, max 100), `date_from`, `date_to`, `resolution`, `search`
- Response:
```json
{
  "calls": [
    {
      "session_id": "...",
      "caller_id": "...",
      "start_time": "...",
      "end_time": "...",
      "resolution": "resolved",
      "primary_intent": "billing_inquiry",
      "total_turn_count": 5,
      "call_summary": "고객이 요금을 조회했고 정상 확인함"
    }
  ],
  "total": 150,
  "page": 1,
  "per_page": 20
}
```

### GET /api/v1/admin/calls/{session_id}
- Response:
```json
{
  "session": { "session_id": "...", "caller_id": "...", ... },
  "turns": [
    {"turn_number": 1, "user_text": "...", "bot_text": "...", "intent": "...", "created_at": "..."}
  ],
  "call_summary": "..."
}
```

### GET /api/v1/admin/stats
- Query: `days` (default 30)
- Response:
```json
{
  "period_days": 30,
  "total_calls": 150,
  "resolution_rate": 0.78,
  "avg_turns": 4.2,
  "avg_duration_seconds": 95,
  "daily": [
    {"date": "2026-03-22", "count": 12, "resolved": 9}
  ]
}
```

### GET /api/v1/admin/stats/intents
- Response:
```json
{
  "intents": [
    {"intent": "billing_inquiry", "count": 45, "resolved": 38, "resolution_rate": 0.84}
  ]
}
```

## 10. UI/UX 고려사항

### 대시보드 화면 구성
1. **헤더**: Callbot Admin 로고 + 탭 (Overview / Call Logs)
2. **Overview 탭**: KPI 카드 (총 통화, 해결률, 평균 턴, 평균 시간) + 일별 차트 + 인텐트 분포
3. **Call Logs 탭**: 검색 바 + 필터 (날짜, 상태) + 통화 목록 테이블 + 페이지네이션
4. **상세 모달/패널**: 통화 클릭 시 턴 이력 + 요약 표시

### 디자인
- 기존 데모의 warm editorial 스타일 유지 (cream 배경, terracotta 포인트, Outfit + Noto Sans KR)
- 반응형 (데스크톱 우선, 모바일 읽기 가능)

## 11. 마일스톤 및 일정

| Phase | 내용 | 예상 기간 |
|-------|------|-----------|
| Phase 1 | DB 스키마 확장 + CallLogger + Resolution 판정 | 1일 |
| Phase 2 | Admin REST API (목록, 상세, 통계) | 1일 |
| Phase 3 | 대시보드 HTML/CSS/JS 구현 | 1~2일 |
| Phase 4 | 배포 + 검증 | 0.5일 |

총 예상: 3~4일

## 12. 리스크 및 완화 방안

| ID | 리스크 | 확률 | 영향 | 완화 |
|----|--------|------|------|------|
| RISK-001 | LLM 요약 생성 실패 시 통화 기록 누락 | L | M | 요약 실패해도 세션/턴 기록은 유지, summary는 null 허용 |
| RISK-002 | 대시보드 인증 없이 공개 노출 | M | H | MVP에서는 CloudFront 경로 제한 또는 간단한 API key 검증 |
| RISK-003 | 대량 데이터 시 통계 쿼리 느림 | L | M | 인덱스 추가, 30일 제한, 필요시 materialized view |
| RISK-004 | Chart.js CDN 의존성 | L | L | CDN 장애 시 차트만 미표시, 데이터는 API로 확인 가능 |

## 13. 성공 지표

| 지표 | 목표값 | 측정 방법 |
|------|--------|-----------|
| 통화 기록 저장율 | 100% | 통화 종료 건수 vs DB 레코드 수 |
| 요약 생성 성공율 | 95% 이상 | summary not null 비율 |
| 대시보드 로드 시간 | 2초 이내 | 브라우저 네트워크 탭 |
| API 응답 시간 (목록) | p95 < 500ms | 서버 로그 |

## 14. 의존성

| 의존성 | 리스크 |
|--------|--------|
| Aurora PostgreSQL | 낮음 — 이미 운영 중 |
| Bedrock Sonnet (요약 생성) | 낮음 — fake 모드 지원 |
| Chart.js CDN | 낮음 — 차트 미표시만 영향 |

## 15. 범위 제외 사항

- 실시간 대시보드 (WebSocket 푸시) — 향후 고려
- 통화 녹음 재생 — 향후 고려
- 다중 관리자 권한 관리 — MVP 범위 외
- 통화 기록 내보내기 (CSV/Excel) — 향후 고려
- 대시보드 인증/로그인 — MVP에서는 API key 또는 경로 제한으로 대체
