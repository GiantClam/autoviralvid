# Vercel + Railway Split Deployment

This project should run with role separation:

- Vercel: web/frontend + lightweight API only
- Railway: Python/Node PPT worker pipeline

## Runtime role env

Use `PPT_EXECUTION_ROLE` to hint runtime behavior:

- `web`: disables heavy PPT worker defaults
- `worker`: enables worker-safe defaults
- `auto`: infer from platform (`VERCEL*` -> `web`, else `worker`)

## Billing rollout note

If you are enabling subscription + credits + generation charging in production:

- Run Supabase SQL first:
  - `docs/sql/2026-04-15-billing-core-supabase.sql`
- Then set billing env on Vercel:
  - `DATABASE_URL`
  - `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_PLAN_PRO`, `PAYPAL_PLAN_ENTERPRISE`
  - `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_PRO`, `STRIPE_PRICE_ENTERPRISE`
  - `GENERATION_BILLING_ENABLED=true`
  - `BILLING_RECONCILE_TOKEN` (or `CRON_SECRET`)
- Full checklist:
  - `docs/runbooks/production-billing-deploy.md`

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

# Direct skill runtime backend (builtin only in normal production flow).
# PPT_DIRECT_SKILL_RUNTIME_REQUIRE=true
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
