# Phase H: 실시간 음성 스트리밍 구현 계획

## 구현 원칙
- TDD 사이클: Red → Green → Refactor
- Tidy First: 구조적 변경과 행위적 변경을 분리
- 각 커밋은 구조적 또는 행위적 중 하나만 포함

## 요구사항 추적 매트릭스

| 요구사항 ID | 요약 | 관련 태스크 |
|-------------|------|-------------|
| FR-001 | app.py STT/TTS 엔진 초기화 및 주입 | TASK-001, TASK-002 |
| FR-002 | 실시간 오디오 스트리밍 — 청크 단위 STT | TASK-005, TASK-006 |
| FR-003 | partial transcript 실시간 전송 | TASK-007, TASK-008 |
| FR-004 | Demo HTML 클라이언트 | TASK-014 |
| FR-005 | end 메시지 핸들러 | TASK-009, TASK-010 |
| FR-006 | handle_audio 리팩토링 | TASK-003, TASK-004, TASK-005 |
| FR-007 | STT 스트림 생명주기 관리 | TASK-003, TASK-009, TASK-011 |
| NFR-001 | RTT P95 ≤ 8초 | TASK-015 |
| NFR-002 | 동시 10세션 | Phase G에서 구현 완료 |
| NFR-003 | 음성 데이터 디스크 미저장 | 전체 (코드 리뷰로 검증) |
| NFR-004 | Python 3.9 호환 | 전체 |
| NFR-005 | 테스트 커버리지 80% | 전체 |

## 구현 순서 개요

H-1: STT/TTS 엔진 주입 + 리팩토링 (TASK-001~004)
H-2: 실시간 스트리밍 + partial transcript (TASK-005~010)
H-3: 비정상 종료 cleanup + voice_ws 라우팅 (TASK-011~013)
H-4: Demo HTML + 레이턴시 벤치마크 (TASK-014~015)

## 태스크 목록

### TASK-001: app.py에서 TranscribeSTTEngine 초기화 (Structural)
- **변경 유형**: Structural
- **설명**: lifespan startup에서 TranscribeSTTEngine 인스턴스 생성. AWS 자격증명 없으면 None (graceful degradation).
- **의존성**: 없음
- **관련 요구사항**: FR-001
- **완료 기준**: 기존 테스트 통과, STT 엔진 초기화 로직 존재
- **커밋 메시지**: "structural: initialize TranscribeSTTEngine in app.py lifespan"

### TASK-002: app.py에서 PollyTTSEngine 초기화 + VoiceServer 주입 (Behavioral)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: PollyTTSEngine 초기화, VoiceServer에 stt_engine + tts_engine 주입
- **테스트**: `test_voice_server_has_stt_and_tts_engines`, `test_graceful_degradation_without_aws`
- **의존성**: TASK-001
- **관련 요구사항**: FR-001
- **완료 기준**: VoiceServer에 엔진 주입됨, AWS 없을 때 None으로 graceful
- **커밋 메시지**: "behavioral: inject STT/TTS engines into VoiceServer"

### TASK-003: VoiceSession에 stt_stream_active + partial_queue 추가 (Structural)
- **변경 유형**: Structural
- **설명**: VoiceSession dataclass에 `stt_stream_active: bool = False`, `partial_queue: asyncio.Queue` 필드 추가
- **의존성**: 없음
- **관련 요구사항**: FR-007, FR-003
- **완료 기준**: 기존 테스트 통과
- **커밋 메시지**: "structural: add stt_stream_active and partial_queue to VoiceSession"

### TASK-004: handle_audio_chunk + handle_end 메서드 스켈레톤 (Structural)
- **변경 유형**: Structural
- **설명**: VoiceServer에 `handle_audio_chunk(session_id, chunk)` → Dict, `handle_end(session_id)` → Dict 스켈레톤 추가. 기존 handle_audio 유지.
- **의존성**: TASK-003
- **관련 요구사항**: FR-006
- **완료 기준**: 기존 테스트 통과, 새 메서드 존재
- **커밋 메시지**: "structural: add handle_audio_chunk and handle_end skeletons"

