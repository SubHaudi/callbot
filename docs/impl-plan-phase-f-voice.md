# Phase F: Voice I/O 통합 구현 계획

## 구현 원칙
- TDD 사이클: Red → Green → Refactor
- Tidy First: 구조적 변경과 행위적 변경을 분리
- 구조적 변경 먼저, 행위적 변경은 그 다음
- 각 커밋은 구조적 또는 행위적 중 하나만 포함

## 요구사항 추적 매트릭스

| 요구사항 ID | 요구사항 요약 | 관련 태스크 |
|-------------|-------------|-------------|
| FR-001 | AWS Transcribe Streaming STT 엔진 | TASK-005, TASK-006 |
| FR-002 | Polly TTS 엔진 | TASK-007, TASK-008 |
| FR-003 | FallbackSTTEngine 래퍼 | TASK-003, TASK-004 |
| FR-004 | WebSocket 음성 파이프라인 | TASK-013, TASK-014, TASK-015, TASK-016 |
| FR-005 | Barge-in 지원 | TASK-009, TASK-010, TASK-017, TASK-018 |
| FR-006 | 음성 데모 클라이언트 | TASK-019 |
| FR-007 | DTMF 특수키 처리 | TASK-011, TASK-012 |
| FR-008 | STTEngine ABC 확장 | TASK-001, TASK-002 |
| FR-009 | 텍스트 폴백 | TASK-015, TASK-016 |
| NFR-001 | 응답 시간 ≤8초 | TASK-020 |
| NFR-004 | 보안 (음성 미저장) | TASK-016 |
| NFR-005 | Python 3.9 호환 | 전체 |

## 구현 순서 개요

5개 스프린트로 구성:
- **F-1 (TASK-001~004)**: ABC 확장 + 팩토리 리팩토링
- **F-2 (TASK-005~006)**: TranscribeSTTEngine 구현
- **F-3 (TASK-007~008)**: PollyTTSEngine 구현
- **F-4 (TASK-009~012)**: Barge-in 수정 + DTMF 수정
- **F-5 (TASK-013~020)**: WebSocket 파이프라인 + 데모 클라이언트 + 벤치마크

## 태스크 목록

### F-1: ABC 확장 + 팩토리 리팩토링

### TASK-001: STTEngine ABC에 stop_stream/cancel 추가 (Structural)
- **변경 유형**: Structural
- **설명**: `STTEngine` ABC에 `stop_stream(handle: StreamHandle) -> None`과 `cancel(handle: StreamHandle) -> None` 추상 메서드 추가. 기존 테스트 벤더 어댑터에 빈 구현 추가.
- **의존성**: 없음
- **관련 요구사항**: FR-008
- **완료 기준**: 기존 테스트 전부 통과, 새 메서드가 ABC에 존재
- **커밋 메시지**: "structural: add stop_stream/cancel to STTEngine ABC (FR-008)"

### TASK-002: STTEngine ABC 확장 테스트 (Behavioral — Red → Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **테스트**: `stop_stream()`, `cancel()` 호출 시 NotImplementedError가 발생하지 않는지 확인 (구현체에서). ABC 인스턴스화 시 추상 메서드 검증.
- **의존성**: TASK-001
- **관련 요구사항**: FR-008
- **커밋 메시지**: "behavioral(green): add STTEngine ABC extension tests (FR-008)"

### TASK-003: FallbackSTTEngine 래퍼 구조 (Structural)
- **변경 유형**: Structural
- **설명**: `voice_io/fallback_stt.py` 생성. `FallbackSTTEngine(STTEngine)` 클래스 스켈레톤. `vendor_factory.py`의 `create_stt_engine` 반환타입을 `STTEngine`으로 통일 (Union 제거). 호출부 리팩토링.
- **의존성**: TASK-001
- **관련 요구사항**: FR-003
- **완료 기준**: 기존 테스트 통과, `create_stt_engine`이 항상 `STTEngine` 반환
- **커밋 메시지**: "structural: create FallbackSTTEngine, unify create_stt_engine return type (FR-003)"

