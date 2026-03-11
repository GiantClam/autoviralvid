FROM python:3.12-slim AS builder

WORKDIR /app

COPY . /src

RUN if [ -f /src/agent/pyproject.toml ]; then \
      mkdir -p /app/agent && cp -R /src/agent/. /app/agent/; \
    elif [ -f /src/pyproject.toml ]; then \
      mkdir -p /app/agent && cp -R /src/. /app/agent/; \
    else \
      echo "No agent Python project found in build context" >&2; \
      exit 1; \
    fi

RUN pip install --no-cache-dir uv

WORKDIR /app/agent

RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runner

WORKDIR /app/agent

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/agent/.venv /app/agent/.venv
COPY --from=builder /app/agent /app/agent

ENV PATH="/app/agent/.venv/bin:$PATH"
ENV PYTHONPATH="/app/agent"
ENV PYTHONUNBUFFERED=1

RUN mkdir -p /app/agent/renders /app/agent/logs \
    && useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app/agent

USER appuser

EXPOSE 8000

CMD ["sh", "-c", "/app/agent/.venv/bin/uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
