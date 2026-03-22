# VAD + 수동 종료 구현 계획

## 구현 원칙
- TDD 사이클: Red → Green → Refactor (JS 코드는 브라우저 테스트 대신 로직 분리 + 수동 검증)
- Tidy First: 구조적 변경과 행위적 변경을 분리
- 각 커밋은 구조적 또는 행위적 중 하나만 포함

## 요구사항 추적 매트릭스
| 요구사항 ID | 요구사항 요약 | 관련 태스크 |
|-------------|-------------|-------------|
| FR-001 | 클라이언트 RMS 실시간 계산 | TASK-002, TASK-003 |
| FR-002 | 무음 1500ms + 최소 음성 500ms 후 auto-stop | TASK-003, TASK-004 |
| FR-003 | 수동 종료 유지 | TASK-005 |
| FR-004 | SILENCE_THRESHOLD 상수화 | TASK-001 |
| FR-005 | 볼륨 인디케이터 | TASK-006 |
| FR-006 | Auto-stop 시각적 피드백 | TASK-007 |
| FR-007 | 녹음 시작 후 1000ms grace period | TASK-003 |
| FR-008 | 서버 변경 없음 | - (검증만) |
| NFR-001 | 순수 JS, 추가 라이브러리 없음 | 전체 |
| NFR-004 | 서버 코드 변경 없음 | - (검증만) |

## 태스크 목록

### TASK-001: VAD 상수 정의 (Structural)
- **변경 유형**: Structural
- **설명**: index.html 상단 JS에 VAD 관련 상수 추가
  ```javascript
  const SILENCE_THRESHOLD = 0.01;
  const SILENCE_DURATION = 1500;
  const VAD_GRACE_PERIOD = 1000;
  const MIN_SPEECH_DURATION = 500;
  const SMOOTHING_FACTOR = 0.3;
  ```
- **완료 기준**: 상수 선언 완료, 기존 기능 영향 없음
- **커밋 메시지**: `structural: add VAD constants`

### TASK-002: RMS 계산 로직 추가 (Behavioral)
- **변경 유형**: Behavioral
- **의존성**: TASK-001
- **설명**: `onaudioprocess` 콜백 내에서 RMS 계산 + smoothing 적용
  ```javascript
  // 각 프레임에서:
  const rms = Math.sqrt(f32.reduce((sum, v) => sum + v * v, 0) / f32.length);
  smoothedRMS = SMOOTHING_FACTOR * rms + (1 - SMOOTHING_FACTOR) * smoothedRMS;
  ```
- **테스트**: 녹음 시작 → 콘솔에 smoothedRMS 값 출력 확인 (음성 시 > 0.01, 무음 시 < 0.01)
- **관련 요구사항**: FR-001
- **완료 기준**: RMS 계산 동작, 기존 audio chunk 전송 영향 없음
- **커밋 메시지**: `behavioral: add RMS calculation in audio processing loop`

### TASK-003: VAD 코어 — silence timer + grace period + min speech (Behavioral)
- **변경 유형**: Behavioral
- **의존성**: TASK-002
- **설명**: VAD 상태 머신 구현
  - 상태 변수: `vadActive=false`, `speechStartTime=null`, `silenceStartTime=null`, `hasSpeech=false`
  - Grace period: `recordingStartTime` 기준 1000ms 이내면 VAD 무시
  - 음성 감지: `smoothedRMS > SILENCE_THRESHOLD` → `speechStartTime` 설정
  - Min speech: 음성 누적 500ms 이상이면 `hasSpeech=true`
  - Silence timer: `hasSpeech && smoothedRMS <= SILENCE_THRESHOLD` → `silenceStartTime` 설정
  - Auto-stop: `now - silenceStartTime >= SILENCE_DURATION` → `stopRecording()` 호출
  - 음성 재감지 시: `silenceStartTime = null` (타이머 리셋)
- **테스트**: 
  1. 녹음 시작 → 1초 이내 무음 → auto-stop 안 됨 (grace period)
  2. 녹음 시작 → 음성 1초 → 무음 1.5초 → auto-stop 됨
  3. 녹음 시작 → 음성 0.3초 → 무음 2초 → auto-stop 안 됨 (min speech 미달)
- **관련 요구사항**: FR-001, FR-002, FR-007
- **완료 기준**: VAD가 조건에 따라 auto-stop 트리거
- **커밋 메시지**: `behavioral: implement VAD core — silence timer, grace period, min speech guard`

### TASK-004: Auto-stop → stopRecording 연결 (Behavioral)
- **변경 유형**: Behavioral
- **의존성**: TASK-003
- **설명**: VAD auto-stop 시 `stopRecording()` 호출 + `isAutoStop=true` 플래그 설정
  - `stopRecording()` 호출 전 `isAutoStop` 플래그 설정
  - 기존 `stopRecording()` 함수는 수정 없음 — WS `end` 메시지 전송 동일
