FROM python:3.12-slim

WORKDIR /opt/callbot

# uv 설치
RUN pip install --no-cache-dir uv

# 의존성 먼저 (캐시 레이어)
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

# 소스 복사
COPY . .

# /opt/ 를 PYTHONPATH에 추가 → import callbot.xxx 가능
ENV PYTHONPATH=/opt

EXPOSE 8000

# ALB health check handles /health — no Docker HEALTHCHECK needed for ECS

CMD [".venv/bin/python", "-m", "server"]
