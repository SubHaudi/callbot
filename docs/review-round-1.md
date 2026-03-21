# Phase D 기능정의서 리뷰 Round 1

## 📊 취합 요약

| # | 이슈 | 유형 | 판정 | 지적수 | 가중점수 | 심각도 |
|---|------|------|------|--------|----------|--------|
| 1 | intent_failure_total Dimension 불일치 | 수치모순 | 🔴 | 4/5 | 37.0 | MAJOR |
| 2 | MTTR KPI 누락 | 논리모순 | 🔴 | 4/5 | 28.9 | MAJOR |
| 3 | FR-011 ↔ US-004 매핑 부정확 | 전제모순 | 🔴 | 4/5 | 22.8 | MINOR |
| 4 | LLM 비용 vs 토큰 불일치 | 논리모순 | 🔴 | 3/5 | 13.5 | MINOR |
| 5 | PII/NLU/LLM 용어 정의 누락 | 용어모순 | 🟡 | 1/5 | 6.8 | MINOR |
| 6 | 아키텍처 다이어그램 PII 누락 | 논리모순 | 🟡 | 1/5 | 7.2 | MINOR |
| 7 | NFR-004 ↔ RISK-003 연결 약함 | 전제모순 | ⚪ | 1/5 | 4.8 | LOW |
| 8 | 총 기간 공수/경과일 모호 | 타임라인 | ⚪ | 1/5 | 4.2 | LOW |
| 9 | MTTD 5분 vs 5분 윈도우 알람 | 수치 | ⚪ | 1/5 | 2.8 | LOW |
| 10 | EMF fallback 마일스톤 미반영 | 일반 | ⚪ | 1/5 | 2.4 | LOW |
| 11 | Histogram CloudWatch 매핑 | 용어 | ⚪ | 1/5 | 2.8 | LOW |

## 🔴 High Confidence — 수정 완료

### 1. intent_failure_total Dimension 불일치 (MAJOR → 수정)
FR-005에서 성공/실패 모두 `intent, action_type`으로 기술되었으나 데이터 모델에서 실패는 `intent, error_type`. → FR-005를 성공/실패 분리 기술로 수정.

### 2. MTTR KPI 누락 (MAJOR → 수정)
비즈니스 임팩트에서 MTTR 30분 목표를 제시했으나 성공 지표에 누락. → 섹션 13에 MTTR KPI 추가.

### 3. FR-011 ↔ US-004 매핑 (MINOR → 수정)
turn_count는 Redis 장애와 무관한 데이터 정합성 이슈. → US-008 신설, FR-011 매핑 변경.

### 4. LLM 비용 vs 토큰 (MINOR → 수정)
"비용 추적" 약속 vs 토큰 수만 수집. → US-006/FR-007에 추정 비용 메트릭 추가, 대시보드 레이블 수정.

## 🟡 Needs Review (Phase 5에서 판단)
- PII/NLU/LLM 용어 정의 누락
- 아키텍처 다이어그램 PII 마스킹 단계 누락

## ⚪ Low Priority
- NFR-004 ↔ RISK-003 연결
- 공수/경과일 분리
- MTTD 5분 윈도우
- EMF fallback 마일스톤
- Histogram CloudWatch 매핑
