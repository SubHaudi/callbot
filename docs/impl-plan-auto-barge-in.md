# 자동 Barge-in 구현 계획

## 구현 원칙
- TDD 사이클: Red → Green → Refactor
- Tidy First: 구조적 변경 먼저, 행위적 변경은 그 다음
- 클라이언트(HTML/JS) 전용 — 서버 코드 변경 없음
- 테스트: JS 단위 테스트는 불가(단일 HTML 파일), 대신 기존 서버 pytest 전체 통과 확인 + 수동 검증

## 요구사항 추적 매트릭스
| 요구사항 ID | 요구사항 요약 | 관련 태스크 |
|-------------|-------------|-------------|
| FR-001 | 클라이언트 VAD (RMS 에너지 분석) | TASK-01 |
| FR-002 | 자동 interrupt 전송 (sustained debounce) | TASK-02 |
| FR-003 | TTS 로컬 즉시 중단 + STT 전환 | TASK-02 |
| FR-005 | 수동 interrupt 버튼 유지 | TASK-01 (기존 유지) |
| FR-007 | 에코 억제 (echoCancellation + 임계값 상향) | TASK-03 |
| FR-006 | Barge-in 시각 피드백 | TASK-04 |
| FR-004 | Debounce 시간 조절 UI | TASK-05 |
| NFR-002 | 기존 pytest 통과 | TASK-06 |

## 태스크 목록

### TASK-01: VAD 모듈 추가 (Structural + Behavioral)
- **설명**: `index.html`에 Web Audio API 기반 VAD 클래스/함수 추가
  - `getUserMedia`에 `echoCancellation: true` constraint
  - AudioWorklet으로 RMS 에너지 계산 (폴백: ScriptProcessorNode, buffer 2048)
  - RMS 콜백: `onVoiceActivity(isActive: boolean)` 형태
  - TTS 비재생 시 VAD 결과 무시 (isPlaying 플래그 체크)
- **의존성**: 없음
- **완료 기준**: 마이크 연결 시 RMS 값이 콘솔에 출력됨. 기존 기능 영향 없음.
- **커밋**: "feat: add client-side VAD with AudioWorklet + ScriptProcessorNode fallback"

### TASK-02: 자동 barge-in 로직 (Behavioral)
- **설명**: VAD 음성 감지 → sustained debounce → 자동 interrupt 전송 + TTS 로컬 즉시 중단
  - `isPlaying === true`일 때만 동작
  - VAD가 임계값 초과 → debounce 타이머 시작
  - debounce 기간 내 RMS < 임계값 → 타이머 리셋
  - debounce 완료(기본 300ms) → `ws.send({type: "interrupt"})` + TTS 로컬 중단 + 기존 STT 파이프라인 전환
  - 기존 수동 interrupt 버튼은 그대로 유지
- **의존성**: TASK-01
- **완료 기준**: TTS 재생 중 마이크에 말하면 자동으로 TTS 중단 + interrupt 전송. 수동 버튼도 여전히 동작.
- **커밋**: "feat: auto barge-in with sustained debounce + local TTS stop"

### TASK-03: 에코 억제 강화 (Behavioral)
- **설명**: TTS 재생 중 VAD RMS 임계값을 동적으로 +10dB 상향
  - `isPlaying` 전환 시 임계값 자동 조정
  - 기본 임계값 -40dBFS → TTS 재생 중 -30dBFS
  - TTS 종료 시 -40dBFS로 복원
- **의존성**: TASK-02
- **완료 기준**: TTS 재생 중 스피커 출력만으로는 VAD가 트리거되지 않음 (에코 오탐 최소화).
- **커밋**: "feat: dynamic VAD threshold during TTS playback for echo suppression"

### TASK-04: Barge-in 시각 피드백 (Behavioral)
- **설명**: barge-in 발생 시 "듣고 있어요..." 텍스트 + 마이크 아이콘 펄스 표시
  - 자동/수동 barge-in 모두에 적용
  - TTS 중단 → 피드백 표시 → STT 처리 중 유지 → 새 응답 시 사라짐
- **의존성**: TASK-02
- **완료 기준**: barge-in 시 화면에 피드백 표시, 새 응답 시 사라짐.
- **커밋**: "feat: visual feedback on barge-in activation"

### TASK-05: Debounce 시간 조절 UI (Behavioral)
- **설명**: 설정 패널에 debounce 슬라이더 추가 (100~400ms, 기본 300ms)
  - 슬라이더 값이 실시간으로 VAD debounce에 반영
  - 현재 값 표시 (예: "300ms")
- **의존성**: TASK-02
- **완료 기준**: 슬라이더로 debounce 변경 시 즉시 반영. 범위 100~400ms.
- **커밋**: "feat: debounce time slider in settings panel"

### TASK-06: 전체 검증 (Behavioral)
- **설명**: 
  1. 서버 pytest 전체 실행 → 통과 확인 (서버 코드 미변경이므로 당연히 통과)
  2. 데모 페이지 수동 검증:
     - 자동 barge-in: TTS 재생 중 말하면 즉시 중단 (10회 중 9회 이상)
     - 에코: TTS만 재생 시 자동 중단 안 됨
     - 수동 버튼: 여전히 동작
     - 피드백: "듣고 있어요" 표시
     - 슬라이더: 100~400ms 범위 동작
  3. deploy.sh로 배포
- **의존성**: TASK-01~05 전체
- **커밋**: "chore: deploy auto barge-in feature"

## 태스크 의존성 그래프
```
TASK-01 → TASK-02 → TASK-03
                  → TASK-04
                  → TASK-05
                               → TASK-06
```

## 테스트 전략
- **서버 테스트**: 기존 pytest 전체 통과 (서버 변경 없으므로 회귀 확인만)
- **클라이언트 검증**: 수동 테스트 (단일 HTML 파일이므로 JS 단위 테스트 대신)
  - 시나리오 1: TTS 재생 중 발화 → 자동 중단 확인
  - 시나리오 2: TTS 재생 중 침묵 → 중단 없음 확인
  - 시나리오 3: 수동 버튼 클릭 → 기존대로 동작
  - 시나리오 4: debounce 슬라이더 조절 → 반응성 변화 확인
