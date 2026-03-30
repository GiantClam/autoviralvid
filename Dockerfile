FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY agent/pyproject.toml agent/uv.lock /app/agent/
WORKDIR /app/agent
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runner

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/agent/.venv /app/agent/.venv
COPY . /app

RUN npm ci --omit=dev

ENV PATH="/app/agent/.venv/bin:$PATH"
ENV PYTHONPATH="/app/agent"
ENV PYTHONUNBUFFERED=1

RUN mkdir -p /app/agent/renders /app/agent/logs \
    && useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["sh", "-c", "cd /app/agent && /app/agent/.venv/bin/uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
