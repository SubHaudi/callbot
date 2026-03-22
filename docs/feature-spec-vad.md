# VAD (Voice Activity Detection) + 수동 종료 기능정의서

## 1. 개요
- 데모 웹 클라이언트에 VAD(음성 활동 감지)를 추가하여 사용자가 말을 멈추면 자동으로 녹음을 종료하고 서버에 전송
- 수동 종료 버튼도 유지하여 VAD 오탐 시 fallback 제공

## 2. 배경 및 목적
- **As-Is**: 녹음 시작 → 말하기 → 녹음 종료 버튼 탭 (2회 탭 필요)
- **To-Be**: 녹음 시작 탭 → 말하기 → 무음 감지 시 자동 종료 (1회 탭) / 수동 종료도 가능
- **비즈니스 임팩트**: 콜봇 데모의 자연스러운 음성 UX 제공. 전화 통화처럼 "그냥 말하면 되는" 경험.
- 서브에이전트 3/3 만장일치로 방향 D(VAD + 수동 종료) 결정됨

## 3. 용어 정의
| 용어 | 정의 |
|------|------|
| VAD | Voice Activity Detection — 오디오 스트림에서 음성 유무를 실시간 판별 |
| Silence Threshold | VAD가 "무음"으로 판정하는 오디오 레벨 기준값 (RMS) |
| Silence Duration | 무음이 지속되어야 자동 종료가 트리거되는 시간 (ms) |
| RMS | Root Mean Square — 오디오 신호의 크기(볼륨) 측정치 |
| Auto-stop | VAD에 의한 자동 녹음 종료 |
| Manual-stop | 사용자가 버튼을 탭하여 수동 녹음 종료 |

## 4. 사용자 스토리
- **US-001**: 사용자로서, 녹음 버튼을 한 번 탭하고 말한 후 자동으로 전송되길 원한다. 매번 종료 버튼을 누르지 않아도 되도록.
- **US-002**: 사용자로서, 긴 문장을 말할 때 중간 잠깐의 pause로 잘리지 않길 원한다. 수동 종료로 타이밍을 제어할 수 있어야 한다.
- **US-003**: 사용자로서, 녹음 중 현재 상태(VAD 감지 여부, 남은 무음 시간)를 시각적으로 확인하고 싶다.

## 5. 기능 요구사항
| ID | 설명 | 우선순위 | 관련 US |
|----|------|----------|---------|
| FR-001 | 클라이언트에서 오디오 RMS를 실시간 계산하여 음성/무음 판별 | P0 | US-001 |
| FR-002 | 무음이 SILENCE_DURATION(기본 1500ms) 이상 지속되면 자동으로 녹음 종료 및 서버 전송. 단, 음성이 최소 500ms 이상 감지된 후에만 silence timer 활성화 (짧은 pause 보호) | P0 | US-001, US-002 |
| FR-003 | 녹음 중 수동 종료 버튼 탭 시 즉시 녹음 종료 및 서버 전송 (기존 동작 유지) | P0 | US-002 |
| FR-004 | SILENCE_THRESHOLD(RMS 기준값)는 상수로 정의, 향후 조정 용이하게 | P1 | US-001 |
| FR-005 | 녹음 중 실시간 볼륨 인디케이터(VU meter) 표시 — 마이크 버튼 주변 시각적 피드백 | P1 | US-003 |
| FR-006 | Auto-stop 시 "자동 전송됨" 시각적 피드백 (system 메시지 또는 인디케이터 변화) | P1 | US-003 |
| FR-007 | 녹음 시작 후 최소 1000ms는 VAD 판정을 무시 (초기 노이즈/마이크 활성화 지연 방지) | P0 | US-001 |
| FR-008 | VAD는 클라이언트(브라우저)에서만 동작. 서버 변경 없음. | P0 | - |

## 6. 비기능 요구사항
| ID | 설명 | 측정 기준 |
|----|------|-----------|
| NFR-001 | VAD 처리는 오디오 처리 루프 내에서 수행, 추가 라이브러리 없이 순수 JS | Web Audio API RMS 계산 |
| NFR-002 | VAD 처리 오버헤드 < 1ms per frame (4096 samples) | performance.now() 측정 |
| NFR-003 | 모바일(iOS Safari, Android Chrome) + 데스크톱(Chrome) 호환 | 수동 테스트 |
| NFR-004 | 기존 서버 코드(voice_server.py, voice_ws.py) 변경 없음 | diff 확인 |

## 7. 기술 설계
### 아키텍처
- **변경 범위**: `voice_io/demo/index.html`의 JavaScript만 수정
- **서버 변경 없음** — 기존 WS 프로토콜(audio chunk → end) 그대로 사용

