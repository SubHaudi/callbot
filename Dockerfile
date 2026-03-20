FROM python:3.12-slim

WORKDIR /app

# uv 설치
RUN pip install --no-cache-dir uv

# 의존성 먼저 (캐시 레이어)
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

# 소스 복사
COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')" || exit 1

CMD [".venv/bin/python", "-m", "server"]
