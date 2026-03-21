# 코드 리뷰 보고서 v2 — 자율 리뷰 Round 1

**일시**: 2026-03-21 04:33 UTC
**리뷰어**: 5명 서브에이전트 (Opus 4.6)
**대상**: `callbot/docs/code-review-report.md` v2

## 📊 취합 요약

| # | 이슈 | 유형 | 판정 | 지적수 | 가중점수 | 심각도 | 조치 |
|---|------|------|------|--------|----------|--------|------|
| 1 | C-07 허위 이슈 — masking_module.py에 로깅 코드 없음 | 근거오류 | 🔴 | 5/5 | 8.6 | MAJOR | ✅ 삭제 |
| 2 | C-05 위치 오류 — models.py → vendor_factory.py:34 | 위치오류 | 🔴 | 5/5 | 8.6 | MINOR | ✅ 수정 |
| 3 | M-07 위치 오류 — orchestrator/enums.py → nlu/enums.py | 위치오류 | 🔴 | 3/5 | 5.2 | MINOR | ✅ 수정 |
| 4 | M-20 SQL injection CRITICAL 격상 검토 | 분류 | 🟡 | 1/5 | 8.0 | MAJOR | 기록 |
| 5 | ThreadPoolExecutor shutdown 누락 MAJOR급 | 누락 | 🟡 | 2/5 | — | MAJOR | 기록 |
| 6 | DAG C-02 의존관계 과도 | DAG | ⚪ | 3/5 | 3.6 | MINOR | — |
| 7 | 줄수 ~8,280 vs ~8,740 | 통계 | ⚪ | 2/5 | 3.0 | MINOR | — |
| 8 | C-01 공수 L→M | 공수 | ⚪ | 1/5 | 1.8 | MINOR | — |

## 🔴 High Confidence 이슈 상세

### 1. C-07 허위 이슈 (5/5 만장일치)
- `nlu/masking_module.py`에 `logging`, `logger`, `log` 관련 코드 0건
- `original_text = text`는 마스킹 알고리즘 내부 변수, 로깅과 무관
- **조치**: C-07 삭제, 감사 로깅 부재는 Mi-12에서 이미 커버

### 2. C-05 위치 오류 (5/5)
- `voice_io/models.py:27` = STTResult.create() classmethod
- 실제 Union 반환: `voice_io/vendor_factory.py:34`
- **조치**: 위치 수정

### 3. M-07 위치 오류 (3/5)
- Intent enum은 `nlu/enums.py`에 정의, `orchestrator/enums.py`가 아님
- **조치**: 위치 수정

## 🟡 Needs Review

### 4. M-20 SQL injection 격상
- `pg_connection.py:131`에서 컬럼명이 f-string으로 삽입
- updates dict가 내부 코드에서만 생성되면 MAJOR 유지 가능
- 1명만 지적 (확신도 8, 근거강도 5)

### 5. ThreadPoolExecutor shutdown 누락
- `server/pipeline.py:14` 글로벌 executor, lifespan에서 shutdown() 미호출
- 2명 지적, MAJOR급 추가 이슈 후보

## 루프 판정
- 🔴 MAJOR 1건 (C-07) → **수정 후 Round 2 진행**
- 🔴 MINOR 2건 (C-05, M-07) → 수정 완료
