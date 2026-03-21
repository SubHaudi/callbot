# Callbot 코드 리뷰 종합 보고서

**일시**: 2026-03-21
**리뷰 대상**: NB3025/callbot 전체 모듈 (91 소스 파일, ~8,280줄 — 테스트 제외)
**방법**: 모듈 그룹별 5명 독립 서브에이전트 리뷰 → 합의 기반 집계
**리뷰어**: 총 35명 (7그룹 × 5명), 유효 32명 (3명 무효 — 엉뚱한 코드 리뷰)
**합의 기준**: 동일 파일 + 동일 함수 + 동일 결함 유형 = 동일 이슈. 3/5 미만은 제외.
**보고서 품질 리뷰**: 5명 평가, 평균 24.2/30

---

## 1. 리뷰 범위

| 그룹 | 모듈 | 파일수 | 줄수 | 유효 리뷰어 |
|------|------|--------|------|-------------|
| A | business + external | 18 | 1,876 | 5/5 |
| B | nlu | 6 | 1,043 | 5/5 |
| C | orchestrator + llm_engine | 10 | 1,333 | 5/5 |
| D | session | 13 | 1,487 | 4/5 |
| E | server | 8 | 637 | 4/5 |
| F | voice_io | 13 | 1,365 | 5/5 |
| G | security | 6 | 539 | 5/5 |
| **합계** | | **74** | **~8,280** | **32/35** |

### 범위 외 (의도적 제외)
- `common/`, `components/`, `config/`, `monitoring/`, `storage/`, `health/` — 보일러플레이트 또는 미구현 스텁 (총 17파일)
- `tests/` — 테스트 코드 자체의 품질 리뷰는 별도 라운드로 계획

---

## 2. CRITICAL 이슈 (만장일치 또는 4/5 이상)

### 파이프라인 통합 (Phase C 블로커)

| ID | 이슈 | 합의 | 📍 위치 | 공수 | 해결 패턴 |
|----|------|------|---------|------|-----------|
| C-01 | **pipeline.py가 핵심 모듈을 연결하지 않음** — IntentClassifier, ExternalAPIWrapper, LLMEngine, MaskingModule 미주입. `llm_service.generate()` 직접 호출 | 19/19 | `server/pipeline.py:26-80` | **L** | pipeline.py 재설계: DI로 IntentClassifier·MaskingModule·ExternalAPIWrapper 주입, process() 내부에서 순차 호출 체인 구성 |
| C-02 | **process_turn()이 intent 분류 결과를 버림** — classify() 호출하지만 반환값 무시, 항상 `context={}` | 5/5 | `orchestrator/conversation_orchestrator.py:40` | **S** | `result = self._intent_classifier.classify(...)` → `context={"intent": result}` 반환 |
| C-03 | **LLM이 API 데이터 없이 답변 생성** — api_result 전달 경로 없음 → factual intent에서 환각 100% | 5/5 | `server/pipeline.py:72-74` | **M** | pipeline PROCESS_BUSINESS 분기에서 intent→ExternalAPI 호출→api_result를 system_prompt에 삽입 후 generate() |

### 아키텍처 설계

| ID | 이슈 | 합의 | 📍 위치 | 공수 | 해결 패턴 |
|----|------|------|---------|------|-----------|
| C-04 | **ExternalSystemBase ABC 중복** — api_wrapper.py와 external_system.py에 동명 다른 인터페이스 → FakeExternalSystem 주입 시 AttributeError | 5/5 | `business/api_wrapper.py:29` vs `business/external_system.py:10` | **S** | api_wrapper.py의 ExternalSystemBase를 APIWrapperSystemBase로 rename, import 일괄 수정 |
| C-05 | **팩토리 반환 타입 Union** — `STTEngine | tuple` 반환 → 모든 호출부에서 isinstance 분기 필요 | 5/5 | `voice_io/vendor_factory.py:34` | **M** | FallbackSTTEngine 래퍼 클래스 도입, 팩토리가 항상 STTEngine 반환 |

### PII/보안 ⚠️ Phase C-sec 병행 필수

