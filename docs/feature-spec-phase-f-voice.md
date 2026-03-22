# Phase F: Voice I/O 통합 기능정의서

## 1. 개요
- 기존 텍스트 파이프라인(Phase C~E)에 음성 입출력 레이어를 통합하여 실제 콜봇 경험을 구현
- 핵심 가치: "음성으로 말하면 음성으로 답하는" E2E 콜봇 데모

## 2. 배경 및 목적

> **참조**: M-번호(M-26~M-33)와 C-05는 `docs/code-review-report.md`의 코드 리뷰 이슈 ID임.

- **As-Is**: 텍스트 기반 파이프라인만 동작 (133 tests). voice_io/ 모듈에 ABC, 벤더 어댑터, 데이터 모델은 있으나 실제 STT/TTS 엔진 통합 없음. `vendor_factory.py`의 `create_stt_engine` 반환타입이 `STTEngine | tuple` Union으로 호출부 분기 필요 (C-05).
- **To-Be**: AWS Transcribe Streaming STT + Amazon Polly TTS + WebSocket 음성 파이프라인 + 브라우저 데모 클라이언트. Barge-in 지원. STT 엔진은 ABC로 추상화되어 추후 faster-whisper(GPU) 등으로 교체 가능.
- **비즈니스 임팩트**: 데모/포트폴리오에서 "실제 콜센터처럼 음성 대화"를 시연 가능

## 3. 용어 정의

| 용어 | 정의 |
|------|------|
| AWS Transcribe Streaming | AWS 관리형 실시간 음성 인식 서비스 (스트리밍 API) |
| Polly | Amazon Polly — AWS 관리형 TTS 서비스 |
| Seoyeon | Amazon Polly 한국어 Neural 음성 |
| VAD | Voice Activity Detection — 음성 구간과 묵음 구간 구분 |
| Barge-in | TTS 재생 중 사용자가 말하면 재생 중단 + 새 입력 처리 |
| SSML | Speech Synthesis Markup Language — TTS 제어 마크업 |
| PCM | Pulse Code Modulation — 비압축 오디오 포맷 |
| opus | WebRTC 표준 오디오 코덱 (브라우저 호환) |
| FallbackSTTEngine | 주 STT 실패 시 폴백 STT로 전환하는 래퍼 클래스 |
| StreamHandle | STT 스트리밍 세션 핸들 (session_id 기반) |

## 4. 사용자 스토리

- **US-016**: As a 데모 참관자, I want 음성으로 말하면 음성으로 답하게, So that 실제 콜센터처럼 체험
- **US-017**: As a 데모 참관자, I want AI가 말하는 도중 끼어들 수 있게 (barge-in), So that 자연스러운 대화 경험
- **US-018**: As a 데모 참관자, I want 대화 내용이 텍스트로도 표시되게, So that 인식 정확도 확인 가능
- **US-019**: As a 운영자, I want 음성 서비스 불가 시 텍스트 폴백 안내, So that 장애 시에도 서비스 지속

## 5. 기능 요구사항

### FR-001: AWS Transcribe Streaming STT 엔진 구현 (P0, US-016)
- 기존 `STTEngine` ABC를 구현하는 `TranscribeSTTEngine` 클래스
- AWS Transcribe Streaming API (boto3) 사용
- 실시간 스트리밍: 청크 단위 전송 → partial result 수신 → final result
- 한국어 `ko-KR` 고정
- 입력: PCM 16kHz 16bit mono
- 레이턴시: 스트리밍이므로 발화 종료 후 ~0.5-1초 내 최종 결과 (CPU 추론 대비 대폭 개선)
- 비용: 월 1천 턴 × 평균 5초 = ~83분 → ~$1.2/mo (데모 규모)
- 대안: STTEngine ABC 교체로 faster-whisper(GPU), Google Speech-to-Text 등 전환 가능
- `stop_stream()`, `cancel()` 메서드 구현 (기존 ABC에 없으면 추가 — M-27)

### FR-002: Amazon Polly TTS 엔진 구현 (P0, US-016)
- 기존 `TTSEngine` ABC를 구현하는 `PollyTTSEngine` 클래스
- Neural 한국어 음성 (Seoyeon)
- 텍스트 → SSML 변환 → Polly API → 오디오 스트림
- 문장 단위 분할 후 스트리밍 (첫 문장 빠른 재생 시작)
- 예상 비용: Neural $16/1M 문자, 데모 규모 (월 1천 턴 × 100자 = 10만 문자) ~$1.6/mo

### FR-003: FallbackSTTEngine 래퍼 (P0)
- `vendor_factory.py`의 `create_stt_engine` 반환타입 Union 제거 (C-05)
- `FallbackSTTEngine`이 주 STT를 래핑하여 항상 `STTEngine` 반환
- 주 엔진(TranscribeSTTEngine) 실패 시: 별도 폴백 STT 없음 → FR-009 텍스트 모드로 전환
- health_check/close 위임 (M-33)
- 호출부 리팩토링 포함: Union 분기 코드 제거

