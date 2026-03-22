# Callbot ECS 배포 구현 계획

## 구현 원칙
- 인프라 배포 작업이므로 TDD는 검증 가능한 단계에만 적용
- 각 TASK는 독립적으로 검증 가능한 단위
- 실패 시 롤백 가능한 순서로 진행

## 요구사항 추적 매트릭스

| 요구사항 ID | 요구사항 요약 | 관련 태스크 |
|-------------|-------------|-------------|
| FR-001 | Dockerfile 수정 및 검증 | TASK-001, TASK-003 |
| FR-002 | ECR push | TASK-003 |
| FR-003 | ECS 환경변수 | TASK-002 |
| FR-004 | DB 스키마 초기화 | TASK-004 |
| FR-005 | 풀 파이프라인 동작 | TASK-005 |
| FR-006 | WebSocket 음성 | TASK-005 |
| FR-007 | ALB 헬스체크 + 2 태스크 | TASK-004 |
| FR-008 | CloudWatch 로그 | TASK-004 |
| FR-009 | CloudFront 전환 | TASK-006 |
| FR-010 | EC2 인프라 정리 | TASK-007 |
| NFR-001 | 배포 10분 이내 | TASK-003~005 |
| NFR-002 | 이미지 500MB 이하 | TASK-003 |
| NFR-003 | ECS 태스크 리소스 (CPU 512, Mem 1024, desired 2) | Terraform 기존 설정, TASK-005 검증 |
| NFR-004 | Aurora SSL 연결 | TASK-002 |
| NFR-005 | ElastiCache TLS 연결 | TASK-002 |
| NFR-006 | 무중단 배포 (rolling update, circuit breaker) | Terraform 기존 설정, TASK-005 검증 |

## 태스크 목록

### TASK-001: Dockerfile 헬스체크 경로 수정
- **변경 유형**: Structural
- **설명**: Dockerfile의 `HEALTHCHECK` 경로를 `/health/live` → `/health`로 수정. CMD entrypoint도 확인.
- **완료 기준**: Dockerfile 내 `/health` 경로 확인
- **커밋 메시지**: `structural: fix Dockerfile healthcheck path to /health`

### TASK-002: 코드 수정 — ElastiCache TLS + 환경변수 호환성
- **변경 유형**: Behavioral
- **설명**: 
  1. Terraform `container_environment`에 설정된 환경변수(DB_HOST, REDIS_HOST 등)와 `ServerConfig.from_env()` 매핑 확인
  2. ElastiCache Serverless는 TLS 필수 — `_init_redis`에 `ssl=True` 설정 추가/확인
  3. Secrets Manager JSON → DATABASE_URL 변환 경로 확인
  4. Bedrock IAM 권한 확인 (Terraform task_role)
  5. ECR push 권한 확인 (claw-dev-role)
- **완료 기준**: 환경변수 1:1 매핑 테이블 작성, TLS 설정 코드 수정 완료, IAM 권한 확인
- **관련 요구사항**: FR-003, NFR-004, NFR-005

### TASK-003: Docker 빌드 + ECR push
- **변경 유형**: Behavioral
- **설명**: 
  1. `docker build -t callbot-dev-api .` — 이미지 크기 확인 (500MB 이하)
  2. ECR login: `aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin 961676526279.dkr.ecr.ap-northeast-2.amazonaws.com`
  3. `docker tag callbot-dev-api:latest 961676526279.dkr.ecr.ap-northeast-2.amazonaws.com/callbot-dev-api:latest`
  4. `docker push`
- **의존성**: TASK-001, TASK-002
- **완료 기준**: 이미지 빌드 성공, 크기 500MB 이하, ECR에 이미지 존재 확인
- **관련 요구사항**: FR-001, FR-002, NFR-002

### TASK-004: ECS 서비스 업데이트 및 헬스체크 확인
- **변경 유형**: Behavioral
- **설명**: 
  1. `aws ecs update-service --cluster callbot-dev --service callbot-dev-api --force-new-deployment`
  2. `aws ecs wait services-stable --cluster callbot-dev --services callbot-dev-api`
  3. ALB 헬스체크 통과 확인 (target group healthy count = 2)
  4. CloudWatch 로그 확인 (`/ecs/callbot-dev`)
  5. DB 스키마 초기화 로그 확인
- **의존성**: TASK-003
- **완료 기준**: 2/2 태스크 RUNNING, `/health` 200, CloudWatch 로그 출력
- **관련 요구사항**: FR-004, FR-007, FR-008, NFR-003, NFR-006

### TASK-005: 풀 파이프라인 E2E 검증
- **변경 유형**: Behavioral (검증)
- **설명**: 
  1. `curl -X POST http://{ALB}/api/v1/turn -H 'Content-Type: application/json' -d '{"caller_id":"test","text":"요금 조회"}'` → 200 + 응답 텍스트
  2. WebSocket 연결 테스트 (선택 — ACM 없으면 ws:// 직접)
- **의존성**: TASK-004
- **완료 기준**: `/api/v1/turn` 정상 응답 (503이 아닌 LLM 응답), WebSocket 연결 성공
- **관련 요구사항**: FR-005, FR-006

### TASK-006: CloudFront 전환 (P1)
- **변경 유형**: Structural
- **설명**: 기존 CloudFront (`E2TRVDNBPEL9CK`)의 origin을 EC2 ALB → ECS ALB (`callbot-dev-alb-587084408.ap-northeast-2.elb.amazonaws.com`)로 변경. AWS CLI 또는 Terraform으로 실행.
- **의존성**: TASK-005
- **완료 기준**: CloudFront URL로 `/api/v1/turn` 정상 응답
- **관련 요구사항**: FR-009

### TASK-007: 기존 EC2 인프라 정리 (P2)
- **변경 유형**: Structural
- **설명**: 
  1. 기존 EC2 (`43.200.154.140`) 중지/삭제
  2. 구 ALB, 구 CF 정리 (Terraform destroy 또는 수동)
  3. `callbot/infra/` 디렉토리 정리
- **의존성**: TASK-006
- **완료 기준**: EC2 terminated, 구 ALB/CF 삭제 확인
- **관련 요구사항**: FR-010

## 태스크 의존성 그래프
```
TASK-001 (Dockerfile) ──┐
TASK-002 (코드수정/TLS) ─┤→ TASK-003 (빌드+push) → TASK-004 (ECS 업데이트) → TASK-005 (E2E)
                                                                                  ↓
                                                                            TASK-006 (CF) → TASK-007 (정리)
```

## 테스트 전략
- TASK-002: Docker 컨테이너 `/health` curl 테스트
- TASK-005: ALB 헬스체크 + CloudWatch 로그 확인
- TASK-006: `/api/v1/turn` E2E curl 테스트 + WebSocket 연결 테스트
- 기존 395 tests는 코드 변경 시에만 실행 (TASK-004에서 config 수정 시)
