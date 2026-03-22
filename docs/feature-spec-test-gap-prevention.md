# 테스트 전략 Gap 해소 — 서버 부팅 검증 및 재발 방지 기능정의서

## 1. 개요
- Callbot 서버의 컴포넌트 조립(부팅) 경로를 검증하는 테스트 계층 신설 및 fail-fast 아키텍처 적용
- 핵심 가치: "333개 unit test가 통과해도 서버가 뜨지 않는" 사각지대 제거

## 2. 배경 및 목적

### 해결하려는 문제
- 모든 테스트가 mock 기반이라 실제 서버 부팅 시 컴포넌트 조립 실패를 감지하지 못함
- DB 없이 배포 → Pipeline 미생성 → VoiceServer에 pipeline=None 전달 → 텍스트 입력 시 "pipeline_not_configured" 에러
- `handle_text`에 `is_text_fallback` 가드로 정상 모드에서 텍스트 입력 차단

### As-Is
| 계층 | 테스트 수 | 검증 대상 |
|------|----------|----------|
| Unit | 333개 | 개별 함수/클래스 (전부 mock) |
| E2E WS | 8개 | mock pipeline + mock STT/TTS |
| Integration (조립) | **0개** | — |
| Smoke (서버 부팅) | **0개** | — |

### To-Be
| 계층 | 테스트 수 | 검증 대상 |
|------|----------|----------|
| Unit | 333+개 | 개별 함수/클래스 |
| Wiring | 7+개 | 컴포넌트 조립 (mock 최소화) |
| E2E WS | 8개 (기존 유지) | mock pipeline + mock STT/TTS |
| Smoke (CI) | 1 job | 실 DB + 서버 부팅 + /health + /turn |
| Smoke (배포 후) | 1 script | 실서버 health + turn + WS |

### 비즈니스 임팩트
- 배포 후 기본 기능이 동작하지 않는 사고 방지
- CI에서 조립 실패를 사전 감지하여 장애 예방

## 3. 용어 정의

| 용어 | 정의 |
|------|------|
| 조립(Wiring) | 서버 부팅 시 컴포넌트(DB, Pipeline, VoiceServer 등)를 연결하는 과정 |
| Fail-fast | **필수 의존성** 초기화 실패 시 서버 부팅 자체를 중단하는 패턴 |
| Smoke test | 서버가 부팅되고 핵심 경로가 동작하는지 최소한으로 확인하는 테스트 |
| Bootstrap | 서버 초기화 시 컴포넌트를 조립하는 로직을 분리한 모듈 |
| 필수 의존성 | DB(PostgreSQL), Pipeline — 이 중 하나라도 실패하면 서버 부팅 중단 |
| 선택 의존성 | STT(Transcribe), TTS(Polly) — 실패해도 텍스트 전용 모드로 서버 부팅 허용. 콜봇이지만 텍스트 테스트/디버깅을 위해 음성 없이도 동작 가능해야 함 |

## 4. 사용자 스토리

- **US-001**: As a 개발자, I want 서버 부팅 실패가 CI에서 즉시 감지되길, So that 배포 전에 조립 문제를 발견할 수 있다.
- **US-002**: As a 개발자, I want 필수 의존성 없이 서버가 뜨지 않길, So that "서버는 떠 있지만 기능이 안 되는" 상태를 방지할 수 있다.
- **US-003**: As a 운영자, I want 배포 직후 smoke test가 자동 실행되길, So that 배포 문제를 즉시 감지하고 롤백할 수 있다.
- **US-004**: As a 개발자, I want `_lifespan` 조립 로직이 테스트 가능한 구조이길, So that 조립 경로를 단위 테스트할 수 있다.

## 5. 기능 요구사항

### FR-001: `_lifespan` fail-fast (P0)
- `server/app.py`의 `_lifespan`에서 **필수 의존성**(DB, Pipeline) 초기화 실패 시 예외를 삼키지 않고 `raise`하여 서버 부팅을 중단한다.
- **선택 의존성**(STT, TTS)은 실패 시 None → 텍스트 전용 모드 허용 (콜봇 디버깅/테스트 목적)
- 기존 `except Exception: logger.exception(...)` → 필수 의존성 실패 시 `raise`
- 관련: US-002

