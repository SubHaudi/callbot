# Phase G: Full Voice Pipeline 구현 계획

## 구현 원칙
- TDD 사이클: Red → Green → Refactor
- Tidy First: 구조적 변경과 행위적 변경을 분리
- 각 커밋은 구조적 또는 행위적 중 하나만 포함

## 요구사항 추적 매트릭스

| 요구사항 ID | 요약 | 관련 태스크 |
|-------------|------|-------------|
| FR-001 | FastAPI WebSocket 엔드포인트 | TASK-001, TASK-002 |
| FR-002 | WebSocket 프로토콜 | TASK-003, TASK-004 |
| FR-003 | STT→Pipeline→TTS 풀 파이프라인 | TASK-005, TASK-006, TASK-007, TASK-008 |
| FR-004 | Barge-in 통합 | TASK-009, TASK-010 |
| FR-005 | 텍스트 폴백 모드 | TASK-011, TASK-012 |
| FR-006 | Demo HTML 클라이언트 | TASK-015 |
| FR-007 | 세션 관리 (제한/타임아웃) | TASK-013, TASK-014 |
| FR-008 | 레이턴시 계측 | TASK-016 |
| NFR-001 | RTT P95 ≤ 8초 | TASK-016 |
| NFR-002 | 동시 10세션 | TASK-013 |
| NFR-003 | 음성 데이터 디스크 미저장 | 전체 (코드 리뷰로 검증) |
| NFR-004 | Python 3.9 호환 | 전체 |
| NFR-005 | 테스트 커버리지 80% | 전체 |

## 구현 순서 개요

G-1: WebSocket 엔드포인트 + 프로토콜 (TASK-001~004)
G-2: 풀 파이프라인 연결 (TASK-005~008)
G-3: Barge-in + 폴백 + 세션 관리 (TASK-009~014)
G-4: Demo + 계측 (TASK-015~016)

## 태스크 목록

### TASK-001: voice_ws.py 모듈 + FastAPI WebSocket 라우터 스켈레톤
- **변경 유형**: Structural
- **TDD 단계**: Setup
- **설명**: `server/voice_ws.py` 생성 — FastAPI WebSocket 라우터, `/api/v1/ws/voice` 엔드포인트 스켈레톤. accept → echo → close.
- **의존성**: 없음
- **관련 요구사항**: FR-001
- **완료 기준**: 라우터 파일 존재, app.py에 마운트, 기존 테스트 통과
- **커밋 메시지**: "structural: add voice_ws.py WebSocket router skeleton"

### TASK-002: WebSocket 연결/종료 테스트
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: WebSocket 연결 시 VoiceSession 생성, disconnect 시 자동 정리 검증
- **테스트**: `test_ws_connect_creates_session`, `test_ws_disconnect_cleans_session`
- **구현**: voice_ws.py에 VoiceServer.create_session/end_session 연결
- **의존성**: TASK-001
- **관련 요구사항**: FR-001, FR-007
- **완료 기준**: 2개 테스트 통과
- **커밋 메시지**: "behavioral: WebSocket connect/disconnect session lifecycle"

### TASK-003: WebSocket 프로토콜 메시지 파싱
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: 클라이언트→서버 JSON 메시지 파싱 — audio, text, interrupt, end 타입 분기
- **테스트**: `test_parse_audio_message`, `test_parse_text_message`, `test_parse_interrupt_message`, `test_parse_end_message`, `test_parse_unknown_type_returns_error`
- **구현**: voice_ws.py에 메시지 핸들러 추가
- **의존성**: TASK-002
- **관련 요구사항**: FR-002
- **완료 기준**: 5개 테스트 통과
- **커밋 메시지**: "behavioral: WebSocket protocol message parsing"

