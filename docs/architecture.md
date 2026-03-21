# Callbot 모듈별 아키텍처

## 전체 구조 (10개 모듈, 75 소스 파일, 68 테스트)

```
┌─────────────────────────────────────────────────────────────┐
│                     server/ (FastAPI)                        │
│  app.py → routes.py (REST) + ws.py (WebSocket)              │
│  pipeline.py (TurnPipeline) → 아래 모듈 조합                │
│  middleware.py (RequestID) + logging_config.py (JSON)        │
└────────┬────────────────────────────────────────────────────┘
         │
    ┌────▼────┐     ┌──────────────┐     ┌───────────────┐
    │   nlu/  │────▶│ orchestrator/│────▶│  llm_engine/  │
    │         │     │              │     │               │
    │ PIF     │     │ Conversation │     │ LLMEngine     │
    │ Intent  │     │ Orchestrator │     │ BedrockService│
    │ Masking │     │ (분기/제어)  │     │ Hallucination │
    └─────────┘     └──────┬───────┘     │ PromptLoader  │
                           │             └───────────────┘
                    ┌──────▼───────┐
                    │  business/   │
                    │              │
                    │ APIWrapper   │ ◀── CircuitBreaker
                    │ AuthModule   │
                    │ RoutingEngine│
                    │ Callback     │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  external/   │
                    │              │
                    │ Factory      │ → FakeExternalSystem (더미)
                    │              │ → AnyTelecomSystem (실제)
                    │ PIIMasker    │
                    │ OpMapping    │
                    │ ResponseNorm │
                    └──────────────┘

    ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
    │  session/    │     │  security/   │     │  voice_io/   │
    │              │     │              │     │              │
    │ SessionMgr   │     │ PIIEncryptor │     │ STTEngine    │
    │ Redis Store  │     │ SecretsMgr   │     │ TTSEngine    │
    │ PG Store     │     │ ServiceAuth  │     │ BargeIn      │
    │ Repository   │     │ TokenStore   │     │ DTMF         │
    └──────────────┘     └──────────────┘     │ VendorAdapter│
                                              └──────────────┘
    ┌──────────────┐
    │  health/     │
    │ router.py    │ → GET /health
    └──────────────┘
```

---

## 모듈별 상세

### 1. server/ (8파일, 637줄)
**역할**: FastAPI 진입점. HTTP/WS 요청 → TurnPipeline → 응답

| 파일 | 핵심 | 상태 |
|------|------|------|
| `app.py` | `create_app()` — PG/Redis/Bedrock 초기화, lifespan | ✅ 완성 |
| `config.py` | `ServerConfig.from_env()` — DATABASE_URL, REDIS_URL 등 | ✅ 완성 |
| `pipeline.py` | `TurnPipeline.process()` — PIF→Orchestrator→LLM 분기 | ⚠️ **PROCESS_BUSINESS에서 단순 generate()만 호출** |
| `routes.py` | `POST /api/v1/turn` | ✅ 완성 |
| `ws.py` | `WebSocket /api/v1/ws` | ✅ 완성 |
| `middleware.py` | `RequestIDMiddleware` | ✅ 완성 |
| `logging_config.py` | `JsonFormatter` + `setup_logging()` | ✅ 완성 |

### 2. nlu/ (6파일, 1043줄)
**역할**: 사용자 발화 → 의도 분류 + PII 마스킹 + 프롬프트 인젝션 필터링

| 파일 | 핵심 | 상태 |
|------|------|------|
| `enums.py` | `Intent` (13개 의도), `EntityType` | ✅ 완성 |
| `intent_classifier.py` | `IntentClassifier` — Mock(키워드) + BERT(추상) | ✅ 완성 |
| `masking_module.py` | `MaskingModule.mask()/restore()` — LLM 전/후 PII 처리 | ✅ 완성 |
| `prompt_injection_filter.py` | `PromptInjectionFilter.filter()` — PIF | ✅ 완성 |
| `models.py` | `FilterResult`, `ClassificationResult`, `MaskedText` | ✅ 완성 |
| `config.py` | `NLUConfig` | ✅ 완성 |

**주목**: `Intent` enum에 `BILLING_INQUIRY`, `PAYMENT_CHECK`, `PLAN_CHANGE` 등 이미 있음. 다만 `DATA_USAGE_INQUIRY`, `ADDON_CANCEL`은 **없음**.

### 3. orchestrator/ (5파일, 631줄)
**역할**: PIF 결과 기반 분기 — 정상→비즈니스, 인젝션→재질문/에스컬레이션