- **테스트**: 음성 후 1.5초 무음 → 자동으로 `end` 메시지 전송 + thinking dots 표시
- **관련 요구사항**: FR-002
- **완료 기준**: auto-stop이 기존 수동 종료와 동일한 WS 프로토콜 사용
- **커밋 메시지**: `behavioral: connect VAD auto-stop to stopRecording flow`

### TASK-005: 수동 종료 동작 보존 검증 (Behavioral)
- **변경 유형**: Behavioral
- **의존성**: TASK-004
- **설명**: 수동 "녹음 완료" 버튼이 여전히 정상 동작하는지 검증
  - 수동 종료 시 VAD 타이머 정리
  - 마이크 버튼 탭으로도 종료 가능 (기존 toggle 동작)
- **테스트**: 
  1. 녹음 중 "녹음 완료" 탭 → 즉시 종료 + 전송
  2. 녹음 중 마이크 버튼 탭 → 즉시 종료 + 전송
- **관련 요구사항**: FR-003
- **완료 기준**: 수동 종료 경로 2가지 모두 동작
- **커밋 메시지**: `behavioral: verify manual stop still works with VAD active`

### TASK-006: 볼륨 인디케이터 UI (Behavioral)
- **변경 유형**: Behavioral
- **의존성**: TASK-002
- **설명**: 마이크 버튼에 RMS 기반 시각적 피드백 추가
  - CSS: `--vol` custom property로 `box-shadow` 크기 조절
  - JS: `requestAnimationFrame` 루프에서 `btnMic.style.setProperty('--vol', smoothedRMS * 100)`
  - CSS: `.btn-mic.recording { box-shadow: 0 0 0 calc(4px + var(--vol, 0) * 0.3px) var(--primary-soft); }`
- **테스트**: 녹음 중 음성 → 버튼 주변 glow 확대, 무음 → 축소
- **관련 요구사항**: FR-005
- **완료 기준**: 볼륨에 따라 시각적 피드백 변화
- **커밋 메시지**: `behavioral: add volume indicator on mic button`

### TASK-007: Auto-stop 시각적 피드백 (Behavioral)
- **변경 유형**: Behavioral
- **의존성**: TASK-004
- **설명**: Auto-stop 발생 시 recording-indicator 텍스트 변경
  - silence timer 시작 시: "듣고 있어요..." → "전송 준비 중..."
  - auto-stop 시: 바로 thinking dots 표시 (기존 stopRecording 흐름)
- **테스트**: 음성 후 무음 → "전송 준비 중..." → auto-stop → thinking dots
- **관련 요구사항**: FR-006
- **완료 기준**: 상태 전환이 시각적으로 표시
- **커밋 메시지**: `behavioral: add auto-stop visual feedback in recording indicator`

### TASK-008: 서버 변경 없음 검증 (Verification)
- **변경 유형**: Verification
- **의존성**: TASK-005, TASK-006, TASK-007 (모든 변경 완료 후)
- **설명**: `git diff` 확인 — `voice_io/voice_server.py`, `server/voice_ws.py` 등 서버 파일 변경 없음
- **테스트**: `git diff --name-only` → `voice_io/demo/index.html`만 변경
- **관련 요구사항**: FR-008, NFR-004
- **완료 기준**: 서버 코드 0 diff
- **커밋 메시지**: N/A (검증만)

## 태스크 의존성 그래프
```
TASK-001 (상수)
  ├→ TASK-002 (RMS 계산)
  │    ├→ TASK-003 (VAD 코어)
  │    │    ├→ TASK-004 (auto-stop 연결)
  │    │    │    ├→ TASK-005 (수동 종료 검증)
  │    │    │    └→ TASK-007 (auto-stop 피드백)
  │    └→ TASK-006 (볼륨 인디케이터)
  └─────────────→ TASK-008 (서버 무변경 검증, TASK-005/006/007 완료 후)
```

## 테스트 전략
- **단위 테스트**: JS 로직 분리 불가 (단일 HTML) → 수동 브라우저 테스트
- **통합 테스트**: 데모 페이지에서 녹음→auto-stop→WS 전송→봇 응답 E2E
- **검증 체크리스트**:
  1. 녹음 시작 후 1초 이내 무음 → auto-stop 안 됨 ✓
  2. 음성 1초 + 무음 1.5초 → auto-stop ✓
  3. 음성 0.3초 + 무음 2초 → auto-stop 안 됨 (min speech) ✓
  4. 수동 "녹음 완료" → 즉시 종료 ✓
  5. 마이크 버튼 재탭 → 즉시 종료 ✓
  6. 볼륨 인디케이터 반응 ✓
  7. "전송 준비 중..." 표시 ✓
  8. 서버 코드 무변경 ✓