### TASK-004: FallbackSTTEngine 동작 테스트 (Behavioral — Red → Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **테스트**: (1) 주 엔진 정상 → 주 엔진 결과 반환, (2) 주 엔진 실패 → STTFallbackError 발생 (텍스트 폴백 트리거), (3) health_check 위임, (4) close 위임
- **의존성**: TASK-003
- **관련 요구사항**: FR-003, FR-009
- **커밋 메시지**: "behavioral(green): implement FallbackSTTEngine with text fallback (FR-003)"

### F-2: TranscribeSTTEngine 구현

### TASK-005: TranscribeSTTEngine 구조 (Structural)
- **변경 유형**: Structural
- **설명**: `voice_io/transcribe_stt.py` 생성. `TranscribeSTTEngine(STTEngine)` 스켈레톤. boto3 transcribe 클라이언트 DI. 한국어 `ko-KR` 고정. PCM 16kHz 16bit mono 입력. 스트리밍 세션 관리 (버퍼 + partial results).
- **의존성**: TASK-001
- **관련 요구사항**: FR-001
- **완료 기준**: 기존 테스트 통과
- **커밋 메시지**: "structural: create TranscribeSTTEngine skeleton (FR-001)"

### TASK-006: TranscribeSTTEngine 동작 테스트 (Behavioral — Red → Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **테스트**: (1) Mock boto3 transcribe 클라이언트로 한국어 텍스트 반환 확인, (2) confidence threshold 검증, (3) stop_stream/cancel 동작, (4) 빈 오디오 → 빈 결과, (5) 클라이언트 미설정 시 RuntimeError, (6) language_code=ko-KR 확인. boto3 mock으로 테스트.
- **의존성**: TASK-005
- **관련 요구사항**: FR-001
- **커밋 메시지**: "behavioral(green): implement TranscribeSTTEngine with mock tests (FR-001)"

### F-3: PollyTTSEngine 구현

### TASK-007: PollyTTSEngine 구조 (Structural)
- **변경 유형**: Structural
- **설명**: `voice_io/polly_tts.py` 생성. `PollyTTSEngine(TTSEngine)` 스켈레톤. SSML 변환 헬퍼 메서드. boto3 Polly 클라이언트 DI.
- **의존성**: 없음
- **관련 요구사항**: FR-002
- **완료 기준**: 기존 테스트 통과
- **커밋 메시지**: "structural: create PollyTTSEngine skeleton (FR-002)"

### TASK-008: PollyTTSEngine 동작 테스트 (Behavioral — Red → Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **테스트**: (1) Mock boto3 Polly로 음성 합성 호출 확인, (2) SSML 변환 정확성, (3) 문장 단위 분할, (4) 속도 팩터 적용, (5) stop_playback 동작. boto3 mock으로 AWS 의존 없이 테스트.
- **의존성**: TASK-007
- **관련 요구사항**: FR-002
- **커밋 메시지**: "behavioral(green): implement PollyTTSEngine with mock tests (FR-002)"

### F-4: Barge-in + DTMF 수정

### TASK-009: BargeInHandler 이벤트 콜백 확장 (Structural)
- **변경 유형**: Structural
- **설명**: `BargeInHandler` Protocol에 `speech_start(session_id: str) -> None`, `speech_end(session_id: str) -> None` 콜백 추가 (M-29). `stop_playback()`이 세션 상태를 stopped 플래그로 전환하도록 인터페이스 명확화 (M-30).
- **의존성**: 없음
- **관련 요구사항**: FR-005
- **완료 기준**: 기존 테스트 통과
- **커밋 메시지**: "structural: extend BargeInHandler with speech events (FR-005, M-29, M-30)"

