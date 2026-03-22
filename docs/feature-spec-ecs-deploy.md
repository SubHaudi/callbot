# Callbot ECS 배포 기능정의서

## 1. 개요
- Callbot 애플리케이션을 기존 Terraform 인프라(ECS Fargate + Aurora + ElastiCache)에 컨테이너로 배포
- 핵심 가치: 이미 프로비저닝된 프로덕션급 인프라를 활용하여 풀 파이프라인(음성+텍스트) 동작 달성

## 2. 배경 및 목적
- **문제**: Callbot 코드(Phase H 완료, 395 tests)가 EC2 데모 모드에서만 동작. DB/Redis 없어 Pipeline 미초기화, 텍스트 턴 불가.
- **As-Is**: EC2 t3.small 수동배포, SQLite, Redis 없음, demo mode. 음성 STT/TTS만 동작.
- **To-Be**: ECS Fargate에 컨테이너 배포, Aurora PostgreSQL + ElastiCache Redis 연결, 풀 파이프라인 동작.
- **비즈니스 임팩트**: 콜봇의 핵심 기능(대화 처리, 세션 관리, 인텐트 분류)이 실제로 동작하는 환경 확보.

## 3. 용어 정의

| 용어 | 정의 |
|------|------|
| callbot-infra-new | Terraform 인프라 레포. ECS/Aurora/Redis/WAF/Monitoring 모듈 포함 |
| callbot | 애플리케이션 코드 레포. FastAPI + VoiceServer |
| ECR | `961676526279.dkr.ecr.ap-northeast-2.amazonaws.com/callbot-dev-api` |
| Aurora | `callbot-dev-aurora.cluster-c7u6ugy62o9d.ap-northeast-2.rds.amazonaws.com` (PG 16.4, Serverless v2) |
| ElastiCache | ElastiCache Serverless Redis 7 (`callbot-dev-redis`) |
| ALB (ECS) | `callbot-dev-alb-587084408.ap-northeast-2.elb.amazonaws.com` |
| ALB (EC2) | 기존 EC2 배포용 ALB (정리 대상) |
| CloudFront (EC2) | `d2hlklbiox15zw.cloudfront.net` (CF ID: `E2TRVDNBPEL9CK`) — 기존 EC2 ALB를 origin으로 사용 |

## 4. 사용자 스토리

- **US-001**: 개발자로서, Docker 이미지를 ECR에 push하고 ECS 서비스를 업데이트하면 새 코드가 배포되어, 수동 SSH 없이 반영된다.
- **US-002**: 사용자로서, `/api/v1/turn` API로 텍스트 대화를 하면 LLM 기반 응답을 받을 수 있다 (현재 503 → 정상 응답).
- **US-003**: 운영자로서, ALB 헬스체크 + CloudWatch 로그로 서비스 상태를 모니터링할 수 있다.
- **US-004**: 개발자로서, 기존 EC2 인프라를 정리하여 이중 비용을 제거한다.

## 5. 기능 요구사항

| ID | 요구사항 | 우선순위 | US |
|----|----------|----------|----|
| FR-001 | Dockerfile 수정 및 검증 — 헬스체크 경로를 `/health`로 수정, 로컬 빌드 성공, `/health` 200 반환 | P0 | US-001 |
| FR-002 | ECR push — Docker 이미지를 `callbot-dev-api:latest`에 push | P0 | US-001 |
| FR-003 | ECS 환경변수 — Aurora endpoint, ElastiCache endpoint, Bedrock 설정이 ECS task definition에 정확히 전달 | P0 | US-002 |
| FR-004 | DB 스키마 초기화 — 서버 부팅 시 `_ensure_schema`가 Aurora에서 정상 동작 | P0 | US-002 |
| FR-005 | 풀 파이프라인 동작 — `/api/v1/turn` 호출 시 LLM 응답 반환 (503이 아닌 정상 응답) | P0 | US-002 |
| FR-006 | WebSocket 음성 — `/ws` 엔드포인트로 음성 STT→Pipeline→TTS 동작 | P1 | US-002 |
| FR-007 | ALB 헬스체크 통과 — ECS 태스크가 healthy 상태 유지, 2개 태스크 running | P0 | US-003 |
| FR-008 | CloudWatch 로그 — 컨테이너 로그가 `/ecs/callbot-dev`에 출력 | P1 | US-003 |
| FR-009 | CloudFront 전환 — 기존 CF를 ECS ALB origin으로 변경하거나, 새 도메인으로 접근 가능 | P1 | US-004 |
| FR-010 | 기존 EC2 인프라 정리 — EC2 + 구 ALB + 구 CF Terraform destroy 또는 수동 삭제 | P2 | US-004 |

## 6. 비기능 요구사항

| ID | 요구사항 | 기준 |
|----|----------|------|
| NFR-001 | 배포 소요 시간 | ECR push → ECS healthy까지 10분 이내 |
| NFR-002 | Docker 이미지 크기 | 500MB 이하 (slim base) |
| NFR-003 | ECS 태스크 리소스 | CPU 512 (0.5 vCPU), Memory 1024 MB, desired count 2 (Terraform 기존 설정) |
| NFR-004 | Aurora 연결 | SSL/TLS 연결, Secrets Manager 비밀번호 관리 |
| NFR-005 | ElastiCache 연결 | TLS 연결 (Serverless Redis 필수) |
| NFR-006 | 무중단 배포 | rolling update, deployment circuit breaker 활성 (Terraform 기존 설정) |

