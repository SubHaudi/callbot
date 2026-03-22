# 코드리뷰 Round 1

## 결과: CRITICAL 0, MAJOR 2 → 수정 완료

### MAJOR 수정

| 이슈 | 지지 | 수정 |
|------|------|------|
| CI Bedrock fake 모드 미동작 | 4/5 | `CALLBOT_LLM_BACKEND=fake` env + `_init_bedrock` fake 분기 |
| `healthy=True`가 pipeline 조립 전 | 3/5 | 모든 조립 완료 후로 이동 |

### 기존 코드 버그 (별도 이슈)
- `asyncio.to_thread` + async `process` (4/5) — Phase G 코드
- `handle_text` caller_id 누락 (1/5) — Phase G 코드

### MINOR (미수정, 기록)
- response_model 불일치 (4/5)
- smoke WS soft-pass (3/5)
- 타입 Any (3/5)
- PR template 이미 구현됨 (에이전트가 파일 못 읽은 것)