### FR-004: 음성 대화 WebSocket 엔드포인트 (P0, US-016)
- 엔드포인트: `/api/v1/ws/voice`
- 오디오 포맷 흐름:
  ```
  브라우저 (opus/webm 48kHz)
    → 서버: ffmpeg 변환 → PCM 16bit 16kHz
    → AWS Transcribe Streaming STT → 텍스트
    → 텍스트 파이프라인 (기존 TurnPipeline.process())
    → Polly TTS → PCM 16bit 24kHz
    → 서버: opus 인코딩 → 브라우저
  ```
- VAD: 발화 끝 감지 (1.0초 침묵, 설정 가능 0.5~2.0초)

### FR-005: Barge-in 지원 (P1, US-017)
- TTS 재생 중 사용자 음성 감지 → TTS 스트리밍 즉시 중단 → 새 STT 시작
- WebSocket 메시지: `{"type": "interrupt"}` → TTS 스트림 중단
- 기존 `BargeInHandler` Protocol 활용
- speech_start/speech_end 이벤트 콜백 추가 (M-29)
- stop_playback()이 세션 상태를 stopped 플래그로 전환 (삭제 안 함 — M-30)

### FR-006: 음성 데모 클라이언트 (P1, US-016, US-018)
- 단일 HTML+JS 페이지
- HTTPS 필수 (브라우저 마이크 접근)
- 브라우저 마이크 (MediaRecorder, opus) → WebSocket → 서버 → 스피커 재생 (AudioContext)
- 대화 내용 텍스트 자막 표시
- TTS 스킵 버튼 (barge-in 대안)

### FR-007: DTMF 특수키 처리 (P1)
- `*`, `#` 키 매핑 추가 (M-26)
- `*` → 이전 메뉴, `#` → 입력 확인 등 콜센터 표준 매핑
- DTMF 세션 메모리 TTL 기반 자동 정리 (M-32)

### FR-008: STTEngine ABC 확장 (P0)
- `stop_stream(handle: StreamHandle) -> None` 추상 메서드 추가 (M-27)
- `cancel(handle: StreamHandle) -> None` 추상 메서드 추가
- 기존 구현체에 빈 구현 추가 (하위 호환)

### FR-009: 텍스트 폴백 (P0, US-019)
- STT 서비스 불가 시: "음성 서비스가 일시 중단되었습니다. 텍스트로 문의해주세요."
- AWS Transcribe Streaming 연결 실패/타임아웃 → 자동 텍스트 모드 전환

## 6. 비기능 요구사항

### NFR-001: 응답 시간
- 음성 턴 RTT P95 ≤ 8초
- 기대 발화 길이: 3~5초 (데모 시나리오 기준)
- 단계별 버짓: VAD 1.0s + ffmpeg 0.2s + STT ≤1.5s + LLM ≤2.5s + TTS ≤0.8s + network+encode ≤0.5s = 6.5s (1.5s 마진)

### NFR-002: 메모리
- 외부 STT/TTS API 사용으로 모델 로딩 불필요
- 전체 프로세스: ~512MB 이내 (데모 규모)

### NFR-003: 비용
- Polly Neural: ~$1.6/mo (데모 규모, 월 1천 턴 × 100자 = 10만 문자)
- Transcribe Streaming: ~$1.2/mo (월 1천 턴 × 5초 = ~83분)
- 합계: ~$2.8/mo

### NFR-004: 보안
- 음성 데이터 로그 미저장 (PCM/opus 원본 디스크 저장 금지)
- STT 결과 텍스트는 기존 PII 마스킹 파이프라인 통과

### NFR-005: 호환성
- Python 3.9+ (기존 환경 유지)
- `typing.Dict`, `typing.Optional` 사용 (Python 3.9 호환)

## 7. 기술 설계

### 아키텍처 개요
```
브라우저 (opus) ←→ WebSocket ←→ VoiceServer
                                    ↕
                              AudioConverter (ffmpeg)
                                    ↕
                              TranscribeSTTEngine ←→ AWS Transcribe Streaming
                                    ↕
                              TurnPipeline.process() (기존)
                                    ↕
                              PollyTTSEngine ←→ Amazon Polly
                                    ↕
                              AudioConverter (opus encode)
                                    ↕
                              WebSocket → 브라우저
```

### 주요 컴포넌트
| 컴포넌트 | 역할 | 신규/수정 |
|----------|------|----------|
| VoiceServer | WebSocket 엔드포인트 + 세션 관리 | 신규 |
| TranscribeSTTEngine | AWS Transcribe Streaming 래핑 STT 구현 | 신규 |
| PollyTTSEngine | Amazon Polly 래핑 TTS 구현 | 신규 |
| FallbackSTTEngine | STT 주/폴백 래퍼 | 신규 |
| AudioConverter | ffmpeg PCM 변환 + opus 인코딩 | 신규 |
| BargeInHandler | barge-in 이벤트 처리 | 수정 (M-29, M-30) |
| STTEngine ABC | stop_stream/cancel 추가 | 수정 (M-27) |
| DTMFProcessor | `*`/`#` 특수키 + TTL 정리 | 수정 (M-26, M-32) |

