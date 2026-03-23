# 🤖 Callbot — AI 통신사 콜봇

통신사 고객 응대 AI 음성 콜봇. 실시간 음성 통화로 요금 조회, 데이터 변경, 로밍 신청 등을 처리합니다.

## 🎯 Demo

> **Live Demo**: https://da0dhxbqgiqxc.cloudfront.net/demo

브라우저에서 마이크 버튼을 누르고 말하면 AI가 실시간으로 응답합니다.

```
👤 "요금 조회해주세요"
🤖 "네, 본인 확인을 위해 전화번호를 말씀해주세요."
👤 "010-1234-5678"
🤖 "김철수 고객님, 현재 5G 프리미어 요금제를 사용 중이시며 이번 달 요금은 65,000원입니다."
```

### 주요 기능
- 🎙️ **실시간 음성 대화** — STT(Transcribe) → AI 응답(Bedrock) → TTS(Polly)
- 🧠 **13개 인텐트** — 요금 조회, 데이터 변경, 로밍, 분실 신고, 해지 등
- 🔇 **VAD (Voice Activity Detection)** — 자동 음성 종료 감지
- 🔒 **PII 마스킹** — 개인정보 자동 마스킹 (주민번호, 전화번호 등)
- 📊 **Admin Dashboard** — 통화 이력, 통계, 인텐트 분석

## 🏗️ Architecture

```
                    ┌─────────────┐
                    │  CloudFront │ ← HTTPS, WAF, Cache
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │     ALB     │ ← Regional WAF
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ ECS Fargate │ ← Python/FastAPI
                    │  (2 tasks)  │
                    └──┬────┬──┬──┘
                       │    │  │
          ┌────────────┘    │  └────────────┐
          ▼                 ▼               ▼
   ┌─────────────┐  ┌────────────┐  ┌─────────────┐
   │   Aurora     │  │   Redis    │  │   Bedrock   │
   │ PostgreSQL   │  │ (Session)  │  │  (Claude)   │
   └─────────────┘  └────────────┘  └─────────────┘

   Voice Pipeline:
   Browser Mic → WebSocket → ALB (직접, CF 미경유) → Transcribe STT
                                                          ↓
                                                   NLU + Pipeline
                                                          ↓
                                                    Polly TTS → Speaker
```

## 🔧 Tech Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.12 / FastAPI / Uvicorn |
| AI/ML | Amazon Bedrock (Claude), Transcribe (STT), Polly (TTS) |
| Database | Aurora Serverless v2 (PostgreSQL) |
| Cache | ElastiCache Serverless (Redis) |
| Infra | ECS Fargate, CloudFront, WAF v2, VPC |
| IaC | Terraform (20+ files, 2-layer architecture) |
| CI/CD | GitHub Actions (CI) + deploy.sh (CD) |
| Test | pytest (741 passed, 54k+ parametrized cases) |

## 📊 Admin Dashboard

> **Live**: https://da0dhxbqgiqxc.cloudfront.net/admin

- 통화 목록 (검색, 필터, 페이지네이션)
- 통화 상세 (전체 대화 이력, 인텐트 흐름)
- 일별 통화량 차트
- 인텐트 분포 통계
- 해결률 (resolved/unresolved/escalated)

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (패키지 매니저)
- AWS credentials (Bedrock, Transcribe, Polly 접근 권한)

### 로컬 실행
```bash
git clone https://github.com/SubHaudi/callbot.git
cd callbot
uv sync                    # 의존성 설치
uv run pytest              # 테스트 실행
uv run uvicorn server.app:app --reload  # 로컬 서버 (http://localhost:8000)
```

> ⚠️ 로컬 실행 시 Aurora/Redis 대신 인메모리 fallback 사용. 전체 기능은 AWS 인프라 필요.

### 프로덕션 배포
```bash
# 1. 인프라 배포 (별도 레포: callbot-infra)
cd callbot-infra/envs/dev/foundation && terraform apply
cd callbot-infra/envs/dev/application && terraform apply

# 2. 앱 배포
./deploy.sh --env dev
```

See [callbot-infra](https://github.com/SubHaudi/callbot-infra) for infrastructure setup.

## 📁 Project Structure

```
├── server/              ← FastAPI 서버, 라우터, 미들웨어
│   ├── pipeline.py      ← TurnPipeline (핵심 대화 처리)
│   ├── voice_ws.py      ← WebSocket 음성 라우터
│   └── app.py           ← FastAPI 앱 + DI 조립
├── nlu/                 ← 자연어 이해 (패턴 매칭 13 인텐트)
├── orchestrator/        ← 대화 흐름 관리 (멀티스텝)
├── session/             ← 세션 관리 (Redis + Aurora)
├── llm_engine/          ← Bedrock 클라이언트 + 프롬프트 로더
├── voice_io/            ← STT (Transcribe) + TTS (Polly) + VAD
├── external/            ← 외부 시스템 연동 (fake/mock)
├── monitoring/          ← 메트릭 수집, 헬스체크
├── business/            ← 비즈니스 모델
├── deploy.sh            ← ECR build → ECS deploy → CF invalidation
└── Dockerfile           ← 프로덕션 이미지
```

## 📈 Development History

> Phase A-B는 초기 설계 및 기반 구축 (서버 스켈레톤, 세션 모델 등)

| Phase | 내용 | PR |
|-------|------|-----|
| C | Pipeline redesign, intent routing, PII masking | #1, #2 |
| C-QA | English injection fix, PII edge cases, retry limit | #3 |
| D | Monitoring & operational stability | #4, #5 |
| E | NLU Enhancement — 13 intents, pattern matching | #6 |
| F | Voice I/O — Transcribe STT + Polly TTS | #7, #8 |
| G | Full Voice Pipeline E2E — WebSocket integration | #9 |
| H | Realtime Streaming — chunk protocol, barge-in | #10 |
| I | VAD + Manual Stop — silence detection | #13 |
| J | Call Log + Admin Dashboard | #14, #15 |

## 📄 License

Private repository.
