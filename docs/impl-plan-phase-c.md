# Callbot Phase C 구현 계획 v4 — 코드 리뷰 보고서 v4 기반

## 개요
기존 모듈의 **갭만 채우고 pipeline.py를 연결**하는 것이 핵심.
코드 리뷰 보고서 v4 (CRITICAL 12, MAJOR 38, 3라운드 15명 리뷰 통과) 기반.

## Phase C 핵심 목표
1. pipeline.py 재설계 — 기존 모듈 DI 연결 (C-01, C-02, C-03)
2. ABC 중복 해소 (C-04)
3. enum 확장 + FakeSystem 확장 (M-07)
4. 다단계 플로우 구현 (요금제 변경, 부가서비스 해지)
5. PII 마스킹 통합 (C-06)
6. 보안 핫픽스 병행 (Phase C-sec)

---

## TASK-001: ExternalSystemBase ABC rename (C-04)
- **변경 유형**: Structural
- **설명**: `business/api_wrapper.py:29`의 `ExternalSystemBase`를 `APIWrapperSystemBase`로 rename. `business/external_system.py:10`의 ExternalSystemBase만 남김.
- **영향 범위**: `external/anytelecom_client.py` import 수정
- **완료 기준**: 기존 테스트 전체 통과, AttributeError 해소
- **공수**: S
- **커밋**: `structural: rename ExternalSystemBase in api_wrapper to APIWrapperSystemBase`

## TASK-002: Intent + Operation enum 확장 (M-07)
- **변경 유형**: Behavioral
- **파일**: `nlu/enums.py`, `business/enums.py`, `nlu/intent_classifier.py`
- **설명**:
  - Intent: `DATA_USAGE_INQUIRY`, `ADDON_CANCEL` 추가
  - BillingOperation: `QUERY_DATA_USAGE`, `CANCEL_ADDON` 추가
  - MockIntentClassifier: 키워드 매핑 ("데이터"→DATA_USAGE, "부가서비스 해지"→ADDON_CANCEL)
- **테스트**: Red → 새 의도 분류 테스트 작성 → Green
- **의존성**: 없음 (TASK-001과 병렬 가능)
- **공수**: S
- **커밋**: `feat: add DATA_USAGE_INQUIRY and ADDON_CANCEL intents`

## TASK-003: FakeExternalSystem 확장
- **변경 유형**: Behavioral
- **파일**: `external/fake_system.py`, `external/operation_mapping.py`, `external/response_normalizer.py`
- **설명**:
  - `call_billing_api(QUERY_DATA_USAGE)` → 잔여 데이터 더미 응답
  - `call_billing_api(CANCEL_ADDON)` → 부가서비스 해지 더미 응답
  - 예외 고객: 해지불가 부가서비스 케이스
  - Normalizer 기대 포맷에 맞춰 응답 구조 통일 (M-03 해결)
- **테스트**: Red → Green
- **의존성**: TASK-002
- **공수**: S
- **커밋**: `feat: extend FakeExternalSystem with data-usage and addon-cancel`

## TASK-004: process_turn() intent 결과 반환 (C-02)
- **변경 유형**: Behavioral
- **파일**: `orchestrator/conversation_orchestrator.py:40`
- **설명**: `classify()` 반환값을 변수에 저장, `context={"intent": result}` 반환
- **테스트**: Red → classify 결과가 context에 포함되는지 확인 → Green
- **의존성**: TASK-002 (새 Intent 포함)
- **공수**: S
- **커밋**: `feat: return intent classification result in process_turn context`

## TASK-005: 인증/세션제한 연결 (M-12)
- **변경 유형**: Behavioral
- **파일**: `orchestrator/conversation_orchestrator.py:28`
- **설명**: `process_turn()` 진입부에 `check_session_limits()` 호출 추가
- **테스트**: 22턴 초과 시나리오 → ESCALATE 반환 확인
- **의존성**: TASK-004
- **공수**: S
- **커밋**: `feat: connect session limits check to process_turn`

## TASK-006: pipeline.py 재설계 — DI + 호출 체인 (C-01, C-03)
- **변경 유형**: Behavioral
- **파일**: `server/pipeline.py`, `server/app.py`
- **설명**:
  - `__init__`에 IntentClassifier, MaskingModule, ExternalAPIWrapper 파라미터 추가
  - `PROCESS_BUSINESS` 분기 재작성:
    ```
    intent = action.context["intent"]  # C-02에서 연결됨
    → intent 기반 분기
    → ExternalAPIWrapper.call_billing_api(intent→operation)
    → LLMEngine.generate(system_prompt + api_result, masked_text)
    ```
  - `app.py` `create_app()`에서 모듈 초기화 + 주입
  - ThreadPoolExecutor → lifespan shutdown 연동 (M-38)
