# Vercel + Railway Split Deployment

This project should run with role separation:

- Vercel: web/frontend + lightweight API only
- Railway: Python/Node PPT worker pipeline

## Runtime role env

Use `PPT_EXECUTION_ROLE` to hint runtime behavior:

- `web`: disables heavy PPT worker defaults
- `worker`: enables worker-safe defaults
- `auto`: infer from platform (`VERCEL*` -> `web`, else `worker`)

## Recommended Vercel env

```text
PPT_EXECUTION_ROLE=web
PPT_EXPORT_SYNC_ENABLED=false
PPT_EXPORT_WORKER_BASE_URL=https://your-railway-worker-domain
# Optional shared token when worker auth is enabled:
# PPT_EXPORT_WORKER_TOKEN=
# Optional HMAC signing secret (recommended):
# PPT_EXPORT_WORKER_SHARED_SECRET=
PPT_MODULE_RETRY_ENABLED=false
PPT_INSTALLED_SKILL_EXECUTOR_ENABLED=false
```

## Recommended Railway env

```text
PPT_EXECUTION_ROLE=worker
PPT_EXPORT_SYNC_ENABLED=true
# Optional HMAC verification secret (recommended):
# PPT_EXPORT_WORKER_SHARED_SECRET=
# Optional explicit switch, defaults to true when secret exists:
# PPT_EXPORT_WORKER_REQUIRE_SIGNATURE=true
PPT_MODULE_RETRY_ENABLED=true
PPT_MODULE_RETRY_MAX_PARALLEL=5
# Mainflow is enabled by default on worker role (set false only for temporary rollback)
# PPT_MODULE_MAINFLOW_ENABLED=true
# Mainflow render_each is enabled by default on worker role (per-slide subagent pass).
# PPT_MODULE_MAINFLOW_RENDER_EACH_ENABLED=true
# Subagent execution is always enabled on worker role.
```

If you need installed external skill runtime on Railway:

```text
# Enabled by default on worker role; keep this only when you want explicit override.
# PPT_INSTALLED_SKILL_EXECUTOR_ENABLED=true
# PPT_INSTALLED_SKILL_EXECUTOR_BIN=uv
# PPT_INSTALLED_SKILL_EXECUTOR_ARGS=["run","python","-m","src.installed_skill_executor"]
# PPT_INSTALLED_SKILL_EXECUTOR_TIMEOUT_SEC=30
# Optional explicit cwd override (defaults to agent root automatically)
# PPT_INSTALLED_SKILL_EXECUTOR_CWD=/app

# Direct skill runtime backend (default: builtin heuristic).
# For Codex CLI + SKILL.md parity planning:
# PPT_DIRECT_SKILL_RUNTIME_MODE=codex_cli
# PPT_DIRECT_SKILL_RUNTIME_REQUIRE=true
# PPT_DIRECT_SKILL_RUNTIME_CODEX_BIN=codex
# PPT_DIRECT_SKILL_RUNTIME_CODEX_ARGS=["exec","--skip-git-repo-check","--sandbox","read-only"]
# PPT_DIRECT_SKILL_RUNTIME_CODEX_TIMEOUT_SEC=90
# PPT_DIRECT_SKILL_RUNTIME_CODEX_CWD=/app
# PPT_DIRECT_SKILL_RUNTIME_SKILL_ROOTS=/app/vendor/minimax-skills/plugins/pptx-plugin/skills:/app/vendor/minimax-skills/skills
# PPT_DIRECT_SKILL_RUNTIME_SKILL_CONTENT_MAX_CHARS=120000
```

## Operational notes

- Keep artifacts in object storage (R2/S3), not local filesystem.
- Persist job state in DB and expose status polling endpoint.
- Do not run long-running subagent/compile loops on Vercel runtime.

## V7 export API mode

- Web role should call:
  - `POST /api/v1/v7/export/submit`
  - `GET /api/v1/v7/export/status/{task_id}`
- Worker role supports both:
  - async submit/status
  - sync `POST /api/v1/v7/export`
