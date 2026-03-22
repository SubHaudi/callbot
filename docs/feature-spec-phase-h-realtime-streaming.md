# Phase H: 실시간 음성 스트리밍 기능정의서

## 1. 개요
- **한 줄 요약**: VoiceServer에 STT/TTS 엔진 실제 주입 + 실시간 오디오 스트리밍 + Demo HTML 업데이트로 end-to-end 음성 통화 완성
- **핵심 가치**: 브라우저에서 마이크로 말하면 AI가 음성으로 응답하는 데모를 실제로 동작시킴

## 2. 배경 및 목적
- **문제**: Phase G에서 WebSocket→STT→Pipeline→TTS 파이프라인을 구현했으나 STT/TTS 엔진이 실제 주입되지 않아 음성 대화가 동작하지 않음
- **As-Is**: VoiceServer에 pipeline만 주입, STT/TTS는 None → `stt_not_configured` 에러 반환. Demo HTML은 Phase F 버전(단순 녹음→재생)
- **To-Be**: TranscribeSTTEngine + PollyTTSEngine 주입, 브라우저에서 실시간 음성 대화 가능, partial transcript 표시
- **비즈니스 임팩트**: 콜봇 데모를 실제로 시연 가능한 상태로 만듦

## 3. 용어 정의

| 용어 | 정의 |
|------|------|
| 실시간 스트리밍 | 오디오 청크를 WebSocket으로 연속 전송하며 STT 결과를 실시간 수신 |
| partial transcript | STT의 중간 인식 결과 (is_final=false) |
| final transcript | STT의 최종 인식 결과 (is_final=true) |
| 오디오 버퍼 | 클라이언트에서 수집한 PCM 청크를 서버로 전송하기 전 누적하는 버퍼 |
| VAD (Voice Activity Detection) | 사용자 발화 시작/종료를 감지하는 메커니즘 |
| PCM 16kHz | 16000Hz 샘플레이트, 16bit, mono — Transcribe 입력 포맷 |

## 4. 사용자 스토리

- **US-001**: As a 데모 사용자, I want 브라우저에서 마이크로 말하면 AI가 음성으로 답해줌, So that 콜봇의 실제 동작을 확인할 수 있다
- **US-002**: As a 데모 사용자, I want 내가 말하는 동안 화면에 인식 중인 텍스트가 실시간 표시됨, So that 시스템이 내 말을 잘 알아듣고 있는지 확인할 수 있다
- **US-003**: As a 개발자, I want app.py에서 STT/TTS 엔진이 자동으로 초기화되어 VoiceServer에 주입됨, So that 배포만 하면 음성 파이프라인이 동작한다

## 5. 기능 요구사항

### FR-001: app.py에서 STT/TTS 엔진 초기화 및 주입 (P0)
- lifespan startup에서 TranscribeSTTEngine, PollyTTSEngine 인스턴스 생성
- VoiceServer 생성 시 stt_engine, tts_engine 파라미터로 주입
- AWS 자격증명 없으면 graceful degradation (텍스트 전용 모드, 로그 경고)
- 관련: US-003

### FR-002: 실시간 오디오 스트리밍 — 청크 단위 STT (P0)
- 클라이언트가 `{"type": "audio", "data": "<base64 PCM>"}` 청크를 연속 전송
- 서버는 세션당 하나의 STT 스트림을 유지하고 청크를 누적
- `{"type": "end"}` 수신 시 STT 최종 결과 요청 → Pipeline → TTS → 응답
- 청크 크기: 3200 bytes (100ms @ 16kHz 16bit mono)
- 관련: US-001, FR-003

### FR-003: partial transcript 실시간 전송 (P1)
- STT 스트리밍 중 partial result 발생 시 즉시 클라이언트로 전송
- `{"type": "transcript", "text": "...", "is_final": false}` — partial
- `{"type": "transcript", "text": "...", "is_final": true}` — final
- TranscribeSTTEngine의 _ResultHandler에서 partial 콜백 지원
- 관련: US-002