- **테스트**: pipeline 단위테스트 수정 + mock 기반 분기 확인
- **의존성**: TASK-001, TASK-002, TASK-003, TASK-004
- **공수**: L (핵심 TASK)
- **커밋**: `feat: wire up NLU, ExternalAPI, LLMEngine in pipeline`

## TASK-007: PIIMasker list 처리 + WS 에러핸들링 (M-02, M-22)
- **변경 유형**: Behavioral
- **파일**: `nlu/masking_module.py`, `server/` WS 엔드포인트
- **설명**:
  - M-02: `mask()`에서 list 내 dict 처리 (`isinstance(v, dict)` 분기)
  - M-22: WS 핸들러에 try/except + JSON error 응답 + 로깅
- **테스트**: Red → Green
- **의존성**: 없음 (병렬 가능)
- **공수**: S
- **커밋**: `fix: handle list[dict] in PIIMasker + WS error handling`

## TASK-008: 요금제 변경 다단계 플로우
- **변경 유형**: Behavioral
- **파일**: `server/pipeline.py`
- **설명**:
  - 기존 `SessionContext.plan_list_context`, `pending_intent` 활용
  - Turn 1: PLAN_CHANGE → QUERY_PLANS → 목록 제시
  - Turn 2: 사용자 선택 → pending_intent 저장 → 확인 요청
  - Turn 3: 확인 → CHANGE_PLAN 실행
- **테스트**: 3턴 플로우, 중간 취소, 타임아웃
- **의존성**: TASK-006
- **공수**: M
- **커밋**: `feat: implement plan-change multi-step flow`

## TASK-009: 부가서비스 해지 다단계 플로우
- **변경 유형**: Behavioral
- **파일**: `server/pipeline.py`
- **설명**: TASK-008과 유사, addon_list 활용
- **테스트**: 해지 성공, 해지불가, 중간 취소
- **의존성**: TASK-006, TASK-003
- **공수**: M
- **커밋**: `feat: implement addon-cancel multi-step flow`

## TASK-010: PII 마스킹 pipeline 통합 (C-06)
- **변경 유형**: Behavioral
- **파일**: `server/pipeline.py`, `server/logging_config.py`
- **설명**:
  - pipeline에 마스킹 포인트: LLM 전 mask() → LLM 후 restore()
  - 정규식 PII 스캔 추가: `\d{2,3}-\d{3,4}-\d{4}` (전화번호), `\d{6}-\d{7}` (주민번호)
  - 로그 출력 전 PIIMasker 적용
- **완료 검증 (DoD)**: 전화번호/주민번호 패턴 → 마스킹 후 LLM 전달 확인
- **테스트**: E2E에서 로그에 PII 미노출 확인
- **의존성**: TASK-006
- **공수**: M
- **커밋**: `feat: integrate regex PII masking into pipeline`

## TASK-011: 통합 테스트
- **변경 유형**: Behavioral
- **파일**: `server/tests/test_e2e.py`
- **설명**:
  - "내 요금 알려줘" → billing 조회 응답
  - "잔여 데이터" → data-usage 응답
  - "요금제 변경" → 3턴 다단계
  - "부가서비스 해지" → 다단계
  - CB OPEN → graceful 메시지
  - PII 마스킹 → 로그 검증
- **의존성**: TASK-008, TASK-009, TASK-010
- **공수**: M
- **커밋**: `test: add Phase C integration tests`

## TASK-012: CI 업데이트
- **변경 유형**: Structural
- **파일**: `.github/workflows/ci.yml`
- **설명**: `CALLBOT_EXTERNAL_BACKEND=fake` + Phase C 테스트 포함
- **의존성**: TASK-011
- **공수**: S
- **커밋**: `ci: update workflow for Phase C`

## TASK-013: PromptLoader DI (M-13)
- **변경 유형**: Behavioral
- **파일**: `server/pipeline.py`, `llm_engine/` (PromptLoader 클래스)
- **설명**:
  - 하드코딩 system_prompt (`"당신은 AnyTelecom 고객센터 AI..."`) → PromptLoader에서 템플릿 로드
  - PromptLoader를 pipeline DI로 주입
  - intent별 프롬프트 템플릿 지원 (billing, data_usage, addon 등)
- **테스트**: Red → 다른 intent에 다른 프롬프트 적용 확인 → Green
- **의존성**: TASK-006 (pipeline DI 구조 완성 후)
- **공수**: M
- **커밋**: `feat: replace hardcoded prompts with PromptLoader DI`

---

## Phase C-sec (보안 핫픽스) — Phase C와 병행

독립 브랜치에서 병렬 진행 가능. Phase C 의존성 없음.

### TASK-S01: PII 해시 HMAC+salt (C-08)
- **파일**: `security/pii_encryptor.py:97`
- **변경**: `hashlib.sha256` → `hmac.new(salt, pii.encode(), hashlib.sha256)`
- **salt**: SecretsManager에서 주입
- **DoD**: 동일 PII의 해시가 salt 변경 시 달라짐 확인
- **공수**: S