### TASK-010: Barge-in 이벤트 테스트 (Behavioral — Red → Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **테스트**: (1) speech_start 콜백 호출 확인, (2) speech_end 콜백 호출 확인, (3) stop_playback 시 세션 상태 stopped 플래그 확인 (삭제 아님), (4) 이미 stopped인 세션에 다시 stop_playback → 무시
- **의존성**: TASK-009
- **관련 요구사항**: FR-005
- **커밋 메시지**: "behavioral(green): implement barge-in speech events and stopped flag (FR-005)"

### TASK-011: DTMF 특수키 + TTL 구조 (Structural)
- **변경 유형**: Structural
- **설명**: `dtmf_processor.py`에 `*`, `#` 키 매핑 상수 추가. 세션 TTL 정리 메커니즘 구조 준비.
- **의존성**: 없음
- **관련 요구사항**: FR-007
- **완료 기준**: 기존 DTMF 테스트 통과
- **커밋 메시지**: "structural: add DTMF special key constants and TTL structure (FR-007, M-26, M-32)"

### TASK-012: DTMF 특수키 + TTL 테스트 (Behavioral — Red → Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **테스트**: (1) `*` 키 → "이전 메뉴" 매핑, (2) `#` 키 → "입력 확인" 매핑, (3) TTL 만료 시 DTMF 세션 자동 정리, (4) TTL 미만 시 세션 유지
- **의존성**: TASK-011
- **관련 요구사항**: FR-007
- **커밋 메시지**: "behavioral(green): implement DTMF special keys and TTL cleanup (FR-007)"

### F-5: WebSocket 파이프라인 + 데모 + 벤치마크

### TASK-013: AudioConverter 구조 (Structural)
- **변경 유형**: Structural
- **설명**: `voice_io/audio_converter.py` 생성. ffmpeg 기반 opus→PCM 16kHz 변환, PCM 24kHz→opus 변환 클래스. ffmpeg 바이너리 존재 확인.
- **의존성**: 없음
- **관련 요구사항**: FR-004
- **완료 기준**: import 성공
- **커밋 메시지**: "structural: create AudioConverter skeleton (FR-004)"

### TASK-014: AudioConverter 동작 테스트 (Behavioral — Red → Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **테스트**: (1) opus→PCM 변환 (mock ffmpeg subprocess), (2) PCM→opus 변환 (mock), (3) ffmpeg 미설치 시 적절한 에러, (4) 빈 오디오 입력 처리
- **의존성**: TASK-013
- **관련 요구사항**: FR-004
- **커밋 메시지**: "behavioral(green): implement AudioConverter with ffmpeg (FR-004)"

### TASK-015: VoiceServer WebSocket 구조 (Structural)
- **변경 유형**: Structural
- **설명**: `voice_io/voice_server.py` 생성. FastAPI WebSocket 엔드포인트 `/api/v1/ws/voice`. `VoiceSession` 데이터 클래스. 세션 관리(생성/종료). STT→TurnPipeline→TTS 파이프라인 와이어링 구조.
- **의존성**: TASK-001, TASK-003, TASK-005, TASK-007, TASK-013
- **관련 요구사항**: FR-004, FR-009
- **완료 기준**: import 성공, 기존 테스트 통과
- **커밋 메시지**: "structural: create VoiceServer WebSocket skeleton (FR-004)"

### TASK-016: VoiceServer 동작 테스트 (Behavioral — Red → Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Red → Green
- **테스트**: (1) WebSocket 연결 → session_started 메시지, (2) 오디오 전송 → transcript 메시지, (3) transcript → TurnPipeline 호출 → response_text + audio 메시지, (4) STT 실패 → error 메시지 (텍스트 폴백), (5) end_session → 세션 정리, (6) 음성 데이터 디스크 저장 안 함 확인 (NFR-004), (7) VAD 침묵 감지 1.0초 기본값 검증 + 설정 가능 범위 0.5~2.0초 확인 (FR-004), (8) partial transcript 메시지 전송 확인 (US-018). Mock STT/TTS/Pipeline 사용.
- **의존성**: TASK-015
- **관련 요구사항**: FR-004, FR-009, NFR-004
- **커밋 메시지**: "behavioral(green): implement VoiceServer WebSocket pipeline (FR-004, FR-009)"