| ID | 이슈 | 합의 | 📍 위치 | 공수 | 해결 패턴 |
|----|------|------|---------|------|-----------|
| C-06 | **PII 마스킹 — 정규식 탐지 없음** — CustomerInfo 미등록 PII(고객이 직접 말한 번호) 마스킹 안 됨 → LLM 전송 | 5/5 | `nlu/masking_module.py:76-140` | **M** | `mask()` 진입 시 정규식(`\d{2,3}-\d{3,4}-\d{4}` 등) 사전 스캔 → 동적 CustomerInfo 확장 후 기존 마스킹 로직 재사용 |
| ~~C-07~~ | ~~PIF 감사로그에 마스킹 전 원문 기록~~ — **v2 리뷰에서 삭제**: masking_module.py에 로깅 코드 자체가 없음 (5/5 합의). 감사 로깅 미구현 문제는 Mi-12에서 커버. | ~~4/5~~ | — | — | — |
| C-08 | **PII 해시 salt 없음** — SHA-256 단독 → 레인보우 테이블로 주민번호/전화번호 역산 가능 | 5/5 | `security/pii_encryptor.py:97` | **S** | `hashlib.sha256` → `hmac.new(salt, pii.encode(), hashlib.sha256)`, salt는 SecretsManager에서 주입 |
| C-09 | **암호화 키 로테이션 부재** — 단일 키, 교체 시 기존 암호문 복호화 불가. ISMS-P 위반 | 5/5 | `security/pii_encryptor.py:34-50` | **M** | key_version 헤더 추가 (iv 앞 1B), `_get_key(version)` → SecretsManager에서 버전별 키 조회, decrypt 시 헤더 읽어 적합 키 사용 |
| C-10 | **HS256 대칭키 JWT** — 모든 서비스가 signing key 공유 → 사칭 가능 | 5/5 | `security/service_authenticator.py:83,106` | **M** | RS256 전환: SecretsManager에 RSA 키페어 저장, encode → private key, decode → public key, `algorithms=["RS256"]` |
| C-11 | **AAD 미사용** — AES-GCM에서 Associated Data 없음 → 암호문 컨텍스트 바인딩 없음 | 4/5 | `security/pii_encryptor.py:66,84` (`None` 인자) | **S** | `aesgcm.encrypt(iv, pt, aad=session_id.encode())` — session_id를 AAD로 바인딩 |

### 데이터 일관성

| ID | 이슈 | 합의 | 📍 위치 | 공수 | 해결 패턴 |
|----|------|------|---------|------|-----------|
| C-12 | **Redis↔PG dual-write 비원자성** — Redis 성공+PG 실패 시 불일치, 보상/롤백 없음 | 4/4 | `session/session_manager.py:40-42,79-102` | **M** | PG를 source of truth로 격상. 쓰기: PG 먼저 → 성공 시 Redis 캐시 갱신. PG 실패 시 Redis write 안 함. Redis 장애 시 PG fallback. |
| C-13 | **Session 동시요청 race condition** — read-modify-write 비보호, lost update 위험 | 4/4 | `session/redis_session_store.py:59-63` | **M** | Redis WATCH/MULTI 또는 Lua script로 CAS (Compare-And-Swap). PG 측은 `SELECT ... FOR UPDATE` |

---

## 3. MAJOR 이슈 (합의 3/5 이상)

### business + external
| ID | 이슈 | 합의 | 📍 위치 | 공수 | 해결 패턴 |
|----|------|------|---------|------|-----------|
| M-01 | CB HALF_OPEN 동시요청 무제한 | 5/5 | `business/api_wrapper.py` CB 클래스 | S | `_half_open_count` 카운터 + max 제한 |
| M-02 | PIIMasker list 내 dict 미처리 | 5/5 | `nlu/masking_module.py:76` | S | `isinstance(v, dict)` 분기 1줄 추가 |
| M-03 | FakeSystem↔Normalizer 응답형식 불일치 | 4/5 | `external/fake_system.py` | S | 반환값을 Normalizer 기대 포맷으로 통일 |
| M-04 | CB thread-safety 없음 | 4/5 | `business/api_wrapper.py` CB 클래스 | S | `threading.Lock()` 추가 |
| M-05 | 재시도/롤백 상수 혼동 | 4/5 | `business/api_wrapper.py` | S | 상수명 rename + docstring |