### TASK-005: handle_audio_chunk — STT 스트림 자동 생성 + 청크 전달 (Behavioral)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: 첫 청크 시 STT 스트림 자동 생성 (start_stream), 이후 청크는 process_audio_chunk로 전달
- **테스트**: `test_first_chunk_creates_stt_stream`, `test_subsequent_chunks_reuse_stream`, `test_chunk_without_stt_returns_error`
- **의존성**: TASK-004
- **관련 요구사항**: FR-002, FR-006, FR-007
- **완료 기준**: 3개 테스트 통과
- **커밋 메시지**: "behavioral: handle_audio_chunk with auto STT stream creation"

### TASK-006: handle_audio_chunk — STT None guard (Behavioral)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: STT 엔진이 None이면 `stt_not_configured` 에러 반환
- **테스트**: `test_audio_chunk_without_stt_returns_error`
- **의존성**: TASK-005
- **관련 요구사항**: FR-001, FR-002
- **완료 기준**: 1개 테스트 통과
- **커밋 메시지**: "behavioral: handle_audio_chunk STT None guard"

### TASK-007: partial transcript — asyncio.Queue 기반 전달 (Behavioral)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: handle_audio_chunk에서 STT partial result 발생 시 session.partial_queue에 넣기. TranscribeSTTEngine의 _ResultHandler partial 이벤트 → Queue
- **테스트**: `test_partial_result_enqueued`, `test_partial_queue_empty_when_no_partial`
- **의존성**: TASK-005
- **관련 요구사항**: FR-003
- **완료 기준**: 2개 테스트 통과
- **커밋 메시지**: "behavioral: partial transcript via asyncio.Queue"

### TASK-008: voice_ws.py — partial transcript 실시간 전송 (Behavioral)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: voice_ws.py에서 audio 청크 처리 중 partial_queue를 비동기로 drain하여 클라이언트에 transcript 메시지 전송
- **테스트**: `test_ws_receives_partial_transcript` (E2E mock)
- **의존성**: TASK-007
- **관련 요구사항**: FR-003
- **완료 기준**: 1개 테스트 통과
- **커밋 메시지**: "behavioral: send partial transcripts from queue to WebSocket"

### TASK-009: handle_end — STT final + Pipeline + TTS (Behavioral)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: end 수신 시 get_final_result → Pipeline → TTS → 응답. STT 스트림 종료.
- **테스트**: `test_handle_end_returns_full_response`, `test_handle_end_without_active_stream`
- **의존성**: TASK-005
- **관련 요구사항**: FR-005, FR-007
- **완료 기준**: 2개 테스트 통과
- **커밋 메시지**: "behavioral: handle_end with STT final + Pipeline + TTS"

### TASK-010: voice_ws.py — end 메시지 라우팅 (Behavioral)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: voice_ws.py에서 `end` 메시지 수신 시 handle_end 호출 + transcript + response 전송
- **테스트**: `test_ws_end_triggers_response` (E2E mock)
- **의존성**: TASK-009
- **관련 요구사항**: FR-005
- **완료 기준**: 1개 테스트 통과
- **커밋 메시지**: "behavioral: route end message to handle_end in voice_ws"

### TASK-011: 비정상 종료 cleanup — STT 스트림 정리 (Behavioral)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: WebSocket disconnect 시 활성 STT 스트림 stop_stream, 리소스 정리
- **테스트**: `test_disconnect_cleans_active_stt_stream`, `test_disconnect_without_stream_no_error`
- **의존성**: TASK-005
- **관련 요구사항**: FR-007
- **완료 기준**: 2개 테스트 통과
- **커밋 메시지**: "behavioral: cleanup STT stream on WebSocket disconnect"