### 기술 스택
- boto3 (AWS Transcribe Streaming + Amazon Polly)
- FastAPI WebSocket
- ffmpeg (오디오 변환)
- opus-tools 또는 opuslib (opus 인코딩)

## 8. 데이터 모델

### 기존 모델 (수정 없음)
- `STTResult`: text, confidence, is_valid, processing_time_ms, failure_type
- `AudioStream`: 오디오 스트림 데이터 클래스
- `StreamHandle`: STT 스트리밍 세션 핸들
- `PartialResult`: 부분 인식 결과

### 신규 모델
- `VoiceSession`: WebSocket 세션 + 오디오 상태 (is_tts_playing, current_stream_handle)
- `AudioChunk`: 오디오 청크 (data: bytes, format: str, sample_rate: int)

## 9. API 설계

### WebSocket 프로토콜: `/api/v1/ws/voice`

**클라이언트 → 서버:**
```json
{"type": "audio", "data": "<base64 opus>"}
{"type": "interrupt"}
{"type": "end_session"}
```

**서버 → 클라이언트:**
```json
{"type": "transcript", "text": "요금 조회해줘", "is_final": true}
{"type": "audio", "data": "<base64 opus>"}
{"type": "response_text", "text": "이번 달 요금은 55,000원입니다."}
{"type": "error", "message": "음성 서비스가 일시 중단되었습니다."}
{"type": "session_started", "session_id": "..."}
```

## 10. UI/UX 고려사항
- 마이크 버튼: 녹음 시작/중지
- 실시간 자막: STT partial result 표시 → final result 확정
- TTS 재생 시 스피커 아이콘 애니메이션
- 스킵 버튼: TTS 즉시 중단
- 연결 상태 표시: 🟢 연결됨 / 🔴 연결 끊김

## 11. 마일스톤 및 일정

| 단계 | 기간 | 산출물 |
|------|------|--------|
| F-1: ABC 확장 + 팩토리 리팩토링 | 1~2일 | STTEngine ABC 확장, FallbackSTTEngine, DTMF 수정 |
| F-2: STT 엔진 구현 | 2~3일 | TranscribeSTTEngine + 단위 테스트 |
| F-3: TTS 엔진 구현 | 2~3일 | PollyTTSEngine + 단위 테스트 |
| F-4: WebSocket + 음성 파이프라인 | 3~4일 | VoiceServer, AudioConverter, E2E 테스트 |
| F-5: Barge-in + 데모 클라이언트 | 2~3일 | BargeInHandler 수정, HTML 데모 |

## 12. 리스크 및 완화 방안

| ID | 리스크 | 확률 | 영향 | 완화 |
|----|--------|------|------|------|
| RISK-001 | AWS Transcribe 한국어 정확도 | M | M | ABC 교체로 faster-whisper(GPU) 또는 Google STT 전환 가능 |
| RISK-002 | ffmpeg 의존성 설치 문제 | L | H | Docker에 ffmpeg 포함, 로컬은 apt/brew 안내 |
| RISK-003 | Polly Neural 한국어 Seoyeon 품질 | L | M | Standard + SSML 폴백 |
| RISK-004 | WebSocket 동시 세션 메모리 | L | M | 데모 규모 동시 1~2 세션, 메모리 모니터링 |
| RISK-005 | opus 인코딩 라이브러리 호환성 | M | M | opuslib 대신 ffmpeg 파이프라인으로 대체 가능 |

## 13. 성공 지표

| KPI | 목표값 | 측정 방법 |
|-----|--------|----------|
| 음성 턴 RTT P95 | < 8초 | VoiceServer 로그 |
| STT 한국어 WER | ≤ 20% | 30문장 테스트셋 (Transcribe 기준, 미달 시 엔진 교체) |
| Barge-in 중단 지연 | P95 < 200ms | BargeInHandler 타이밍 |
| 텍스트 폴백 전환 | < 3초 | STT 실패 → 폴백 안내 지연 |
| 데모 E2E 성공률 | ≥ 90% | 10회 데모 시나리오 |

## 14. 의존성

| 의존성 | 리스크 |
|--------|--------|
| AWS Transcribe Streaming (boto3) | Low — 이미 boto3 사용 중, IAM 권한만 추가 |
| boto3 (Polly) | Low — 이미 사용 중 |
| ffmpeg 시스템 바이너리 | Medium — 시스템 패키지 |
| opus 인코딩 라이브러리 | Medium — ffmpeg으로 대체 가능 |
| 기존 TurnPipeline (Phase C~E) | Low — 133 tests 안정 |

## 15. 범위 제외 사항
- Amazon Connect 연동
- GPU 기반 STT (faster-whisper 등 — ABC 교체로 추후 전환 가능)
- 실시간 화자 분리 (speaker diarization)
- 다국어 지원 (한국어만)
- ECS 배포 (로컬 개발 환경 우선)
- 부하 테스트 (별도 Phase)