### TASK-017: VoiceServer Barge-in 테스트 (Behavioral — Red)
- **변경 유형**: Behavioral
- **TDD 단계**: Red
- **테스트**: (1) TTS 재생 중 interrupt 메시지 → TTS 중단, (2) TTS 재생 중 새 오디오 → TTS 중단 + 새 STT 시작, (3) stopped 상태에서 새 발화 정상 처리
- **의존성**: TASK-016, TASK-010
- **관련 요구사항**: FR-005
- **커밋 메시지**: "behavioral(red): add VoiceServer barge-in tests (FR-005)"

### TASK-018: VoiceServer Barge-in 구현 (Behavioral — Green)
- **변경 유형**: Behavioral
- **TDD 단계**: Green
- **구현**: VoiceServer에 barge-in 핸들링 로직 추가. interrupt 메시지 처리, VAD 기반 자동 감지.
- **의존성**: TASK-017
- **관련 요구사항**: FR-005
- **완료 기준**: TASK-017 테스트 통과
- **커밋 메시지**: "behavioral(green): implement VoiceServer barge-in handler (FR-005)"

### TASK-019: 음성 데모 클라이언트 (Behavioral)
- **변경 유형**: Behavioral
- **설명**: `static/voice-demo.html` — 단일 HTML+JS 파일. 마이크 캡처 (MediaRecorder, opus) → WebSocket 전송. 서버 오디오 수신 → AudioContext 재생. 실시간 자막 표시. TTS 스킵 버튼. 연결 상태 표시.
- **의존성**: TASK-016
- **관련 요구사항**: FR-006
- **커밋 메시지**: "behavioral: create voice demo HTML client (FR-006)"

### TASK-020: RTT + Barge-in 벤치마크 테스트 (Behavioral)
- **변경 유형**: Behavioral
- **설명**: (1) Mock STT(지연 2.5s) + Mock TTS(0.8s) + Mock LLM(2.5s) 환경에서 VoiceServer E2E RTT ≤ 8초 확인 (P95). (2) Barge-in 중단 지연 P95 < 200ms 측정 — TTS 재생 중 interrupt 전송 후 중단까지 소요 시간.
- **의존성**: TASK-016, TASK-018
- **관련 요구사항**: NFR-001
- **커밋 메시지**: "behavioral: add voice pipeline RTT benchmark (NFR-001)"

## 태스크 의존성 그래프

```
TASK-001 → TASK-002
    ↓
    ├── TASK-003 → TASK-004
    │       ↓
    └── TASK-005 → TASK-006
                ↓
    TASK-003 ──→ TASK-015 ←── TASK-005
    TASK-007 → TASK-008 ──→↗
    TASK-013 → TASK-014 ──→↗
                     ↓
                  TASK-016 → TASK-017 → TASK-018
                     ↓           ↑          ↓
                  TASK-019   TASK-010    TASK-020
                                ↑
                            TASK-009

TASK-011 → TASK-012  (독립)
```

병렬 가능 구간:
- TASK-003/004와 TASK-005/006는 TASK-001 완료 후 병렬 가능
- F-3(TASK-007~008)은 의존 없이 독립 병렬 가능
- F-4(TASK-009~012)는 독립 병렬 가능
- TASK-019와 TASK-020은 각각 TASK-016, TASK-018 완료 후 병렬 가능

## 테스트 전략
- **단위 테스트**: 각 엔진(STT/TTS)은 mock으로 외부 의존 없이 테스트
- **통합 테스트**: VoiceServer + Mock 엔진으로 WebSocket E2E
- **벤치마크**: RTT 지연 시뮬레이션으로 NFR-001 검증
- **테스트 커버리지**: 새 코드 80% 이상
- **회귀 방지**: 기존 133 테스트 전체 통과 유지