### FR-002: bootstrap.py 분리 (P0)
- `_lifespan`의 조립 로직을 `server/bootstrap.py`로 분리한다.
- `assemble_pipeline(pg_connection, redis_store, bedrock_service) → TurnPipeline`: DB connection이 None이면 `RuntimeError` 발생
- `assemble_voice_server(pipeline, stt_engine, tts_engine) → VoiceServer`: 팩토리 함수
- `init_stt_engine() → Optional[STTEngine]`: 실패 시 None (텍스트 전용 모드는 허용)
- `init_tts_engine() → Optional[TTSEngine]`: 실패 시 None
- `_lifespan`은 bootstrap 함수를 호출하는 얇은 레이어로 변경
- 관련: US-004

### FR-003: routes.py pipeline None 방어 (P0)
- `server/routes.py`의 `turn_endpoint`에서 `app.state.pipeline`이 None이면 503 반환
- `getattr(request.app.state, "pipeline", None)` 패턴 사용
- 관련: US-002

### FR-004: handle_text fallback 가드 제거 (P0)
- `voice_io/voice_server.py`의 `handle_text`에서 `is_text_fallback` 체크를 제거하여 텍스트 입력을 항상 허용
- 원래 가드는 "음성 모드에서 텍스트 차단" 의도였으나, 실제로는 텍스트 테스트/디버깅을 불가능하게 만드는 버그. Pipeline 유무로만 제어해야 함
- WS 경로(`handle_text`)에서도 pipeline None 시 에러 응답 반환하는 방어 코드 추가
- 관련: US-002

### FR-005: Wiring test 신설 (P0)
- `server/tests/test_wiring.py` — mock 최소화 조립 검증
- `assemble_pipeline`: DB None → RuntimeError 테스트
- `assemble_pipeline`: mock DB로 조립 성공 + 내부 컴포넌트 실제 객체 확인
- `assemble_pipeline`: process가 async 함수인지 확인
- `assemble_voice_server`: STT/TTS 없이 생성 가능
- `assemble_voice_server`: 전체 엔진으로 생성 + 속성 확인
- `assemble_voice_server`: 세션 생성 가능
- `turn_endpoint`: pipeline None → 503 반환
- 관련: US-001, US-004

### FR-006: CI smoke job 신설 (P1)
- `.github/workflows/ci.yml`에 `smoke` job 추가
- GitHub Actions services: PostgreSQL 16, Redis 7
- 서버 부팅 → `/health` 200 확인 → `/api/v1/turn` 정상 응답 확인
- `test` job 성공 후 실행 (`needs: test`)
- 관련: US-001

### FR-007: 배포 후 smoke script (P1)
- `tests/smoke_test.sh` — 배포 직후 실행하는 스크립트
- Health check (HTTP 200)
- Turn API (POST → response_text 존재)
- WebSocket 연결 (WS connect → 메시지 송수신)
- 실패 시 exit 1 (CI/CD 연동용)
- 관련: US-003

### FR-008: PR 체크리스트 템플릿 (P2)
- `.github/PULL_REQUEST_TEMPLATE.md` 신설
- 서버 부팅 경로 변경 시 wiring test 갱신 여부
- 새 의존성 추가 시 CI services 반영 여부
- mock 전용 테스트에 대응하는 조립 테스트 존재 여부
- app.state 속성 추가 시 방어 코드 여부
- 관련: US-001

## 6. 비기능 요구사항

### NFR-001: CI 실행 시간
- smoke job 추가로 인한 CI 전체 실행 시간 증가: 최대 2분 이내 (PG/Redis 컨테이너 시작 ~30초 + 서버 부팅 ~5초 + smoke 요청 ~5초 + 여유 ~80초)
- test job과 smoke job은 순차 실행 (needs: test)

### NFR-002: 테스트 격리
- wiring test는 외부 서비스(AWS Transcribe/Polly) 의존성 없이 실행 가능해야 함
- DB는 mock 또는 testcontainers로 대체

### NFR-003: 하위 호환성
- 기존 333개 unit test + 8개 E2E WS test가 모두 통과해야 함
- 기존 테스트 코드 변경 최소화 (handle_text 테스트만 업데이트)

### NFR-004: Python 3.9 호환
- 모든 신규 코드는 Python 3.9에서 동작해야 함 (`Dict`, `List`, `Optional` from typing)

### NFR-005: 문서화
- bootstrap.py의 각 함수에 docstring 포함
- smoke_test.sh에 사용법 주석 포함

## 7. 기술 설계

### 아키텍처 변경