### VAD 알고리즘
1. ScriptProcessor의 `onaudioprocess` 콜백에서 각 프레임의 RMS 계산
2. `RMS > SILENCE_THRESHOLD` → 음성 감지 (speaking)
3. `RMS <= SILENCE_THRESHOLD` → 무음 (silence)
4. 무음 시작 시점부터 타이머 시작 (**단, 음성이 최소 500ms 이상 감지된 후에만**)
5. 무음이 `SILENCE_DURATION`ms 이상 → `stopRecording()` 호출 (auto-stop)
6. 음성 재감지 시 타이머 리셋

### 상수
```javascript
const SILENCE_THRESHOLD = 0.01;  // RMS 기준값 (조정 가능)
const SILENCE_DURATION = 1500;   // 무음 지속 시간 (ms)
const VAD_GRACE_PERIOD = 1000;   // 녹음 시작 후 VAD 무시 기간 (ms)
const MIN_SPEECH_DURATION = 500; // 최소 음성 감지 시간 (ms) — 이후에만 silence timer 활성화
```

### 볼륨 인디케이터
- 마이크 버튼에 CSS custom property(`--vol`)로 현재 RMS를 전달
- `box-shadow` 또는 `border` 크기로 볼륨 시각화
- 부드러운 감쇠: `smoothedRMS = 0.3 * currentRMS + 0.7 * prevRMS`

## 8. 데이터 모델
해당 없음 (클라이언트 전용 변경, DB/API 변경 없음)

## 9. API 설계
해당 없음 (기존 WS 프로토콜 유지: `{type: "audio", data: base64}` → `{type: "end"}`)

## 10. UI/UX 고려사항
### 녹음 흐름 변경
1. 🎤 탭 → 녹음 시작 + VAD 활성화
2. 말하기 → 볼륨 인디케이터 반응
3. 말 멈춤 → 무음 카운트다운 시작 (시각적 표시)
4. 1.5초 무음 → 자동 전송 + thinking dots
5. (또는) 수동 "녹음 완료" 버튼 → 즉시 전송

### 시각적 피드백
- 녹음 중: 마이크 버튼 주변 볼륨 링 (RMS 기반)
- 무음 감지 중: recording-indicator 텍스트 변경 ("듣고 있어요..." → "전송 준비 중...")
- Auto-stop: 부드러운 전환 (바로 thinking dots)

### 접근성
- 수동 종료 버튼 항상 표시 (VAD 의존 안 함)
- 시각적 피드백은 보조적 — 기능은 시각 없이도 동작

## 11. 마일스톤 및 일정
- **Phase 1** (이번 구현): VAD 코어 + 수동 종료 + 볼륨 인디케이터
  - 산출물: 수정된 index.html
  - 예상 기간: 1일

## 12. 리스크 및 완화 방안
| ID | 리스크 | 확률 | 영향 | 완화 |
|----|--------|------|------|------|
| RISK-001 | 시끄러운 환경에서 VAD 오탐 (무음 미감지) | M | M | SILENCE_THRESHOLD 조정 가능하게 상수화, 수동 종료 fallback |
| RISK-002 | 조용한 목소리가 음성으로 감지 안 됨 | M | H | threshold 낮춤 + 수동 종료 fallback |
| RISK-003 | ScriptProcessor deprecated (Web Audio API) | L | L | AudioWorklet 마이그레이션은 향후 고려, 현재 모든 브라우저 지원 |
| RISK-004 | iOS Safari에서 AudioContext 자동 시작 제한 | M | M | 사용자 제스처(탭) 후 AudioContext 생성 — 이미 구현됨 |

## 13. 성공 지표
| KPI | 목표값 | 측정 방법 |
|-----|--------|-----------|
| Auto-stop 정확도 | 조용한 환경에서 90% 이상 정상 동작 | 수동 테스트 10회 |
| 오탐율 (중간 pause에서 잘림) | 10% 미만 | SILENCE_DURATION(1.5초) 미만 pause 포함 문장 테스트 |
| 수동 종료 동작 | 100% (기존과 동일) | 기존 동작 회귀 테스트 |

## 14. 의존성
| 의존성 | 리스크 |
|--------|--------|
| Web Audio API (ScriptProcessor) | 낮음 — 모든 주요 브라우저 지원 |
| 기존 WS 프로토콜 | 없음 — 변경 없음 |

## 15. 범위 제외 사항
- 서버 사이드 VAD (모든 처리는 클라이언트)
- AudioWorklet 마이그레이션 (향후)
- 노이즈 캔슬링 / 고급 VAD 알고리즘 (WebRTC VAD 등)
- VAD 설정 UI (threshold/duration 사용자 조정)