### nlu
| ID | 이슈 | 합의 | 📍 위치 | 공수 | 해결 패턴 |
|----|------|------|---------|------|-----------|
| M-06 | Mock confidence=0.9 고정 → FAILURE 경로 미검증 | 5/5 | `nlu/intent_classifier.py` MockClassifier | S | 파라미터화 또는 threshold 미만 테스트 추가 |
| M-07 | Intent enum DATA_USAGE/ADDON_CANCEL 없음 | 5/5 | `nlu/enums.py` | S | enum 값 2개 추가 (Phase C 비즈니스 로직 확장 시 필요) |
| M-08 | PIF 영어/유니코드 우회 미대응 | 4/5 | `nlu/prompt_injection_filter.py` | M | 유니코드 정규화(NFKC) + 영문 패턴 추가 |
| M-09 | datetime.utcnow() deprecated | 4/5 | `nlu/` 전반 | S | `datetime.now(UTC)` 일괄 치환 |
| M-10 | PIF 에스컬레이션 트리거 미구현 | 3/5 | `nlu/prompt_injection_filter.py` | M | threshold 초과 시 ESCALATE 반환 |
| M-11 | 마스킹 토큰 충돌 (동일 필드 다중 출현) | 3/5 | `nlu/masking_module.py:101` | S | 토큰에 인덱스 suffix 추가 |

### orchestrator + llm_engine
| ID | 이슈 | 합의 | 📍 위치 | 공수 | 해결 패턴 |
|----|------|------|---------|------|-----------|
| M-12 | 인증/세션제한 메서드가 process_turn에 미연결 | 4/5 | `orchestrator/conversation_orchestrator.py:28` | S | process_turn 진입부에 `check_session_limits()` 호출 추가 |
| M-13 | PromptLoader 미사용 — 하드코딩 프롬프트 | 4/5 | `server/pipeline.py:72` | M | PromptLoader DI 주입, 하드코딩 문자열 → 템플릿 로드 |
| M-14 | check_session_limits 22턴 분기 미도달 | 4/5 | `orchestrator/conversation_orchestrator.py` | S | 통합 테스트에서 22턴 시나리오 추가 |
| M-15 | 환각검증기 숫자만 체크 | 3/5 | `llm_engine/llm_engine.py` | M | 날짜/금액 포맷 + api_result 교차 검증 |
| M-16 | max_tokens 16384 vs 150자 잘림 — 토큰 낭비 | 3/5 | `llm_engine/bedrock_service.py:87` | S | max_tokens를 용도별 조정 (응답: 512, 요약: 256) |

### session
| ID | 이슈 | 합의 | 📍 위치 | 공수 | 해결 패턴 |
|----|------|------|---------|------|-----------|
| M-17 | Redis TTL 만료 시 PG fallback 없음 | 4/4 | `session/redis_session_store.py:72` | M | load() miss 시 PG 조회 → Redis 재캐싱 |
| M-18 | PG turn_count 미갱신 — 항상 0 | 3/4 | `session/session_manager.py` | S | `insert_turn` 후 `UPDATE SET turn_count = turn_count + 1` |
| M-19 | create_session PG 실패 시 고아 Redis 세션 | 3/4 | `session/session_manager.py:44-102` | S | PG 먼저 insert → 성공 시 Redis save (C-12 해결 시 함께 해결) |
| M-20 | SQL injection 위험 (update_session 동적 SET) — ⚠️ 현재 호출부는 하드코딩 키만 사용하나, 방어적 화이트리스트 필수 | 3/4 | `session/pg_connection.py:131-134` | S | 허용 컬럼 화이트리스트 검증 추가 |
| M-21 | Redis 장애 시 graceful degradation 없음 | 3/4 | `session/redis_session_store.py` 전반 | M | try/except → PG fallback + 메트릭 |

