# 시스템 프롬프트 음성 최적화 구현 계획 (v2)

## 구현 원칙
- TDD 사이클: Red → Green → Refactor
- Tidy First: 구조적 변경 먼저, 행위적 변경은 그 다음
- 각 커밋은 구조적 또는 행위적 중 하나만 포함

## 요구사항 추적 매트릭스
| 요구사항 ID | 요구사항 요약 | 관련 태스크 |
|-------------|-------------|-------------|
| FR-001 | 베이스 프롬프트에 음성 지침 추가 | TASK-03, TASK-04 |
| FR-002 | 인텐트별 프롬프트 응답 형식 가이드 | TASK-05, TASK-06 |
| FR-003 | 프롬프트 이중 구조 통합 | TASK-01, TASK-02 |
| FR-004 | 응답 글자 수 150→80 축소 | TASK-07, TASK-08 |
| NFR-001 | 기능적 회귀 테스트 통과 | 전 Green 태스크 + TASK-09 |

## 태스크 순서 (Tidy First: 구조 → 행위)

### TASK-01: 프롬프트 이중 구조 통합 (Structural)
- `llm_engine.py`의 `_build_system_prompt()` 하드코딩 제거 → `PromptLoader` 호출로 변경
- `prompt_loader.py`를 single source of truth로 통합
- 테스트 assertion을 키워드 포함 방식으로 변경 (test_prompt_loader.py + test_llm_engine.py 모두)
- **의존성**: 없음
- **완료 기준**: 모든 기존 테스트 통과, 프롬프트 소스 단일화, 동작 변경 없음
- **커밋**: "structural: unify prompt sources into PromptLoader"

### TASK-02: 통합 정합성 테스트 (Structural)
- `test_llm_engine_uses_prompt_loader()` — LLMEngine이 PromptLoader에서 프롬프트를 가져오는지 검증
- **의존성**: TASK-01
- **커밋**: "structural: verify LLMEngine uses unified PromptLoader"

### TASK-03: 베이스 프롬프트 음성 지침 — Red (Behavioral)
- `test_base_prompt_contains_voice_guidelines()` — "간결"/"1~2문장" 포함, "마크다운 금지" 등 지침 문구 포함 확인
- **의존성**: TASK-02
- **커밋**: "behavioral: red — test base prompt voice guidelines"

### TASK-04: 베이스 프롬프트 음성 지침 — Green (Behavioral)
- `prompt_loader.py`의 `_BASE_SYSTEM_PROMPT`에만 음성 지침 추가 (single source of truth)
- 간결(1~2문장), 구어체, 핵심 우선, 마크다운 서식 금지
- **의존성**: TASK-03
- **완료 기준**: TASK-03 테스트 + 기존 테스트 모두 통과
- **커밋**: "behavioral: green — add voice channel guidelines to base prompt"

### TASK-05: 인텐트별 프롬프트 — Red (Behavioral)
- `test_intent_prompts_have_required_fields()` — BILLING_INQUIRY에 "금액", DATA_USAGE에 "잔여" 등 필수 필드 키워드 확인
- **의존성**: TASK-02 (TASK-04와 병렬 가능하지만 직렬 진행)
- **커밋**: "behavioral: red — test intent-specific voice format guides"

### TASK-06: 인텐트별 프롬프트 — Green (Behavioral)
- `_INTENT_PROMPTS` 재작성. 음성 응답 형식 가이드 + 필수 포함 정보 + 구어체. 80자 이내 응답 가능하도록 설계.
- **의존성**: TASK-05
- **커밋**: "behavioral: green — optimize intent prompts for voice channel"

### TASK-07: 응답 글자 수 기본값 — Red (Behavioral)
- `test_llm_engine.py`: `assert len(result.text) <= 150` → `<= 80`
- `test_integration.py`: `config.max_syllables == 150` → `== 80`
- **의존성**: TASK-06
- **커밋**: "behavioral: red — update max syllables assertion 150→80"

### TASK-08: 응답 글자 수 기본값 — Green (Behavioral)
- `_MAX_SYLLABLES_DEFAULT = 150` → `80`
- **의존성**: TASK-07
- **커밋**: "behavioral: green — reduce _MAX_SYLLABLES_DEFAULT 150→80"

### TASK-09: 전체 테스트 + 최종 검증 (Behavioral)
- pytest 전체 실행, 실패 시 수정
- 5개 주요 인텐트 프롬프트가 80자 이내 응답 가능한지 확인
- **의존성**: TASK-08
- **커밋**: "behavioral: fix remaining test assertions for voice-optimized prompts"

## 의존성 그래프
```
TASK-01 → TASK-02 → TASK-03 → TASK-04 → TASK-05 → TASK-06 → TASK-07 → TASK-08 → TASK-09
```

## 리뷰 반영 사항 (v1 → v2)
- TASK-007(구조 통합)을 최선두로 이동 → Tidy First 원칙 준수
- TASK-004에서 llm_engine.py 중복 추가 제거 → prompt_loader.py 한 곳만
- TASK-001 범위 확대: test_prompt_loader.py + test_llm_engine.py 프롬프트 assertion 모두 커버
- TASK-002(정보 수집)를 TASK-07에 통합
- TASK-008(정합성 테스트)를 Structural로 재분류
- NFR-001을 전 Green 태스크에 적용 (매 Green 후 기존 테스트 통과 확인)