```
AS-IS:
  _lifespan (130줄 모놀리스)
    ├── DB 초기화
    ├── Redis 초기화
    ├── Bedrock 초기화
    ├── Pipeline 조립 (inline)
    ├── STT/TTS 초기화 (inline)
    ├── VoiceServer 조립 (inline)
    └── except: 삼킴 → graceful degradation

TO-BE:
  _lifespan (얇은 레이어)
    ├── DB/Redis/Bedrock 초기화
    ├── bootstrap.assemble_pipeline() ← 테스트 가능
    ├── bootstrap.init_stt/tts_engine() ← 테스트 가능
    ├── bootstrap.assemble_voice_server() ← 테스트 가능
    └── except: raise → fail-fast
```

### 주요 컴포넌트

| 컴포넌트 | 역할 | 파일 |
|----------|------|------|
| bootstrap.py | 조립 함수 모음 | `server/bootstrap.py` (신규) |
| test_wiring.py | 조립 검증 테스트 | `server/tests/test_wiring.py` (신규) |
| ci.yml smoke job | CI 서버 부팅 검증 | `.github/workflows/ci.yml` (수정) |
| smoke_test.sh | 배포 후 검증 | `tests/smoke_test.sh` (신규) |
| PR template | 리뷰 체크리스트 | `.github/PULL_REQUEST_TEMPLATE.md` (신규) |

### 기술 스택
- Python 3.9, FastAPI, pytest, uvicorn
- GitHub Actions (services: postgres:16, redis:7)
- websockets (smoke script WS 테스트)

## 8. 데이터 모델
- 데이터 모델 변경 없음. 기존 스키마 유지.

## 9. API 설계
- API 변경 없음. 기존 `/api/v1/turn`, `/health`, `/api/v1/ws/voice` 유지.
- 변경: `turn_endpoint`에서 pipeline None 시 503 응답 추가 (기존 AttributeError 대신)

## 10. UI/UX 고려사항
- UI 변경 없음. Demo HTML에서 ws:// → wss:// 자동 감지는 이전 커밋에서 이미 수정됨.

## 11. 마일스톤 및 일정

| Phase | 산출물 | 예상 소요 |
|-------|--------|----------|
| P0 코드 변경 | fail-fast, bootstrap, routes 방어, handle_text 수정 | 30분 |
| P0 테스트 | test_wiring.py (7개) | 30분 |
| P1 CI | ci.yml smoke job | 15분 |
| P1 Script | smoke_test.sh | 15분 |
| P2 Process | PR template | 10분 |

총 예상: ~1시간 40분

## 12. 리스크 및 완화 방안

### RISK-001: fail-fast로 인한 서버 부팅 실패
- 발생 확률: M | 영향도: H
- 완화: DB 연결 실패 시 명확한 에러 메시지 출력, systemd restart 설정으로 자동 재시도

### RISK-002: CI smoke job 타임아웃
- 발생 확률: L | 영향도: M
- 완화: PG/Redis health check 설정, 서버 부팅 대기 sleep 5초, job timeout 60초

### RISK-003: handle_text fallback 가드 제거 시 의도치 않은 동작
- 발생 확률: L | 영향도: M
- 완화: 기존 Phase G 테스트 업데이트, text 입력은 Pipeline 유무에만 의존

## 13. 성공 지표

| KPI | 목표 | 측정 방법 |
|-----|------|----------|
| 조립 실패 CI 감지율 | 100% | wiring test에서 DB None → RuntimeError |
| 서버 부팅 CI 감지율 | 100% | smoke job에서 서버 부팅 + /turn 응답 |
| 기존 테스트 통과율 | 100% | 기존 333+ 테스트 전체 통과 |
| CI 추가 시간 | < 2분 | smoke job 실행 시간 측정 |

## 14. 의존성

| 의존성 | 리스크 |
|--------|--------|
| PostgreSQL 16 (CI services) | Low — GitHub Actions 표준 지원 |
| Redis 7 (CI services) | Low — GitHub Actions 표준 지원 |
| websockets (smoke script) | Low — 이미 프로젝트 의존성 |

## 15. 범위 제외 사항

- **testcontainers 도입**: wiring test는 mock DB로 충분. testcontainers는 향후 고려.
- **CD 자동 롤백**: smoke_test.sh 실패 시 자동 롤백은 이번 범위 외.
- **실서버 E2E WS 테스트 (Playwright)**: B층 테스트는 별도 Phase로.
- **DB 없이 동작하는 데모 모드**: 이번 범위는 fail-fast. 데모 모드는 향후 별도 feature로.
