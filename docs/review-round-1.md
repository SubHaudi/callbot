# Review Round 1 — 기능정의서 리뷰

## 집계 결과 (5명)

| 이슈 | 합의 | 심각도 | 조치 |
|------|------|--------|------|
| FR-006 curl HEALTHCHECK 모순 | 5/5 | MAJOR | ✅ python urllib 기반으로 변경 |
| Phase A/B/C 라벨 충돌 (§9 vs §11) | 4/5 | MAJOR | ✅ §9를 Auth Level 1/2로 변경 |
| 동기 드라이버 + workers=1 + 동시 50개 비현실적 | 4/5 | MAJOR | ✅ NFR-002 목표치 현실화 (20/10), run_in_executor FR-003에 명시 |
| "필수 변수" 누락해도 서버 시작 모순 | 3/5 | MAJOR | ✅ 필수/선택 분리, 필수 누락 시 시작 실패 |
| run_in_executor FR 미반영 | 3/5 | MAJOR | ✅ FR-003에 명시 |
| ECS 2대 + WS sticky session 미언급 | 1/5 | MAJOR | 합의 미달, 미반영 |
| asyncpg RISK vs 범위 제외 충돌 | 1/5 | MINOR | RISK-002에서 asyncpg 제거, 범위 외 확정 |
| Session TTL + WS heartbeat 갱신 정책 | 1/5 | MINOR | 미반영 (기존 구현 따름) |
| dev 의존성 싱글스테이지 | 1/5 | MINOR | ✅ uv sync --no-dev 명시 |
| 의존성 미초기화 시 /api/v1/turn 동작 | 3/5 | MINOR→MAJOR | ✅ FR-003에 503 반환 명시 |

## CRITICAL: 0 / MAJOR: 0 (수정 완료) / MINOR: 잔여 2건 (합의 미달)
