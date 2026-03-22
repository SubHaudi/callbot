# Phase G: Full Voice Pipeline 기능정의서

## 1. 개요
- WebSocket 음성 파이프라인 풀 E2E 통합: 브라우저 마이크 → WebSocket → STT → NLU → LLM → TTS → 음성 응답
- 핵심 가치: 지금까지 Phase A~F에서 만든 10개 모듈을 하나의 동작하는 음성 대화 데모로 통합

## 2. 배경 및 목적
- **문제**: 개별 모듈(STT, TTS, NLU, Pipeline, VoiceServer)이 각각 unit-tested이지만, 실제 음성→응답 음성 전체 경로가 E2E로 연결된 적 없음
- **As-Is**: VoiceServer가 131줄 스켈레톤. FastAPI 앱(`server/app.py`)에 WebSocket 엔드포인트 없음. demo HTML은 존재하나 실제 서버 미연결
- **To-Be**: `ws://host:port/api/v1/ws/voice`로 접속 → 음성 입력 → AI 음성 응답, 브라우저 데모 동작
- **임팩트**: 데모 가능한 프로토타입 완성, 이해관계자 시연 가능

## 3. 용어 정의

| 용어 | 정의 |
|------|------|
| VoiceSession | 단일 WebSocket 연결에 대응하는 음성 세션 객체 |
| STT handle | TranscribeSTTEngine의 스트리밍 세션 핸들 (StreamHandle) |
| TurnPipeline | NLU→Orchestrator→LLM 텍스트 처리 파이프라인 |
| Barge-in | 사용자가 TTS 재생 중 발화하여 재생을 중단하는 동작 |
| 텍스트 폴백 | STT 실패 시 텍스트 입력 모드로 전환 (FR-005) |
| PCM 16kHz | 16000Hz 샘플레이트, 16bit, mono PCM 오디오 포맷 |

## 4. 사용자 스토리

- **US-001**: 사용자로서, 브라우저에서 마이크 버튼을 누르고 말하면 AI가 음성으로 응답받고 싶다
- **US-002**: 사용자로서, AI가 말하는 도중에 끼어들면(barge-in) AI가 멈추고 내 말을 들어주길 원한다
- **US-003**: 사용자로서, 음성 인식이 실패하면 텍스트로 입력할 수 있길 원한다
- **US-004**: 개발자로서, WebSocket JSON 프로토콜이 명확하여 클라이언트 구현이 쉽길 원한다

## 5. 기능 요구사항

### FR-001: FastAPI WebSocket 엔드포인트 (P0)
- 경로: `GET /api/v1/ws/voice` → WebSocket upgrade
- 연결 시 VoiceSession 자동 생성, 종료 시 자동 정리
- 관련: US-001, US-004

### FR-002: WebSocket 프로토콜 정의 (P0)
- **클라이언트 → 서버**:
  - `{"type": "audio", "data": "<base64 PCM>"}` — 오디오 청크
  - `{"type": "text", "text": "..."}` — 텍스트 폴백 입력
  - `{"type": "interrupt"}` — Barge-in 요청
  - `{"type": "end"}` — 발화 종료 (최종 결과 요청)
- **서버 → 클라이언트**:
  - `{"type": "transcript", "text": "...", "is_final": true}` — final STT 결과 (Phase 1은 버퍼 누적→일괄 처리이므로 항상 is_final=true. partial transcript는 Phase 2 실시간 스트리밍에서 지원 예정)
  - `{"type": "response", "text": "...", "audio": "<base64 PCM>"}` — AI 응답 + TTS 오디오
  - `{"type": "interrupted"}` — Barge-in ACK (클라이언트는 TTS 재생 중단)
  - `{"type": "error", "message": "..."}` — 에러
  - `{"type": "fallback", "message": "..."}` — 텍스트 폴백 전환 알림
- 관련: US-004

### FR-003: STT→Pipeline→TTS 풀 파이프라인 (P0)
- VoiceServer.handle_audio()에서 실제 TranscribeSTTEngine → TurnPipeline → PollyTTSEngine 연결
- STT final result → pipeline.process() → TTS synthesize() → audio 응답
- 관련: US-001

### FR-004: Barge-in 통합 (P1)
- 클라이언트가 `{"type": "interrupt"}` 전송 시 TTS 재생 중단
- 서버: PollyTTSEngine.stop_playback() 호출 + VoiceSession.is_tts_playing = False
- 서버 → 클라이언트: `{"type": "interrupted"}` ACK 전송 → 클라이언트가 Web Audio 재생 중단
- 기존 STT 핸들이 있으면 stop_stream() 후 새 STT 스트림 시작하여 사용자 발화 수신
- 관련: US-002

### FR-005: 텍스트 폴백 모드 (P1)
- STTFallbackError 발생 시 세션을 텍스트 폴백으로 전환
- 이후 `{"type": "text"}` 메시지로 텍스트 입력 처리
- Pipeline → TTS 경로는 동일하게 동작
- 관련: US-003

### FR-006: Demo HTML 클라이언트 업데이트 (P1)
- 기존 `voice_io/demo/index.html` 수정
- WebSocket 프로토콜(FR-002)에 맞게 연결
- MediaRecorder로 마이크 녹음 → PCM 변환 → base64 → WebSocket 전송
- 서버 응답 audio를 AudioContext로 재생
- 관련: US-001

### FR-007: 세션 관리 (P0)
- WebSocket disconnect 시 VoiceSession + STT handle 자동 정리
- 동시 세션 제한: 최대 10개 (설정 가능)
- 세션 타임아웃: 5분 무활동 시 자동 종료
- 관련: US-001

