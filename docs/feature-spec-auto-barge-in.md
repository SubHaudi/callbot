# 자동 Barge-in 기능정의서

## 1. 개요
- 사용자가 AI 응답(TTS 재생) 중 말을 시작하면 자동으로 TTS 재생을 중단하는 기능
- 핵심 가치: 수동 인터럽트 버튼 없이도 자연스러운 대화 흐름 제공

## 2. 배경 및 목적
- **문제**: 현재 barge-in은 사용자가 데모 페이지에서 "중단" 버튼을 수동 클릭해야만 동작. 실제 전화 통화에서는 상대방이 말하는 도중 끼어들 수 있는데, 현재 구현은 이를 지원하지 않음.
- **As-Is**: 서버에 `handle_interrupt` 로직 존재 + `BargeInHandler` 프로토콜 정의됨. 클라이언트는 수동 버튼 클릭 → `{type: "interrupt"}` 메시지 전송으로만 중단 가능.
- **To-Be**: 클라이언트가 TTS 재생 중 마이크 음성 활동(VAD)을 감지하면 자동으로 interrupt 전송 → TTS 즉시 중단 → 사용자 발화 처리.
- **비즈니스 임팩트**: 대화 자연스러움 향상, 사용자 대기 시간 감소, 실제 전화 상담과 유사한 UX 제공.

## 3. 용어 정의

| 용어 | 정의 |
|------|------|
| Barge-in | TTS 재생 중 사용자가 끼어들어 응답을 중단시키는 행위 |
| VAD (Voice Activity Detection) | 오디오 스트림에서 사람 음성의 시작/종료를 감지하는 기술 |
| 자동 Barge-in | VAD 기반으로 사용자 발화를 감지하여 수동 조작 없이 자동으로 barge-in을 실행하는 기능 |
| TTS 재생 상태 | 클라이언트가 AI 응답 오디오를 재생 중인 상태 |
| Debounce 시간 | VAD가 음성 활동을 연속으로 감지한 상태를 유지해야 하는 최소 시간. 중간에 RMS가 임계값 아래로 떨어지면 타이머 리셋. (sustained detection) |
| RMS 임계값 | 음성 활동으로 판단하는 최소 오디오 에너지 수준 (dBFS 단위) |

## 4. 사용자 스토리

- **US-001**: 고객으로서, AI가 답변하는 도중 궁금한 점이 있으면 바로 말을 걸어 끊고 싶다
- **US-002**: 고객으로서, 기침/한숨 같은 비의도적 소리에는 AI가 중단되지 않았으면 좋겠다 (에너지 기반 감지의 한계로 일부 오탐 허용)
- **US-003**: 고객으로서, barge-in 후 AI가 내 말을 바로 듣고 응답해줬으면 좋겠다 (barge-in → TTS 중단 → 기존 STT 파이프라인으로 자동 전환)

## 5. 기능 요구사항

| ID | 요구사항 | 우선순위 | 관련 US |
|----|---------|---------|---------|
| FR-001 | 클라이언트 VAD: TTS 재생 중 마이크 오디오의 RMS 에너지를 분석하여 음성 활동 추정 (에너지 기반, 음성/비음성 구분 불가) | P0 | US-001 |
| FR-002 | 자동 interrupt 전송: VAD가 음성을 연속 감지하고 debounce 시간(기본 300ms) 동안 지속되면 자동으로 `{type: "interrupt"}` 메시지 전송 | P0 | US-001, US-002 |
| FR-003 | TTS 즉시 중단: interrupt 전송과 동시에 클라이언트가 TTS 재생을 로컬에서 즉시 멈추고 마이크 입력 모드(기존 STT 파이프라인)로 전환. 서버 interrupted 응답은 후속 확인용. | P0 | US-001, US-003 |
| FR-004 | Debounce 시간 조절: debounce 시간을 사용자가 설정 가능하게 (기본 300ms, 범위 100~400ms) | P1 | US-002 |
| FR-005 | 수동 interrupt 버튼 유지: 기존 수동 중단 버튼은 그대로 유지 (폴백) | P0 | - |
| FR-006 | Barge-in 시각 피드백: barge-in 발생 시 사용자에게 시각적으로 알림 ("듣고 있어요..." 표시) | P1 | US-003 |
| FR-007 | 에코 억제: 마이크 스트림에 `echoCancellation: true` constraint 적용 + TTS 재생 중 VAD RMS 임계값을 동적으로 +10dB 상향하여 에코 오탐 최소화 | P0 | US-002 |

## 6. 비기능 요구사항

| ID | 요구사항 | 기준 |
|----|---------|------|
| NFR-001 | VAD 감지 → interrupt 전송까지 지연 | 기본 설정(300ms) 기준, debounce 포함 500ms 이내 |
| NFR-002 | 기존 테스트 호환성 | 기능적 회귀 테스트 전부 통과 (서버 코드 변경 없으므로 기존 pytest 그대로) |
| NFR-003 | 브라우저 호환성 | Chrome 64+, Safari 14.1+, Firefox 76+ |

## 7. 기술 설계

### 아키텍처
- **변경 범위**: 클라이언트(데모 페이지) 전용. 서버 코드 변경 없음.
- 서버의 `handle_interrupt`와 `{type: "interrupt"}` 프로토콜은 이미 구현되어 있으므로, 클라이언트에서 VAD 감지 → 자동 interrupt 전송만 추가.