### server
| ID | 이슈 | 합의 | 📍 위치 | 공수 | 해결 패턴 |
|----|------|------|---------|------|-----------|
| M-22 | WS 에러핸들링 부재 | 4/4 | `server/` WS 엔드포인트 | S | try/except + error JSON 응답 + 로깅 |
| M-23 | lifespan 초기화 실패 처리 불명확 | 3/4 | `server/` lifespan | S | 실패 시 sys.exit(1) + 상세 로그 |
| M-24 | 입력 validation 없음 | 3/4 | `server/` 엔드포인트 | M | Pydantic 모델 도입 |
| M-25 | config 시크릿 관리/검증 부재 | 3/4 | `server/` 설정 로딩 | M | 시작 시 필수 시크릿 존재 검증 |
| M-38 | **ThreadPoolExecutor shutdown 누락** — 글로벌 executor가 lifespan shutdown에서 미정리, graceful shutdown 시 스레드 orphan + 진행중 작업 유실 | 4/5 | `server/pipeline.py:14` | S | lifespan shutdown에 `_executor.shutdown(wait=True)` 추가 |

### voice_io
| ID | 이슈 | 합의 | 📍 위치 | 공수 | 해결 패턴 |
|----|------|------|---------|------|-----------|
| M-26 | DTMF `*`/`#` 미처리 — 콜센터 필수 | 5/5 | `voice_io/` DTMF 핸들러 | S | 특수키 매핑 추가 |
| M-27 | STTEngine ABC에 stop_stream/cancel 없음 — 리소스 누수 | 4/5 | `voice_io/models.py` STTEngine ABC | S | abstractmethod 추가 |
| M-28 | 바지인 실제 오디오 중단 메커니즘 없음 | 4/5 | `voice_io/` BargeInHandler | M | TTS stop 콜백 연동 |
| M-29 | BargeInHandler에 speech_start/end 없음 | 4/5 | `voice_io/` BargeInHandler | S | 이벤트 콜백 추가 |
| M-30 | stop_playback()이 세션 상태 삭제 — 바지인 후 replay 불가 | 3/5 | `voice_io/` TTS 관련 | S | 상태를 stopped 플래그로 전환, 삭제 안 함 |
| M-31 | Transcribe SDK 불일치 (boto3 ≠ streaming SDK) | 3/5 | `voice_io/` STT 구현 | M | amazon-transcribe-streaming-sdk로 통일 |
| M-32 | DTMF 세션 메모리 누수 | 3/5 | `voice_io/` DTMF | S | TTL 기반 자동 정리 |
| M-33 | fallback 엔진 health_check/close 누락 | 3/5 | `voice_io/` fallback | S | ABC 메서드 구현 추가 |

### security
| ID | 이슈 | 합의 | 📍 위치 | 공수 | 해결 패턴 |
|----|------|------|---------|------|-----------|
| M-34 | env 백엔드 키 변환 버그 (/,- 미치환) | 4/5 | `security/secrets_manager.py:106` | S | `/` → `_`, `-` → `_` 치환 로직 수정 |
| M-35 | 캐시에 시크릿 평문 저장 | 4/5 | `security/secrets_manager.py` 캐시 | M | 메모리 내 암호화 또는 TTL 기반 무효화 |
| M-36 | InMemoryTokenStore 프로덕션 부적합 — revoke 소실 | 4/5 | `security/` token store | M | Redis 기반 TokenStore 구현 |
| M-37 | JWT aud/iss 클레임 미검증 | 3/5 | `security/service_authenticator.py:103-106` | S | decode 옵션에 `audience`, `issuer` 추가 |

---

## 4. MINOR 이슈

| ID | 이슈 | 합의 |
|----|------|------|
| Mi-01 | PIIMasker에 email/ssn 미포함 | 4/5 |
| Mi-02 | FakeSystem: QUERY_CUSTOMER/ROLLBACK 미구현 | 4/5 |
| Mi-03 | operation_mapping 한글 문자열 키 → enum 직접 사용 권장 | 3/5 |
| Mi-04 | `_stats` 메모리 누수 — TTL 없음 | 4/5 |
| Mi-05 | `assert` 사용 → `-O`로 무효화 | 3/5 |
| Mi-06 | NLUConfig 미사용 dead code | 3/5 |
| Mi-07 | ClassificationResult frozen=True 권장 | 3/5 |
| Mi-08 | ResponseSplitter 음절≠문자 명명 불일치 | 4/5 |
| Mi-09 | request_id 전파 범위 불명확 | 3/4 |
| Mi-10 | format_amount 이중 로직 | 4/5 |
| Mi-11 | VendorConfig AWS 하드코딩 — Phase E 확장 시 리팩토링 필요 | 3/5 |
| Mi-12 | 감사 로깅(Audit Trail) 부재 — PII 접근 기록 의무 미충족 | 4/5 |
| Mi-13 | PII 필드 분류체계 미정의 | 3/5 |
| Mi-14 | Session 헬퍼 메서드마다 Redis GET/SET 왕복 | 3/4 |
| Mi-15 | datetime.now() timezone-naive | 3/4 |
| Mi-16 | SessionContext 타입 힌트 느슨함 | 3/4 |