### FR-004: Demo HTML 클라이언트 업데이트 (P0)
- `voice_io/demo/index.html` 을 Phase G WebSocket 프로토콜에 맞게 재작성
- MediaRecorder → PCM 변환 (AudioWorklet 또는 ScriptProcessorNode)
- 실시간 partial transcript 표시 영역
- TTS 오디오 재생 (base64 PCM → AudioContext)
- barge-in 버튼 (interrupt 메시지 전송)
- 텍스트 폴백 입력 필드
- 연결 상태 표시 (connected/disconnected/error)
- 관련: US-001, US-002

### FR-005: `end` 메시지 핸들러 구현 (P0)
- `end` 수신 시: 현재 STT 스트림의 최종 결과 요청
- final transcript → Pipeline.process() → TTS → response 전송
- STT 스트림 종료 후 새 스트림 대기 상태로 전환 (다음 audio 청크 수신 시 새 스트림 생성)
- 관련: FR-002

### FR-006: VoiceServer handle_audio 리팩토링 — 스트리밍 지원 (P0)
- 기존 handle_audio: 한 번에 전체 오디오 받아 일괄 처리
- 변경: `handle_audio_chunk` (STT 스트림에 직접 전달) + `handle_end` (최종 처리) 분리
- `handle_audio_chunk`: 첫 청크 시 STT 스트림 자동 생성, 이후 청크는 기존 스트림에 전달
- `handle_end`: get_final_result → Pipeline → TTS → 응답
- partial transcript는 asyncio.Queue를 통해 voice_ws.py로 전달 (RISK-004 완화)
- 기존 handle_audio는 하위 호환을 위해 유지 (내부적으로 chunk+end 호출)
- 관련: FR-002, FR-005

### FR-007: STT 스트림 생명주기 관리 (P0)
- 스트림 생성: 첫 audio 청크 수신 시 자동 생성 (`start_stream`)
- 스트림 종료: `end` 수신 시 `get_final_result` → `stop_stream`
- 연속 발화: end 후 다시 audio 수신 시 새 스트림 자동 생성
- 비정상 종료: WebSocket disconnect 시 활성 STT 스트림 `stop_stream` + 리소스 정리
- barge-in: interrupt 수신 시 기존 스트림 stop → 새 스트림 대기 (Phase G handle_interrupt 유지)
- 관련: FR-002, FR-006

## 6. 비기능 요구사항

- **NFR-001**: RTT P95 ≤ 8초 (STT ≤1.5s + Pipeline ≤5s + TTS ≤1.5s) — Phase G 기준 유지
- **NFR-002**: 동시 10세션 안정 — Phase G 기준 유지
- **NFR-003**: 보안 (P0) — 음성 데이터 디스크 저장 안 함 (Phase F 규칙 유지)
- **NFR-004**: Python 3.9 호환 (P0)
- **NFR-005**: 테스트 커버리지 80% 이상

## 7. 기술 설계

### 아키텍처
```
Browser (Demo HTML)
  ↕ WebSocket (FR-002 프로토콜)
voice_ws.py (라우터)
  ↕ VoiceServer API
voice_server.py
  → TranscribeSTTEngine (실시간 스트리밍)
  → TurnPipeline (NLU + LLM)
  → PollyTTSEngine (TTS 합성)
```

### 스트리밍 흐름
1. 클라이언트: MediaRecorder → PCM 16kHz → base64 → `{"type":"audio"}` 전송
2. voice_ws.py: base64 디코딩 → `handle_audio_chunk(session_id, chunk)`
3. VoiceServer: STT 스트림에 청크 전달, partial 콜백 실행
4. voice_ws.py: partial transcript를 클라이언트로 전송
5. 클라이언트: `{"type":"end"}` 전송
6. voice_ws.py: `handle_end(session_id)` 호출
7. VoiceServer: get_final_result → Pipeline → TTS → 응답 반환
8. voice_ws.py: transcript + response + audio를 클라이언트로 전송

### 기술 스택
- AWS Transcribe Streaming SDK (`amazon-transcribe-0.6.4`)
- Amazon Polly (Seoyeon Neural, ko-KR)
- FastAPI WebSocket
- Web Audio API (AudioWorklet)

## 8. 데이터 모델

기존 VoiceSession 확장:
- `stt_stream_active: bool` — STT 스트림 활성 여부
- `partial_queue: asyncio.Queue` — partial transcript를 voice_ws.py로 전달하는 비동기 큐