| 파일 | 핵심 | 상태 |
|------|------|------|
| `conversation_orchestrator.py` | `process_turn()`, `handle_system_control()`, `check_session_limits()`, `trigger_escalation()`, `determine_auth_requirement()`, `handle_no_response()`, `process_dtmf_input()`, `conduct_satisfaction_survey()` | ✅ 완성 |
| `enums.py` | `ActionType` (PROCESS_BUSINESS, SYSTEM_CONTROL, ESCALATE, AUTH_REQUIRED, SURVEY) | ✅ 완성 |
| `models.py` | `OrchestratorAction`, `SystemControlResult`, `SessionLimitAction` | ✅ 완성 |
| `health_checker.py` | 시스템 헬스체크 | ✅ 완성 |

### 4. llm_engine/ (5파일, 702줄)
**역할**: LLM 응답 생성 — 프롬프트 구성, 후처리, 음성 최적화

| 파일 | 핵심 | 상태 |
|------|------|------|
| `llm_engine.py` | `LLMEngine.generate_response()`, `generate_plan_list_response()`, `generate_change_confirmation()`, `ResponseSplitter`, `PromptLoader` | ✅ 완성 |
| `bedrock_service.py` | `BedrockLLMService(LLMServiceBase)` — boto3 Bedrock 호출 | ✅ 완성 |
| `hallucination_verifier.py` | 환각 검증 | ✅ 완성 |
| `models.py` | `LLMResponse` | ✅ 완성 |
| `enums.py` | `ScopeType` | ✅ 완성 |

**주목**: `LLMServiceBase.generate(system_prompt, user_message)` — function calling 미지원. 현재 단순 텍스트 생성만.

### 5. business/ (10파일, 1257줄)
**역할**: 비즈니스 로직 — API 래핑, 인증, 라우팅, 콜백

| 파일 | 핵심 | 상태 |
|------|------|------|
| `api_wrapper.py` | `ExternalAPIWrapper` + `CircuitBreaker` (CLOSED/OPEN/HALF_OPEN, threshold/reset) | ✅ 완성 |
| `external_system.py` | `ExternalSystemBase` ABC — `call_billing_api()`, `call_customer_db()` | ✅ 완성 |
| `auth_module.py` | `AuthenticationModule` — 본인인증 (생년월일/비밀번호) | ✅ 완성 |
| `routing_engine.py` | `RoutingEngine` — 의도→상담사그룹, 영업시간 판단 | ✅ 완성 |
| `callback_scheduler.py` | `CallbackScheduler` — 콜백 예약 | ✅ 완성 |
| `enums.py` | `BillingOperation` (5개), `CustomerDBOperation` (3개), `CircuitStatus` | ✅ 완성 |
| `models.py` | `APIResult`, `RollbackResult`, `RoutingResult` 등 14개 dataclass | ✅ 완성 |

**주목**: `BillingOperation`에 `QUERY_BILLING`, `QUERY_PAYMENT`, `QUERY_PLANS`, `CHANGE_PLAN`, `ROLLBACK_PLAN_CHANGE` 이미 있음.

### 6. external/ (8파일, 619줄)
**역할**: 외부 시스템 연동 — 실제 API vs 더미

| 파일 | 핵심 | 상태 |
|------|------|------|
| `factory.py` | `create_external_system()` — `CALLBOT_EXTERNAL_BACKEND=fake\|anytelecom` | ✅ 완성 |
| `fake_system.py` | `FakeExternalSystem` — 하드코딩 더미 응답 (요금, 납부, 요금제 목록, 변경) | ✅ 완성 |
| `anytelecom_system.py` | `AnyTelecomExternalSystem` — 실제 API | ✅ 완성 |
| `anytelecom_client.py` | `AnyTelecomHTTPClient` — mTLS HTTP | ✅ 완성 |
| `pii_masker.py` | `PIIMasker.mask()` — dict 필드 기반 | ✅ 완성 |
| `operation_mapping.py` | `OperationMapping` — (system, operation) → HTTP 매핑 | ✅ 완성 |
| `response_normalizer.py` | `ResponseNormalizer` — API 응답 정규화 | ✅ 완성 |
| `mtls_provider.py` | mTLS 인증서 관리 | ✅ 완성 |

### 7. session/ (13파일, 1487줄)
**역할**: 세션 관리 — PG 영속화 + Redis 캐시

| 파일 | 핵심 | 상태 |
|------|------|------|
| `session_manager.py` | `SessionManager` — 세션 CRUD, 턴 업데이트, 제한 확인, billing 캐시, plan_list context | ✅ 완성 |
| `redis_session_store.py` | `RedisSessionStore` — Redis 기반 | ✅ 완성 |
| `pg_connection.py` | `PostgreSQLConnection` — 커넥션 풀 | ✅ 완성 |
| `repository.py` | `CallbotDBRepository` — DB CRUD | ✅ 완성 |
| `models.py` | `SessionContext` (plan_list_context, cached_billing_data 포함), `ConversationSession`, `Turn` | ✅ 완성 |

**주목**: `SessionContext`에 `plan_list_context`, `cached_billing_data`, `pending_intent` 이미 있음 — 다단계 플로우 지원 기반.