### TASK-004: WebSocket 서버→클라이언트 응답 포맷
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: 서버→클라이언트 JSON 응답 생성 — transcript, response, error, fallback, interrupted 타입
- **테스트**: `test_send_transcript`, `test_send_response_with_audio`, `test_send_error`, `test_send_interrupted_ack`
- **구현**: 응답 헬퍼 함수들
- **의존성**: TASK-003
- **관련 요구사항**: FR-002
- **완료 기준**: 4개 테스트 통과
- **커밋 메시지**: "behavioral: WebSocket server-to-client response format"

### TASK-005: VoiceServer.handle_audio → async 래핑 구조 준비
- **변경 유형**: Structural
- **TDD 단계**: Setup
- **설명**: VoiceServer.handle_audio()에서 동기 TurnPipeline.process() 호출을 asyncio.to_thread()로 래핑하는 구조 준비. STT는 이미 async 안전 (PR #8).
- **의존성**: TASK-004
- **관련 요구사항**: FR-003
- **완료 기준**: 기존 테스트 통과, 구조만 변경
- **커밋 메시지**: "structural: prepare async wrapper for Pipeline in handle_audio"

### TASK-006: STT→Pipeline 연결 테스트
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: handle_audio에서 STT final → TurnPipeline.process() 호출 검증 (mock)
- **테스트**: `test_handle_audio_calls_pipeline_with_stt_text`, `test_handle_audio_empty_stt_returns_error`
- **구현**: handle_audio에서 to_thread(pipeline.process) 호출
- **의존성**: TASK-005
- **관련 요구사항**: FR-003
- **완료 기준**: 2개 테스트 통과
- **커밋 메시지**: "behavioral: STT to Pipeline integration in handle_audio"

### TASK-007: Pipeline→TTS 연결 테스트
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: Pipeline 응답 → PollyTTSEngine.synthesize() → 오디오 반환 검증 (mock)
- **테스트**: `test_handle_audio_returns_tts_audio`, `test_handle_audio_tts_failure_returns_text_only`
- **구현**: handle_audio에 TTS 합성 + base64 인코딩 추가
- **의존성**: TASK-006
- **관련 요구사항**: FR-003
- **완료 기준**: 2개 테스트 통과
- **커밋 메시지**: "behavioral: Pipeline to TTS integration in handle_audio"

### TASK-008: WebSocket 풀 파이프라인 E2E (mock)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: WebSocket으로 audio 메시지 전송 → transcript + response + audio 수신 E2E (mock 엔진들)
- **테스트**: `test_ws_full_pipeline_mock_e2e`
- **구현**: voice_ws.py에서 handle_audio 결과를 WebSocket 응답으로 변환
- **의존성**: TASK-007
- **관련 요구사항**: FR-001, FR-002, FR-003
- **완료 기준**: E2E 테스트 통과
- **커밋 메시지**: "behavioral: full pipeline E2E test via WebSocket (mock engines)"

### TASK-009: Barge-in interrupt 핸들링
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: interrupt 메시지 수신 → TTS stop_playback + interrupted ACK 전송
- **테스트**: `test_interrupt_stops_tts_and_sends_ack`, `test_interrupt_when_not_playing`
- **구현**: voice_ws.py interrupt 핸들러
- **의존성**: TASK-008
- **관련 요구사항**: FR-004
- **완료 기준**: 2개 테스트 통과
- **커밋 메시지**: "behavioral: barge-in interrupt handling with ACK"

### TASK-010: Barge-in 후 STT 스트림 재시작
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: interrupt 후 기존 STT 핸들 stop_stream → 새 STT 스트림 시작
- **테스트**: `test_interrupt_restarts_stt_stream`
- **구현**: handle_interrupt에서 STT 핸들 교체 로직
- **의존성**: TASK-009
- **관련 요구사항**: FR-004
- **완료 기준**: 1개 테스트 통과
- **커밋 메시지**: "behavioral: restart STT stream after barge-in"

### TASK-011: 텍스트 폴백 전환
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: STTFallbackError → 텍스트 폴백 모드 전환 + fallback 메시지 전송
- **테스트**: `test_stt_failure_triggers_text_fallback`, `test_fallback_sends_fallback_message`
- **구현**: handle_audio에서 STTFallbackError catch → 폴백 전환
- **의존성**: TASK-008
- **관련 요구사항**: FR-005
- **완료 기준**: 2개 테스트 통과
- **커밋 메시지**: "behavioral: text fallback on STT failure"

### TASK-012: 텍스트 폴백 모드에서 text 메시지 처리
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: 폴백 모드에서 {"type":"text"} 수신 → Pipeline → TTS → 응답
- **테스트**: `test_text_fallback_processes_text_input`, `test_text_input_in_normal_mode_rejected`
- **구현**: voice_ws.py에 handle_text 로직
- **의존성**: TASK-011
- **관련 요구사항**: FR-005
- **완료 기준**: 2개 테스트 통과
- **커밋 메시지**: "behavioral: text input processing in fallback mode"

### TASK-013: 동시 세션 제한
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: VoiceServer에 max_sessions 파라미터, 초과 시 WebSocket 연결 거부
- **테스트**: `test_max_sessions_rejects_new_connection`, `test_session_count_tracks_correctly`
- **구현**: create_session에서 제한 체크
- **의존성**: TASK-002
- **관련 요구사항**: FR-007, NFR-002
- **완료 기준**: 2개 테스트 통과
- **커밋 메시지**: "behavioral: concurrent session limit (max 10)"

### TASK-014: 세션 타임아웃
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: VoiceSession에 last_activity 추적, 5분 무활동 시 자동 종료
- **테스트**: `test_session_timeout_auto_cleanup`, `test_activity_resets_timeout`
- **구현**: VoiceSession.last_activity + VoiceServer.cleanup_expired()
- **의존성**: TASK-013
- **관련 요구사항**: FR-007
- **완료 기준**: 2개 테스트 통과
- **커밋 메시지**: "behavioral: session timeout after 5min inactivity"

### TASK-015: Demo HTML 클라이언트 업데이트
- **변경 유형**: Behavioral
- **TDD 단계**: Green (프론트엔드, 수동 검증)
- **설명**: voice_io/demo/index.html을 FR-002 프로토콜에 맞게 수정. MediaRecorder → PCM → base64, AudioContext 재생, interrupted ACK 처리
- **의존성**: TASK-008
- **관련 요구사항**: FR-006
- **완료 기준**: 브라우저에서 음성 대화 데모 동작
- **커밋 메시지**: "behavioral: update demo HTML for WebSocket voice protocol"

### TASK-016: 레이턴시 계측 + RTT 벤치마크
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: handle_audio에 단계별 타이밍 로깅, 응답에 processing_ms 포함
- **테스트**: `test_response_includes_processing_ms`, `test_rtt_under_8s_mock`
- **구현**: time.perf_counter() 계측, 응답 필드 추가
- **의존성**: TASK-008
- **관련 요구사항**: FR-008, NFR-001
- **완료 기준**: 2개 테스트 통과
- **커밋 메시지**: "behavioral: latency instrumentation and RTT benchmark"

## 태스크 의존성 그래프

```
TASK-001 → TASK-002 → TASK-003 → TASK-004
                ↓                      ↓
           TASK-013 → TASK-014    TASK-005 → TASK-006 → TASK-007 → TASK-008
                                                                      ↓
                                                    TASK-009 → TASK-010
                                                    TASK-011 → TASK-012
                                                    TASK-015
                                                    TASK-016
```

## 테스트 전략
- **단위 테스트**: 프로토콜 파싱, 응답 포맷, 세션 관리
- **통합 테스트**: VoiceServer + mock 엔진들 → handle_audio 풀 경로
- **E2E 테스트**: FastAPI TestClient WebSocket → 전체 파이프라인
- **테스트 커버리지 목표**: 80% 이상
- **AWS 실제 테스트**: `@pytest.mark.integration` 마커로 분리
