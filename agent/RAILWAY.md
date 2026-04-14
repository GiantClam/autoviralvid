# Railway Backend Deployment

This backend should be deployed as a dedicated Railway service.

## Service settings

- Root Directory: repository root (`.`)
- Dockerfile path: `Dockerfile`
- Health check: `/healthz`
- Replicas: `1`

Use:

- [Dockerfile](d:/github/with-langgraph-fastapi/Dockerfile)
- [railway.toml](d:/github/with-langgraph-fastapi/railway.toml)

## Required environment variables

At minimum:

```text
AUTH_SECRET=
NEXTAUTH_SECRET=
AUTH_REQUIRED=true
CORS_ORIGIN=https://your-frontend.vercel.app
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
```

For digital-human video generation:

```text
RUNNINGHUB_API_KEY=
RUNNINGHUB_SORA2_WORKFLOW_ID=1985261217524629506
RUNNINGHUB_MAX_CONCURRENT=1
R2_ACCOUNT_ID=
R2_ACCESS_KEY=
R2_SECRET_KEY=
R2_BUCKET=video
R2_PUBLIC_BASE=https://your-cdn.example.com
```

For storyboard/LLM features:

```text
OPENROUTER_API_KEY=
OPENROUTER_API_BASE=https://openrouter.ai/api/v1
# Optional: use AIBERM as primary upstream, auto-fallback to OpenRouter
# AIBERM_API_BASE=https://your-aiberm-gateway.example.com/v1
# AIBERM_API_KEY=
# Optional: CRAZYROUTE works the same as AIBERM and is used when AIBERM is absent
# CRAZYROUTE_API_BASE=https://your-crazyroute-gateway.example.com/v1
# CRAZYROUTE_API_KEY=
# OPENROUTER_FALLBACK_API_BASE=https://openrouter.ai/api/v1
# OPENROUTER_FALLBACK_API_KEY=   # optional, defaults to OPENROUTER_API_KEY
# CONTENT_LLM_MODEL=openai/gpt-5.3-codex  # optional
```

For PPT module retry + subagent executor:

```text
# Runtime role hint (worker/web/auto). Railway service should be worker.
PPT_EXECUTION_ROLE=worker
PPT_EXPORT_SYNC_ENABLED=true
# Optional shared-secret signature verification for web->worker submit/status proxy.
# If set, worker endpoints require valid HMAC headers by default.
PPT_EXPORT_WORKER_SHARED_SECRET=
# Optional explicit switch (default true when shared secret is set)
# PPT_EXPORT_WORKER_REQUIRE_SIGNATURE=true

# Enable per-slide module retry orchestration (single-slide retry -> parallel render -> full-deck compile)
PPT_MODULE_RETRY_ENABLED=true
PPT_MODULE_RETRY_MAX_PARALLEL=5
# Mainflow is enabled by default on worker role (set false only for temporary rollback)
# PPT_MODULE_MAINFLOW_ENABLED=true

# Installed skill executor (S13 real skill chain) is enabled by default on worker role.
# Optional overrides:
# PPT_INSTALLED_SKILL_EXECUTOR_ENABLED=true
# PPT_INSTALLED_SKILL_EXECUTOR_BIN=uv
# PPT_INSTALLED_SKILL_EXECUTOR_ARGS=["run","python","-m","src.installed_skill_executor"]
# PPT_INSTALLED_SKILL_EXECUTOR_TIMEOUT_SEC=30
# Optional explicit cwd override (defaults to agent root automatically)
# PPT_INSTALLED_SKILL_EXECUTOR_CWD=/app

# Direct skill runtime backend for installed_skill_executor.
# Default mode is builtin heuristic; to align with Codex CLI + SKILL.md planning:
# PPT_DIRECT_SKILL_RUNTIME_MODE=codex_cli
# PPT_DIRECT_SKILL_RUNTIME_REQUIRE=true   # strict: no fallback
# PPT_DIRECT_SKILL_RUNTIME_CODEX_BIN=codex
# PPT_DIRECT_SKILL_RUNTIME_CODEX_ARGS=["exec","--skip-git-repo-check","--sandbox","read-only"]
# PPT_DIRECT_SKILL_RUNTIME_CODEX_TIMEOUT_SEC=90
# PPT_DIRECT_SKILL_RUNTIME_CODEX_CWD=/app
# Optional skill root override (os.pathsep-separated):
# PPT_DIRECT_SKILL_RUNTIME_SKILL_ROOTS=/app/vendor/minimax-skills/plugins/pptx-plugin/skills:/app/vendor/minimax-skills/skills
# Optional max SKILL.md injection chars:
# PPT_DIRECT_SKILL_RUNTIME_SKILL_CONTENT_MAX_CHARS=120000

# Subagent execution before each targeted slide render is always enabled on worker role.

# Optional: custom subagent executor process.
# Default executor (when these are unset):
#   uv run python -m src.ppt_subagent_executor
# PPT_SUBAGENT_EXECUTOR_BIN=
# PPT_SUBAGENT_EXECUTOR_ARGS=
# PPT_SUBAGENT_EXECUTOR_CWD=/app

# Shared model id (used by all LLM call sites in this project)
CONTENT_LLM_MODEL=openai/gpt-5.3-codex
OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
# Optional OpenAI-compatible gateways (priority: AIBERM -> CRAZYROUTE -> OPENROUTER)
# AIBERM_API_BASE=
# AIBERM_API_KEY=
# CRAZYROUTE_API_BASE=
# CRAZYROUTE_API_KEY=

# OR OpenAI mode
# OPENAI_API_KEY=
# CONTENT_LLM_MODEL=gpt-5.3-codex
```

For Vercel frontend runtime (non-worker), explicitly keep heavy execution off:

```text
PPT_EXECUTION_ROLE=web
PPT_EXPORT_SYNC_ENABLED=false
PPT_EXPORT_WORKER_BASE_URL=https://your-railway-worker-domain
# Optional internal auth passthrough when backend auth is enabled:
# PPT_EXPORT_WORKER_TOKEN=
# Optional HMAC signing secret (must match worker side)
# PPT_EXPORT_WORKER_SHARED_SECRET=
PPT_MODULE_RETRY_ENABLED=false
PPT_INSTALLED_SKILL_EXECUTOR_ENABLED=false
```

V7 export split calls:

- `POST /api/v1/v7/export/submit` to enqueue export
- `GET /api/v1/v7/export/status/{task_id}` to poll status
- `POST /api/v1/v7/export` remains sync path for worker role

## Verification

After deployment, check:

```text
GET /healthz
GET /docs
GET /render/health
```

`/render/health` should report `ffmpeg_available=true`.