## 7. 기술 설계

### 아키텍처
```
사용자 → CloudFront → ALB (callbot-dev-alb) → ECS Fargate (private subnet)
                                                    ↓
                                            Aurora PostgreSQL (private subnet)
                                            ElastiCache Redis (private subnet)
                                            Bedrock (ap-northeast-2)
```

### 주요 컴포넌트
1. **Dockerfile** — 헬스체크 경로 `/health`로 수정 필요 (기존 `/health/live`)
2. **ECR** — `callbot-dev-api` 레포 (이미 존재)
3. **ECS Task Definition** — Terraform에서 `container_environment`로 환경변수 주입
4. **Aurora** — Secrets Manager로 비밀번호 관리, `DATABASE_URL` 환경변수로 전달
5. **ElastiCache** — Serverless Redis, TLS 필수

### 기술 스택
- Python 3.12, FastAPI, uvicorn
- Docker (multi-stage 불필요 — uv sync로 의존성 설치)
- AWS ECS Fargate, ECR, Aurora Serverless v2, ElastiCache Serverless

## 8. 데이터 모델
- 기존 callbot 스키마 (`_ensure_schema`에서 자동 생성)
- Aurora PostgreSQL 16.4 호환

## 9. API 설계
- 기존 API 그대로 (변경 없음)
- `GET /health` — 헬스체크
- `POST /api/v1/turn` — 텍스트 턴
- `WS /ws` — WebSocket 음성

## 10. UI/UX 고려사항
- 데모 HTML (`/demo`) — 기존 그대로, WebSocket URL만 ECS ALB로 변경될 수 있음
- wss:// 지원은 ALB HTTPS 리스너 필요 (ACM 인증서 없으면 ws:// 사용)

## 11. 마일스톤 및 일정

| Phase | 산출물 | 예상 시간 |
|-------|--------|-----------|
| 1 | Dockerfile 수정 + 로컬 빌드 검증 | 30분 |
| 2 | ECR push | 15분 |
| 3 | ECS 환경변수 확인 + 서비스 업데이트 | 30분 |
| 4 | 헬스체크 + 풀 파이프라인 동작 확인 | 30분 |
| 5 | CloudFront 전환 (선택) | 15분 |
| 6 | 기존 EC2 인프라 정리 (선택) | 30분 |

## 12. 리스크 및 완화 방안

| ID | 리스크 | 확률 | 영향 | 완화 |
|----|--------|------|------|------|
| RISK-001 | Aurora Secrets Manager 비밀번호 형식이 ServerConfig와 불일치 | M | H | ServerConfig.from_env()가 JSON 형식 지원 확인됨 |
| RISK-002 | ElastiCache TLS 연결 실패 — redis-py TLS 설정 필요 | M | H | `_init_redis`에 `ssl=True`, `ssl_cert_reqs` 설정 확인 |
| RISK-003 | Dockerfile CMD/헬스체크 경로 수정 누락 | M | M | FR-001에서 수정 태스크로 명시, TASK에서 검증 |
| RISK-004 | ECS 태스크가 Bedrock 호출 권한 없음 | L | H | Terraform task_role에 Bedrock 정책 확인 (ecs module의 IAM) |
| RISK-005 | 기존 EC2 CloudFront 삭제 시 DNS 영향 | L | M | 순차 전환: 새 ALB 먼저 확인 → CF origin 변경 → EC2 정리 |

## 13. 성공 지표

| KPI | 목표값 | 측정 방법 |
|-----|--------|-----------|
| `/health` 응답 | 200 OK | curl ALB endpoint |
| `/api/v1/turn` 응답 | 200 + 응답 텍스트 포함 | curl POST |
| ECS 태스크 상태 | 2/2 RUNNING | aws ecs describe-services |
| CloudWatch 로그 | 서버 부팅 로그 출력 | aws logs tail |

## 14. 의존성

| 의존성 | 상태 | 리스크 |
|--------|------|--------|
| callbot-infra-new Terraform | 배포 완료 ✅ | 낮음 |
| ECR 레포 | 생성됨 ✅ | 낮음 |
| Aurora Serverless v2 | 가동 중 ✅ | 낮음 |
| ElastiCache Serverless | 가동 중 ✅ | 낮음 |
| IAM 역할 (task role, execution role) | 생성됨 ✅ | 낮음 |
| claw-dev-role (ECR push 권한) | 확인 필요 | 중간 |

## 15. 범위 제외 사항
- CI/CD 파이프라인 (GitHub Actions → ECR → ECS) — 향후 구현
- 커스텀 도메인 + ACM 인증서 — 향후 구현
- ECS Exec 디버깅 설정 — 필요시 추가
- 오토스케일링 정책 튜닝 — Terraform 기본값 사용
