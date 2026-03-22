## Checklist

- [ ] Unit tests pass (`pytest`)
- [ ] **서버 부팅 경로 (`server/app.py` `_lifespan`)** 변경 시: wiring test 갱신했는가?
- [ ] **새 의존성** (DB, Redis, 외부 API) 추가 시: CI `services`에 반영했는가?
- [ ] mock만 쓰는 테스트 추가 시: 실제 조립 경로도 커버하는 테스트가 있는가?
- [ ] `app.state`에 새 속성 추가 시: 해당 속성 없을 때의 방어 코드 (503) 있는가?
- [ ] 배포 후 `tests/smoke_test.sh` 로컬 실행 통과

## Mock 원칙

- 외부 서비스 (AWS, 외부 API): mock OK
- 내부 컴포넌트 조립 (Pipeline, SessionManager 등): **최소 1개 테스트는 실제 객체로**
- `server/bootstrap.py`의 조립 함수: **mock 금지 대상** — `server/tests/test_wiring.py`에서 검증