### TASK-S02: AAD 바인딩 (C-11)
- **파일**: `security/pii_encryptor.py:66,84`
- **변경**: `aesgcm.encrypt(iv, pt, None)` → `aesgcm.encrypt(iv, pt, session_id.encode())`
- **DoD**: 다른 session_id로 decrypt → 실패 확인
- **공수**: S

### TASK-S03: RS256 전환 (C-10)
- **파일**: `security/service_authenticator.py:83,106`
- **변경**: HS256 → RS256, SecretsManager에 RSA 키페어
- **DoD**: public key만으로 encode 불가 확인
- **공수**: M

### TASK-S04: 키 로테이션 (C-09)
- **파일**: `security/pii_encryptor.py:34-50`
- **변경**: key_version 헤더 (iv 앞 1B), `_get_key(version)` 버전별 키 조회
- **DoD**: v1 암호문 → v2 키 환경에서 복호화 성공
- **공수**: M

### TASK-S05: SQL injection 방지 (M-20)
- **파일**: `session/pg_connection.py:131`
- **변경**: 허용 컬럼 화이트리스트 검증 (`ALLOWED_COLUMNS = {"end_time", "end_reason", ...}`)
- **DoD**: 화이트리스트 외 컬럼명 → ValueError 발생
- **공수**: S

### TASK-S06: JWT aud/iss 검증 (M-37)
- **파일**: `security/service_authenticator.py:103-106`
- **변경**: `jwt.decode()` 옵션에 `audience`, `issuer` 추가
- **DoD**: 잘못된 aud → 토큰 거부
- **공수**: S

### TASK-S07: env 키 변환 버그 수정 (M-34)
- **파일**: `security/secrets_manager.py:106`
- **변경**: `.upper().replace(".", "_")` → `.upper().replace(".", "_").replace("/", "_").replace("-", "_")`
- **DoD**: `callbot/jwt-signing-key` → `CALLBOT_JWT_SIGNING_KEY`
- **공수**: S

---

## 의존관계 DAG

### Phase C (메인 트랙)
```
TASK-001 (ABC rename) ──┐
                        ├──→ TASK-003 (FakeSystem) ──┐
TASK-002 (enum 확장) ───┤                            ├──→ TASK-006 (pipeline 재설계) ──→ TASK-008 (요금제)
                        │                            │         │                          ↓
TASK-004 (intent 반환) ─┘                            │         ├──→ TASK-009 (부가서비스)
                                                     │         ├──→ TASK-010 (PII 마스킹)
                                                     │         └──→ TASK-013 (PromptLoader)
                                                     │                    ↓
                                                     │         TASK-011 (통합 테스트) → TASK-012 (CI)
                                                     │
TASK-005 (세션제한) ─── TASK-004 이후, TASK-006과 독립

병렬 가능: TASK-007 (PIIMasker list + WS 에러) — 의존성 없음
```

### Phase C-sec (병행 트랙)
```
TASK-S01 (HMAC salt) ──── 독립
TASK-S02 (AAD) ────────── 독립
TASK-S03 (RS256) ──────── 독립
TASK-S04 (키 로테이션) ── 독립
TASK-S05 (SQL 화이트리스트) ── 독립
TASK-S06 (JWT aud/iss) ── TASK-S03 이후 (같은 파일 변경, 실용적 순서)
TASK-S07 (env 키 변환) ── 독립
```

---

## 예상 일정

| 트랙 | TASK 수 | 공수 | 예상 기간 |
|------|---------|------|-----------|
| Phase C (메인) | 13 | 1L + 5M + 7S | 1~1.5주 |
| Phase C-sec (병행) | 7 | 2M + 5S | 0.5~1주 |
| **합계** | **20** | | **1.5~2주** |

---

## v2 대비 변경점
- ✅ C-02 (intent 반환) 별도 TASK-004로 분리
- ✅ C-04 (ABC rename) TASK-001로 추가 — Structural 선행
- ✅ M-12 (인증/세션제한) TASK-005로 추가
- ✅ M-38 (ThreadPoolExecutor shutdown) TASK-006에 포함
- ✅ M-22 (WS 에러핸들링) TASK-007에 포함
- ✅ Phase C-sec 7건 병행 트랙 신설
- ✅ 의존관계 DAG 보강
- ✅ DoD (완료 검증) 추가 (보안 TASK)

*작성: 2026-03-21 04:40 UTC*
*v4 수정: 2026-03-21 04:45 UTC — Round 1 리뷰 반영: TASK-013(M-13) 추가, S04 독립화, DAG 수정, M-03 명시, TASK-002 병렬화*
*기반: 코드 리뷰 보고서 v4 (3라운드 15명 리뷰 통과)*