---

## 5. Phase별 영향 분석

### Phase C (비즈니스 로직) — Tier 1 필수

#### 의존관계 DAG

```
C-04 (ABC rename) ──┐
                    ├──→ C-01 (pipeline 재설계) ──→ C-02 (intent 연결)
M-07 (enum 확장) ───┘         │                         │
                              ├──→ C-03 (api_result) ───┘
                              └──→ M-12 (인증 연결)

병렬 가능: M-02, M-22, M-13 (pipeline과 무관)
```

| 순서 | 작업 | 선행 | 공수 |
|------|------|------|------|
| 1 | C-04: ExternalSystemBase ABC 통합 (rename) | 없음 | S |
| 2 | M-07: Intent/Operation enum 확장 | 없음 | S |
| 3 | C-01: pipeline.py 재설계 — DI + 호출 체인 | C-04, M-07 | L |
| 4 | C-02: intent 결과 반환 연결 | C-01 | S |
| 5 | C-03: api_result → LLM 전달 경로 | C-01 | M |
| 6 | M-12: 인증/세션제한 연결 | C-01 | S |
| ∥ | M-02: PIIMasker list 처리 | 없음 | S |
| ∥ | M-22: WS 에러핸들링 | 없음 | S |
| ∥ | M-13: PromptLoader DI | C-01 | M |

### Phase C-sec (보안 핫픽스) — Phase C와 병행 ⚠️

리뷰어 5/5 만장일치: "보안을 프로덕션까지 미루지 마라"

| 순서 | 작업 | 공수 | 완료 검증 (DoD) |
|------|------|------|-----------------|
| 1 | C-06: 정규식 PII 마스킹 | M | 전화번호/주민번호 패턴 → 마스킹 후 LLM 전달 확인 |
| 2 | C-08: PII 해시 HMAC+salt | S | 동일 PII의 해시가 salt 변경 시 달라짐 확인 |
| 3 | C-11: AAD 바인딩 | S | 다른 session_id로 decrypt 시도 → 실패 확인 |
| 4 | C-10: RS256 전환 | M | public key만으로 encode 불가 확인 |
| 5 | C-09: 키 로테이션 | M | 키 v1 암호문 → v2 키 환경에서 복호화 성공 확인 |
| 6 | M-20: SQL injection 방지 | S | 화이트리스트 외 컬럼명 → 예외 발생 확인 |
| 7 | M-37: JWT aud/iss 검증 | S | 잘못된 aud → 토큰 거부 확인 |

### Phase D (모니터링) — Tier 2
| # | 작업 | 공수 |
|---|------|------|
| 7 | M-18: PG turn_count 갱신 | S |
| 8 | M-17: Redis TTL fallback | M |
| 9 | M-24: 입력 validation | M |
| 10 | M-01: CB HALF_OPEN 제한 | S |

### Phase E (음성) — Tier 2
| # | 작업 | 공수 |
|---|------|------|
| 11 | C-05: 팩토리 Union 제거 → FallbackSTTEngine 래퍼 | M |
| 12 | M-26: DTMF `*`/`#` 처리 | S |
| 13 | M-27: STTEngine stop_stream 추가 | S |
| 14 | M-29: BargeInHandler speech events | S |
| 15 | M-31: Transcribe SDK 교체 | M |

### 프로덕션 전 필수 (Tier 3)
| # | 작업 | 공수 |
|---|------|------|
| 16 | C-12: Redis↔PG dual-write 순서 정립 (PG first) | M |
| 17 | C-13: Session 동시성 제어 (WATCH/MULTI + FOR UPDATE) | M |
| 18 | M-35: 시크릿 캐시 암호화 | M |
| 19 | M-36: Redis 기반 TokenStore | M |