## 9. API 설계

기존 WebSocket `/api/v1/ws/voice` 프로토콜 확장:

### 클라이언트→서버 (변경 없음)
- `{"type": "audio", "data": "<base64 PCM>"}` — 오디오 청크
- `{"type": "text", "text": "..."}` — 텍스트 폴백
- `{"type": "interrupt"}` — barge-in
- `{"type": "end"}` — 발화 종료 (이제 실제 동작)

### 서버→클라이언트 (변경 없음)
- `{"type": "transcript", "text": "...", "is_final": true/false}` — STT 결과
- `{"type": "response", "text": "...", "audio": "<base64 PCM 16kHz 16bit mono>", "processing_ms": N}` — 응답
- `{"type": "interrupted"}` — barge-in ACK
- `{"type": "error", "message": "..."}` — 에러
- `{"type": "fallback", "message": "..."}` — 폴백 전환

## 10. UI/UX 고려사항

### Demo HTML 레이아웃
- 상단: 연결 상태 표시 (🟢 Connected / 🔴 Disconnected)
- 중앙: 대화 로그 (사용자 발화 + AI 응답)
- 중앙: partial transcript 실시간 표시 (회색 텍스트, final 시 검정)
- 하단: 마이크 버튼 (🎙️ 녹음 시작/종료) + barge-in 버튼 (⏹️)
- 하단: 텍스트 입력 필드 (폴백용)
- Chrome 기준 개발 (Web Audio API)

## 11. 마일스톤 및 일정

### Phase H-1: STT/TTS 엔진 주입 + end 핸들러 (TASK 1~5)
- app.py에서 엔진 초기화/주입
- handle_audio_chunk + handle_end 분리
- VoiceSession 오디오 버퍼

### Phase H-2: 실시간 스트리밍 연결 (TASK 6~10)
- voice_ws.py에서 청크→handle_audio_chunk 라우팅
- end→handle_end 라우팅
- partial transcript 콜백 + 전송

### Phase H-3: Demo HTML + E2E (TASK 11~15)
- Demo HTML 재작성 (PCM 변환, partial 표시, TTS 재생)
- E2E 테스트
- 레이턴시 벤치마크

## 12. 리스크 및 완화 방안

- **RISK-001**: AWS 자격증명 없는 환경에서 초기화 실패 (M/M) → graceful degradation, try/except로 None 유지
- **RISK-002**: Transcribe Streaming SDK의 asyncio 호환성 이슈 (L/H) → PR #8에서 이미 해결 (ThreadPoolExecutor 패턴)
- **RISK-003**: 브라우저 AudioWorklet 호환성 (M/L) → Chrome 기준, ScriptProcessorNode 폴백
- **RISK-004**: partial transcript 콜백이 비동기 WebSocket send와 충돌 (M/M) → asyncio.Queue 사용 (FR-006에서 확정)

## 13. 성공 지표

| 지표 | 목표 | 측정 방법 |
|------|------|-----------|
| E2E 음성 대화 | 브라우저→서버→브라우저 왕복 동작 | 데모에서 수동 테스트 |
| RTT P95 | ≤ 8초 | processing_ms 측정 |
| partial transcript | 발화 중 실시간 표시 | 데모에서 확인 |
| 테스트 커버리지 | 80% | pytest --cov |
| 동시 세션 | 10세션 안정 | 부하 테스트 |

## 14. 의존성

| 의존성 | 리스크 |
|--------|--------|
| AWS Transcribe Streaming SDK (amazon-transcribe-0.6.4) | 저 — PR #8에서 검증 완료 |
| Amazon Polly (boto3) | 저 — PR #7에서 검증 완료 |
| IAM `CallbotVoiceIO` 정책 (transcribe:*, polly:*) | 저 — 이미 설정됨 |
| Chrome Web Audio API (AudioWorklet) | 중 — 브라우저 호환성 |

## 15. 범위 제외 사항

- SIP/PSTN 연결 (향후 Phase)
- WebSocket 인증 (향후 Phase)
- VAD 자동 감지 (현재는 수동 end 버튼)
- 다중 언어 지원 (현재 ko-KR만)
- 모바일 브라우저 최적화
- 프로덕션 배포 (Docker/ECS)