### FR-008: 레이턴시 계측 (P2)
- 각 턴의 STT/Pipeline/TTS 단계별 소요시간 로깅
- 응답에 `processing_ms` 포함
- RTT P95 ≤ 8초 검증 가능
- 관련: US-001

## 6. 비기능 요구사항

### NFR-001: RTT (P0)
- 전체 음성→응답 RTT P95 ≤ 8초 (STT ≤1.5s + Pipeline ≤5s + TTS ≤1.5s)
- 측정: FR-008 레이턴시 로그로 검증

### NFR-002: 동시성 (P1)
- 동시 10세션 지원 (asyncio 기반)
- 세션 간 상태 격리

### NFR-003: 보안 (P0)
- 음성 데이터 디스크 저장 안 함 (Phase F NFR-004 규칙 유지)
- WebSocket 인증은 데모 범위에서 미구현 (향후 추가)

### NFR-004: Python 3.9 호환 (P0)
- `from __future__ import annotations`, `typing.Dict/Optional` 사용

### NFR-005: 테스트 커버리지 (P0)
- 신규 코드 80% 이상
- E2E 통합 테스트: mock + 실제 AWS 두 트랙

## 7. 기술 설계

### 아키텍처 개요
```
Browser (demo/index.html)
  ↕ WebSocket (JSON + base64 audio)
FastAPI WebSocket endpoint (/api/v1/ws/voice)
  ↕
VoiceServer
  ├→ TranscribeSTTEngine (AWS Transcribe Streaming)
  ├→ TurnPipeline (NLU → Orchestrator → LLM)
  ├→ PollyTTSEngine (Amazon Polly)
  └→ AudioConverter (PCM ↔ opus, 필요시)
```

### 주요 컴포넌트
- **voice_ws.py** (신규): FastAPI WebSocket 라우터
- **voice_server.py** (수정): handle_audio → 실제 엔진 연결, handle_text (폴백)
- **server/app.py** (수정): voice WebSocket 라우터 마운트
- **demo/index.html** (수정): WebSocket 프로토콜 연동

### 기술 스택
- FastAPI WebSocket, asyncio
- boto3 (Transcribe, Polly)
- amazon-transcribe-streaming-sdk

## 8. 데이터 모델
- 기존 VoiceSession dataclass 확장: `stt_handle`, `last_activity`, `turn_count` 추가
- 신규 데이터 없음 (음성 데이터 디스크 미저장)

## 9. API 설계

### WebSocket: `GET /api/v1/ws/voice`
- Upgrade: websocket
- 프로토콜: FR-002 참조
- 인증: 데모 범위 미구현

### 기존 REST: `POST /api/v1/turn` (변경 없음)

## 10. UI/UX 고려사항
- demo HTML: 연결 상태 표시, 녹음 버튼 (토글), 중단 버튼, 대화 로그
- 음성 재생: Web Audio API (AudioContext)
- 접근성: 텍스트 입력 폴백 지원

## 11. 마일스톤 및 일정

### Phase G-1: WebSocket 엔드포인트 + 프로토콜 (TASK 1~4)
- FastAPI WebSocket 라우터, 프로토콜 파싱, 세션 관리

### Phase G-2: 풀 파이프라인 연결 (TASK 5~8)
- VoiceServer 실제 엔진 연결, STT→Pipeline→TTS 통합

### Phase G-3: Barge-in + 폴백 + 세션 관리 (TASK 9~14)
- Barge-in 통합, 텍스트 폴백, 세션 제한/타임아웃

### Phase G-4: Demo + 계측 (TASK 15~16)
- HTML 클라이언트 업데이트, 레이턴시 계측

## 12. 리스크 및 완화 방안

### RISK-001: asyncio + 동기 엔진 충돌 (H/H)
- TurnPipeline.process()가 동기 → asyncio.to_thread() 래핑
- 완화: TranscribeSTTEngine은 이미 asyncio 안전 (PR #8)

### RISK-002: WebSocket 동시성 (M/M)
- 다수 세션 시 이벤트루프 블로킹
- 완화: 동기 호출은 to_thread(), 세션 제한 10

### RISK-003: Demo 브라우저 호환 (L/M)
- MediaRecorder API 브라우저 차이
- 완화: Chrome 기준 개발, polyfill 미적용

## 13. 성공 지표

| KPI | 목표 | 측정 방법 |
|-----|------|-----------|
| E2E RTT | P95 ≤ 8초 | FR-008 로그 |
| 한국어 인식률 | ≥ 95% (Polly 합성 기준) | E2E 테스트 |
| 테스트 커버리지 | ≥ 80% | pytest-cov |
| 동시 세션 | 10세션 안정 | 부하 테스트 |

## 14. 의존성

| 의존성 | 리스크 |
|--------|--------|
| AWS Transcribe Streaming | 낮음 (PR #8 검증) |
| Amazon Polly | 낮음 (E2E 검증) |
| FastAPI WebSocket | 낮음 (성숙 라이브러리) |
| amazon-transcribe-streaming-sdk | 낮음 (설치 완료) |

## 15. 범위 제외 사항
- WebSocket 인증/인가 (향후 Phase)
- 실제 전화망(SIP/PSTN) 연동
- Custom Vocabulary 튜닝
- 멀티 스피커 분리
- 음성 데이터 저장/분석
- process_audio_chunk 실시간 스트리밍 (Phase 2, 현재는 버퍼 누적)