---

## 6. 테스트 현황 및 누락 관점

### 테스트 커버리지
- **현재**: 183 tests 수집, 전수 통과
- **테스트 유형**: 단위 테스트 위주, 모듈 간 통합 테스트 부재
- **목표 (Phase C 완료 후)**: pipeline end-to-end 통합 테스트 최소 10 시나리오
- ⚠️ `pytest --cov` 라인 커버리지 수치는 미측정 — Phase C 착수 시 기준선 측정 권장

### 성능/부하 (미평가)
- 콜센터 동시 호 처리량 SLA 미정의
- LLM 응답 시간 예산 (RTT budget) — spec에서 8초 목표
- Redis/PG 커넥션 풀 크기 적정성 미검증
- `ThreadPoolExecutor(max_workers=20)` 근거 불명 (`server/pipeline.py:14`)

### 장애 복구 (미평가)
- Redis SPOF — 클러스터/센티널 미적용
- PG 장애 시 서비스 전체 중단 (graceful degradation 없음)
- LLM/Bedrock 장애 시 fallback 전략 없음

### 규정 컴플라이언스 (부분 평가)
- ISMS-P: 키 로테이션(C-09), 감사 로깅(Mi-12) 미충족
- 개인정보보호법: PII 마스킹(C-06), 해시 보강(C-08) 필요
- ⚠️ 의존성 보안 스캔(pip-audit 등) 미실행

---

## 7. 총평

### 강점
- **모듈 분리 우수**: ABC/Protocol 기반 추상화, factory 패턴, DI 구조 전반에 걸쳐 일관적
- **도메인 모델 풍부**: SessionContext에 plan_list_context, pending_intent 등 다단계 플로우 기반 이미 갖춤
- **기존 모듈이 Phase C 작업량을 대폭 줄여줌**: FakeExternalSystem, IntentClassifier, LLMEngine 등 구현 완료
- **한국어 특화**: 숫자 변환, PIF 한국어 패턴 등 도메인 이해도 높음

### 약점
- **pipeline.py가 핵심 병목**: 잘 만든 모듈들이 연결 안 됨 — "빈 껍데기" 상태
- **PII 보호 갭**: 통신사 환경에서 치명적 — 정규식 마스킹 미구현, 감사로그 평문, 해시 salt 없음
- **보안 모듈 규제 미달**: ISMS-P/개인정보보호법 기준 키 로테이션, 감사 로깅, PII 해시 보강 필수
- **테스트 커버리지 편향**: 단위 테스트는 있으나, 모듈 간 통합 테스트 부재

### 리스크 평가
| 항목 | 평가 |
|------|------|
| Phase C 구현 난이도 | **낮음** — 기존 모듈 연결이 핵심, 새 코드 최소 |
| Phase C-sec 난이도 | **낮~중** — 대부분 S/M, 패턴 명확 |
| Phase D/E 구현 난이도 | **중간** — voice_io ABC 변경 + 모니터링 통합 |
| 프로덕션 준비도 | **낮음** — PII/보안/동시성 이슈 해결 필요 |
| 예상 일정 (Phase C + C-sec) | **1.5~2주** |
| 예상 일정 (Phase D) | **0.5~1주** |
| 예상 일정 (Phase E) | **1~2주** |

### 이슈 통계
| 심각도 | 건수 |
|--------|------|
| CRITICAL | **12** (C-07 삭제, 원 13→12) |
| MAJOR | **38** |
| MINOR | **16** |

---

*보고서 작성: 2026-03-21 03:30 UTC*
*보고서 보강 (v2): 2026-03-21 04:15 UTC — 리뷰어 피드백 반영*
*보고서 보강 (v3): 2026-03-21 04:35 UTC — Round 1: C-07 삭제(허위 이슈), C-05/M-07 위치 수정*
*보고서 보강 (v4): 2026-03-21 04:38 UTC — Round 2: M-38 추가(ThreadPoolExecutor shutdown), M-20 주석 부기*
*리뷰 방법: 7그룹 × 5명 독립 리뷰 → 합의율 기반 집계 (3/5 이상만 포함)*
*보고서 품질 리뷰: 5명 평가, 평균 24.2/30*
