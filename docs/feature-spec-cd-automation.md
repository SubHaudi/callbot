# CD 자동화 기능정의서

## 1. 개요
- main 브랜치 push 시 CI 통과 후 자동으로 ECR → ECS → CloudFront 배포를 수행하는 GitHub Actions CD 파이프라인
- 핵심 가치: 수동 `deploy.sh` 실행 제거, 코드 머지 → 자동 배포로 개발 속도 향상

## 2. 배경 및 목적
- **문제**: 현재 배포는 개발자가 로컬에서 `deploy.sh`를 수동 실행. AWS 자격증명 필요, 배포 일관성 보장 어려움.
- **As-Is**: `ci.yml`(테스트+스모크) + `deploy.sh`(수동 ECR/ECS/CF) 분리 운영
- **To-Be**: `ci.yml` 통과 후 `cd.yml`이 자동으로 Docker build → ECR push → ECS force-deploy → CF invalidation 실행
- **비즈니스 임팩트**: 배포 시간 단축, 휴먼 에러 제거, 일관된 배포 프로세스

## 3. 용어 정의

| 용어 | 정의 |
|------|------|
| CD | Continuous Deployment. 코드 변경이 자동으로 프로덕션에 배포되는 프로세스 |
| CI | Continuous Integration. 테스트 자동화 (`ci.yml`) |
| ECR | AWS Elastic Container Registry. Docker 이미지 저장소 |
| ECS | AWS Elastic Container Service. 컨테이너 오케스트레이션 |
| CF Invalidation | CloudFront 캐시 무효화 |
| OIDC | OpenID Connect. GitHub → AWS 역할 위임 시 사용하는 인증 방식 |

## 4. 사용자 스토리

- **US-001**: 개발자로서, main에 코드를 push하면 테스트 통과 후 자동으로 배포됐으면 좋겠다
- **US-002**: 개발자로서, 배포 실패 시 어느 단계에서 실패했는지 GitHub Actions에서 바로 확인하고 싶다
- **US-003**: 운영자로서, 배포된 Docker 이미지가 어떤 커밋에서 빌드됐는지 추적하고 싶다

## 5. 기능 요구사항

| ID | 요구사항 | 우선순위 | 관련 US |
|----|---------|---------|---------|
| FR-001 | CD 워크플로우: main push 시 CI 성공 후 자동 실행 | P0 | US-001 |
| FR-002 | Docker build + ECR push: 커밋 SHA 태그 + latest 태그 | P0 | US-001, US-003 |
| FR-003 | ECS force-deploy + 안정화 대기 | P0 | US-001 |
| FR-004 | CloudFront invalidation (`/demo/*`, `/admin/*`) | P0 | US-001 |
| FR-005 | AWS 인증: OIDC 우선, Access Key 폴백 허용 (GitHub → AWS IAM Role) | P0 | US-001 |
| FR-006 | 배포 단계별 로그 + 실패 시 명확한 에러 메시지 | P1 | US-002 |

## 6. 비기능 요구사항

| ID | 요구사항 | 기준 |
|----|---------|------|
| NFR-001 | CD 전체 소요 시간 | 10분 이내 (CI 제외) |
| NFR-002 | 기존 CI 영향 없음 | ci.yml 변경 없이 CD 추가 |
| NFR-003 | 시크릿 관리 | AWS 자격증명은 OIDC 또는 GitHub Secrets 사용, 코드에 하드코딩 금지 |

## 7. 기술 설계

### 아키텍처
- `.github/workflows/cd.yml` 신규 생성
- CI(`ci.yml`) 완료 후 CD 트리거 (`workflow_run` 이벤트)
- GitHub OIDC → AWS IAM Role 위임 (기존 `claw-dev-role` 활용 또는 전용 role)

### CD 워크플로우 흐름
1. `ci.yml` 성공 (main push) → `cd.yml` 트리거
2. AWS OIDC 인증
3. ECR 로그인
4. Docker build + tag (`latest` + `${{ github.sha }}`)
5. ECR push
6. ECS update-service --force-new-deployment
7. ECS wait services-stable (timeout 5분)
8. CloudFront invalidation

### AWS 설정
- **리전**: ap-northeast-2
- **ECR**: `961676526279.dkr.ecr.ap-northeast-2.amazonaws.com/callbot-dev-api`
- **ECS 클러스터**: `callbot-dev`
- **ECS 서비스**: `callbot-dev-api`
- **CF Distribution**: `E1I8BGAT5D2987`
- **IAM Role**: GitHub OIDC 신뢰 정책이 필요 (또는 Access Key 방식 폴백)

### GitHub Secrets 필요 목록
- `AWS_ROLE_ARN` (OIDC 방식) 또는 `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`
- CF distribution ID는 워크플로우 내 하드코딩 가능 (공개 정보)

## 8. 데이터 모델
- 변경 없음

## 9. API 설계
- 변경 없음

## 10. UI/UX 고려사항
- GitHub Actions 탭에서 CD 워크플로우 실행 상태 확인 가능
- 각 step에 명확한 이름 부여 (Build, Push, Deploy, Invalidate)

## 11. 마일스톤 및 일정

| Phase | 내용 | 포함 FR | 예상 기간 |
|-------|------|---------|----------|
| 1 | cd.yml 작성 + GitHub Secrets 설정 안내 | FR-001~006 | 30분 |

## 12. 리스크 및 완화 방안

| ID | 리스크 | 확률 | 영향 | 완화 |
|----|--------|------|------|------|
| RISK-001 | OIDC IAM Role 설정 미비로 인증 실패 | M | H | Access Key 방식을 폴백으로 제공, OIDC 설정 가이드 문서화 |
| RISK-002 | ECS 안정화 대기 타임아웃 | L | M | timeout 설정 + 실패 시 명확한 에러 로그 |
| RISK-003 | main push마다 배포되어 불안정한 코드 배포 | L | M | CI(test+smoke) 통과 필수 조건으로 게이트 역할 |

## 13. 성공 지표

| KPI | 목표 | 측정 방법 |
|-----|------|----------|
| CD 성공률 | ≥ 95% | GitHub Actions 실행 이력 |
| CD 소요 시간 | ≤ 10분 | GitHub Actions 타임라인 |
| 수동 배포 빈도 | 0회 (CD 도입 후) | 팀 기록 |

## 14. 의존성
- GitHub Actions (GitHub 제공)
- AWS ECR, ECS, CloudFront (기존 인프라)
- AWS IAM (OIDC 또는 Access Key)
- 기존 `ci.yml` 워크플로우

## 15. 범위 제외 사항
- 프로덕션 환경 CD (현재 dev만)
- 블루/그린 배포, 카나리 배포
- Slack/Discord 배포 알림 (향후 추가 가능)
- Terraform 인프라 자동화 (별도 관리)
