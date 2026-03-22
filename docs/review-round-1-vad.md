# VAD 기능정의서 리뷰 Round 1

## 📊 취합 요약
| # | 이슈 | 유형 | 판정 | 지적 수 | 가중점수 | 심각도 |
|---|------|------|------|---------|----------|--------|
| ISS-001 | 오탐율 테스트 "2초 이내" vs SILENCE_DURATION 1.5초 | 수치모순 | 🔴 | 5/5 | 33.6 | MAJOR |
| ISS-002 | US-002 FR 매핑 누락 — 수동종료에만 의존 | 논리모순 | 🔴 | 4/5 | 17.2 | MAJOR |
| ISS-003 | ScriptProcessor deprecated 리스크 L/L 과소평가 | 전제모순 | ⚪ | 3/5 | 10.8 | MINOR |

## 수정 반영
- ISS-001: 테스트 기준 "2초 이내" → "SILENCE_DURATION(1.5초) 미만"
- ISS-002: FR-002에 US-002 매핑 추가, MIN_SPEECH_DURATION(500ms) 상수 추가, VAD 알고리즘에 최소 음성 감지 조건 추가
- ISS-003: MINOR — 기록만 (데모 한정 수용)