### 변경 대상 파일
1. `voice_io/demo/index.html` — VAD 로직 추가, 에코 억제, 자동 interrupt 전송, 시각 피드백

### VAD 구현 방식
- Web Audio API의 `AudioWorklet`을 사용하여 마이크 오디오의 RMS 에너지를 실시간 분석.
- 폴백: `ScriptProcessorNode` (deprecated이나 구버전 브라우저 대응. buffer size 2048 → ~46ms @44.1kHz 지연).
- RMS 에너지가 임계값을 초과하면 음성 활동으로 추정.
- TTS 재생 상태일 때만 VAD 결과를 interrupt로 연결 (비재생 중에는 무시).

### 에코 억제 전략
1. `getUserMedia` 시 `echoCancellation: true` constraint 적용 (브라우저 내장 AEC 활용)
2. TTS 재생 중 VAD RMS 임계값을 기본값 대비 +10dB 상향 (에코 에너지 필터링)
3. 위 두 가지는 "기본 에코 억제"로, 범위 제외의 "고급 AEC"와는 구분됨

### 자동 Barge-in 흐름
1. TTS 재생 시작 → `isPlaying = true`, VAD 임계값 +10dB 상향
2. VAD가 음성 감지 → debounce 타이머 시작
3. debounce 기간 내 RMS가 임계값 아래로 떨어지면 → 타이머 리셋 (sustained detection)
4. debounce 기간(기본 300ms) 동안 연속 감지 유지 → `{type: "interrupt"}` 자동 전송 + TTS 로컬 즉시 중단
5. 서버 → `{type: "interrupted"}` 응답 (후속 확인)
6. 클라이언트: "듣고 있어요" 피드백 표시 + 기존 STT 파이프라인으로 전환 (마이크 입력 → 서버 전송)

### VAD 파라미터
| 파라미터 | 기본값 | 범위 | 설명 |
|---------|--------|------|------|
| RMS 임계값 | -40 dBFS | 고정 (향후 조절 가능성 검토) | 음성 활동으로 판단하는 최소 에너지 |
| TTS 재생 중 임계값 보정 | +10 dB | 고정 | 에코 억제용 동적 상향 |
| Debounce 시간 | 300ms | 100~400ms | 연속 감지 유지 시간 |

## 8. 데이터 모델
- 변경 없음 (클라이언트 전용)

## 9. API 설계
- 변경 없음 (기존 `{type: "interrupt"}` / `{type: "interrupted"}` 프로토콜 그대로 사용)

## 10. UI/UX 고려사항
- TTS 재생 중 VAD가 음성을 감지하면 화면에 "듣고 있어요..." 텍스트 + 마이크 아이콘 펄스 표시
- 기존 수동 "중단" 버튼은 유지
- Debounce 시간 슬라이더 (설정 패널에 추가, P1)

## 11. 마일스톤 및 일정

| Phase | 내용 | 포함 FR | 예상 기간 |
|-------|------|---------|----------|
| 1 | VAD 로직 + 에코 억제 + 자동 interrupt + TTS 즉시 중단 | FR-001, FR-002, FR-003, FR-005, FR-007 | 60분 |
| 2 | 시각 피드백 + debounce 조절 UI | FR-004, FR-006 | 30분 |

## 12. 리스크 및 완화 방안

| ID | 리스크 | 확률 | 영향 | 완화 |
|----|--------|------|------|------|
| RISK-001 | 스피커 출력이 마이크에 피드백되어 자체 barge-in 발생 (에코) | M | M | FR-007: echoCancellation constraint + TTS 중 VAD 임계값 +10dB 상향. 잔존 리스크는 수용. |
| RISK-002 | 환경 소음(키보드, 기침)이 VAD를 트리거 | M | M | RMS 임계값 + sustained debounce로 필터링. RMS 기반 한계 인정, 향후 WebRTC VAD 검토. |
| RISK-003 | AudioWorklet 미지원 브라우저 | L | M | ScriptProcessorNode 폴백 구현 |

## 13. 성공 지표

| KPI | 목표 | 측정 방법 |
|-----|------|----------|
| 자동 barge-in 동작률 | ≥ 90% (10회 중 9회 이상 정상 중단) | 수동 테스트: TTS 재생 중 의도적 발화 |
| 오탐률 | ≤ 20% (비발화 상황 5회 중 1회 이하 오인식) | 수동 테스트: 침묵/배경소음 노출 |
| 기존 테스트 통과율 | 100% | pytest 전체 실행 |

## 14. 의존성
- Web Audio API (브라우저 내장)
- 기존 서버 `handle_interrupt` + WebSocket 프로토콜
- 기존 STT 파이프라인 (barge-in 후 마이크 입력 전환용)

## 15. 범위 제외 사항
- 서버 측 VAD (현재 클라이언트 VAD만 구현)
- 고급 AEC 알고리즘 (reference signal subtraction 등) — 기본 에코 억제(echoCancellation constraint + 임계값 상향)는 범위 내
- 모바일 브라우저 최적화 — Phase O에서 별도 처리
- RMS 임계값 사용자 조절 — 향후 확장 가능성 검토