### TASK-011B: barge-in 시 STT 스트림 정리 (Behavioral)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: interrupt 수신 시 활성 STT 스트림 stop_stream + stt_stream_active 리셋. Phase G handle_interrupt 확장.
- **테스트**: `test_interrupt_stops_active_stt_stream`, `test_interrupt_without_stream_no_error`
- **의존성**: TASK-005, TASK-011
- **관련 요구사항**: FR-007
- **완료 기준**: 2개 테스트 통과
- **커밋 메시지**: "behavioral: stop STT stream on barge-in interrupt"

### TASK-011C: handle_audio 하위 호환 위임 (Behavioral)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: 기존 handle_audio를 내부적으로 handle_audio_chunk + handle_end로 위임. 기존 API 호환 유지.
- **테스트**: `test_legacy_handle_audio_delegates_to_chunk_and_end`
- **의존성**: TASK-009
- **관련 요구사항**: FR-006
- **완료 기준**: 1개 테스트 통과
- **커밋 메시지**: "behavioral: delegate handle_audio to chunk+end for backward compat"

### TASK-012: voice_ws.py — audio 청크 라우팅 변경 (Behavioral)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: voice_ws.py에서 audio 메시지를 handle_audio 대신 handle_audio_chunk로 라우팅
- **테스트**: `test_ws_audio_routes_to_chunk_handler` (E2E mock)
- **의존성**: TASK-008, TASK-010
- **관련 요구사항**: FR-002, FR-006
- **완료 기준**: 1개 테스트 통과
- **커밋 메시지**: "behavioral: route audio to handle_audio_chunk in voice_ws"

### TASK-013: 연속 발화 테스트 (Behavioral)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: end 후 다시 audio 수신 → 새 STT 스트림 자동 생성 검증
- **테스트**: `test_consecutive_utterances_create_new_streams`
- **의존성**: TASK-009, TASK-012
- **관련 요구사항**: FR-007
- **완료 기준**: 1개 테스트 통과
- **커밋 메시지**: "behavioral: verify consecutive utterance STT stream lifecycle"

### TASK-014: Demo HTML 클라이언트 재작성 (Behavioral)
- **변경 유형**: Behavioral
- **TDD 단계**: Green (프론트엔드, 수동 검증)
- **설명**: voice_io/demo/index.html을 Phase H 프로토콜에 맞게 재작성. MediaRecorder→PCM, partial transcript 표시, TTS 재생, barge-in, 텍스트 폴백, 연결 상태
- **의존성**: TASK-012
- **관련 요구사항**: FR-004
- **완료 기준**: 브라우저에서 실시간 음성 대화 데모 동작
- **커밋 메시지**: "behavioral: rewrite demo HTML for realtime streaming"

### TASK-015: 레이턴시 벤치마크 (Behavioral)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **설명**: E2E 레이턴시 측정 — STT + Pipeline + TTS 단계별 타이밍
- **테스트**: `test_end_to_end_processing_ms_in_response`
- **의존성**: TASK-009
- **관련 요구사항**: NFR-001
- **완료 기준**: processing_ms가 응답에 포함됨
- **커밋 메시지**: "behavioral: latency benchmark for realtime pipeline"

## 태스크 의존성 그래프

```
TASK-001 → TASK-002
TASK-003 → TASK-004 → TASK-005 → TASK-006
                          ↓
                    TASK-007 → TASK-008
                    TASK-009 → TASK-010
                    TASK-011
                          ↓
              TASK-008 + TASK-010 → TASK-012 → TASK-013
                                         ↓
                                    TASK-014
              TASK-009 → TASK-015
```

## 테스트 전략
- **단위 테스트**: handle_audio_chunk, handle_end, STT 스트림 생명주기
- **통합 테스트**: VoiceServer + mock STT/TTS → 청크→partial→end→response 풀 경로
- **E2E 테스트**: FastAPI TestClient WebSocket → 전체 파이프라인 (mock 엔진)
- **수동 테스트**: Demo HTML + 실제 AWS 엔진 (브라우저)
- **테스트 커버리지 목표**: 80% 이상