### 8. security/ (6파일, 539줄)
**역할**: PII 암호화/토큰화, Secrets Manager, JWT 서비스 인증

✅ 전부 완성.

### 9. voice_io/ (13파일, 1365줄)
**역할**: 음성 입출력 — STT/TTS 추상화, 벤더 어댑터, 바지인, DTMF

| 파일 | 핵심 | 상태 |
|------|------|------|
| `stt_engine.py` | `STTEngine` ABC — `start_stream()`, `process_audio_chunk()`, `get_final_result()`, VAD 설정 | ✅ 완성 |
| `tts_engine.py` | `TTSEngine` ABC — `synthesize()`, `stop_playback()`, `set_speed()`, 한국어 숫자 변환 | ✅ 완성 |
| `barge_in.py` | `BargeInHandler` Protocol | ✅ 완성 |
| `stt_vendor_adapter.py` | `STTVendorAdapter(STTEngine)` — 벤더 통합 | ✅ 완성 |
| `tts_vendor_adapter.py` | `TTSVendorAdapter(TTSEngine)` — 벤더 통합 | ✅ 완성 |
| `vendor_factory.py` | `create_stt_engine()`, `create_tts_engine()` | ✅ 완성 |
| `dtmf_processor.py` | `DTMFProcessor` — DTMF 입력 처리 | ✅ 완성 |
| `vendor_config.py` | `VendorConfig.from_env()` | ✅ 완성 |

### 10. health/ (1파일, 115줄)
`GET /health` 엔드포인트. ✅ 완성.

---

## 갭 분석 (Phase C에 필요한 것 vs 이미 있는 것)

### 이미 있음 ✅
1. **더미 API** → `external/fake_system.py` (요금조회, 납부확인, 요금제목록, 요금제변경)
2. **CircuitBreaker** → `business/api_wrapper.py` (CLOSED/OPEN/HALF_OPEN 완전 구현)
3. **의도 분류** → `nlu/intent_classifier.py` (키워드 기반 MockIntentClassifier)
4. **의도 enum** → `nlu/enums.py` (BILLING_INQUIRY, PAYMENT_CHECK, PLAN_CHANGE 등)
5. **PII 마스킹** → `external/pii_masker.py` + `nlu/masking_module.py`
6. **PII 암호화** → `security/pii_encryptor.py`
7. **세션 관리** → `session/session_manager.py` (Redis+PG, plan_list_context 포함)
8. **LLM 엔진** → `llm_engine/llm_engine.py` (generate_response, plan_list, change_confirmation)
9. **요금제 변경 플로우** → `llm_engine`의 `generate_plan_list_response()`, `generate_change_confirmation()`
10. **프롬프트 인젝션 필터** → `nlu/prompt_injection_filter.py`
11. **인증 모듈** → `business/auth_module.py`
12. **라우팅** → `business/routing_engine.py`
13. **로깅** → `server/logging_config.py` (JsonFormatter)
14. **STT/TTS/Barge-in** → `voice_io/` 전체
15. **외부 시스템 팩토리** → `external/factory.py` (fake/anytelecom 전환)

### 없거나 부족 ❌
1. **pipeline.py 글루**: `PROCESS_BUSINESS` 분기가 기존 모듈(NLU→ExternalAPI→LLMEngine)을 연결 안 함
2. **Function calling**: `LLMServiceBase.generate()`가 단순 텍스트만 — tool_use 미지원
3. **잔여 데이터 조회**: `BillingOperation`에 DATA_USAGE 없음, `FakeExternalSystem`에도 없음
4. **부가서비스 해지**: `BillingOperation`에 ADDON_CANCEL 없음
5. **다단계 플로우 상태머신**: `SessionContext`에 plan_list_context는 있지만, 범용 flow_state (상태 전이) 없음
6. **CloudWatch 메트릭 발행**: `monitoring/` 모듈 비어있음
7. **Docker Compose에 mock_api**: 현재 fake_system은 인프로세스 — 별도 서비스 아님

### 설계 판단 필요 🤔
1. **FakeExternalSystem을 그대로 쓸지 vs mock_api HTTP 서버를 별도로 만들지**
   - 현재: `CALLBOT_EXTERNAL_BACKEND=fake` → 인프로세스 더미
   - Phase C: 이미 잘 동작하므로 **FakeExternalSystem 확장이 합리적** (HTTP 서버 불필요)
2. **Function calling 도입 vs 기존 IntentClassifier + LLMEngine 파이프라인 유지**
   - 기존: IntentClassifier(키워드) → Orchestrator → LLMEngine.generate_response()
   - 이미 완성된 파이프라인이므로 **기존 구조 유지 + 확장이 합리적**
3. **PII 마스킹 통합**: 이미 두 곳에 구현 — nlu/masking_module (LLM 전/후) + external/pii_masker (로그)
