# AutoViralVid

This repository contains a Next.js frontend plus a Python backend for video generation, digital-human orchestration, stitching, and rendering. The production backend entrypoint is `agent/main.py`.

## Prerequisites

- Node.js 18+ 
- Python 3.8+
- Poetry 2+
- Any of the following package managers:
  - [pnpm](https://pnpm.io/installation) (recommended)
  - npm
  - [yarn](https://classic.yarnpkg.com/lang/en/docs/install/#mac-stable)
  - [bun](https://bun.sh/)
- Backend service credentials for the integrations you use

> **Note:** `package-lock.json` is committed and should stay in sync with `package.json` so frontend builds remain reproducible across local, CI, and Vercel environments.

## Getting Started

1. Install dependencies using your preferred package manager:
```bash
# Using pnpm (recommended)
pnpm install

# Using npm
npm install

# Using yarn
yarn install

# Using bun
bun install
```

2. Install Python dependencies for the backend service:
```bash
# Using pnpm
pnpm install:agent

# Using npm
npm run install:agent

# Using yarn
yarn install:agent

# Using bun
bun run install:agent
```

3. Configure backend environment variables:
```bash
cp agent/.env.example agent/.env
```

4. Start the development server:
```bash
# Using pnpm
pnpm dev

# Using npm
npm run dev

# Using yarn
yarn dev

# Using bun
bun run dev
```

This will start both the UI and agent servers concurrently.

## Available Scripts
The following scripts can also be run using your preferred package manager:
- `dev` - Starts both UI and agent servers in development mode
- `dev:debug` - Starts development servers with debug logging enabled
- `dev:ui` - Starts only the Next.js UI server
- `dev:agent` - Starts only the Python backend server
- `dev:agent:render` - Starts a stable non-reload Python renderer on port `8124` for UI render E2E
- `build` - Builds the Next.js application for production
- `start` - Starts the production server
- `lint` - Runs ESLint for code linting
- `test` - Runs offline-safe frontend unit tests
- `test:integration` - Runs renderer/API integration tests that require local services
- `test:deployed` - Runs deployed-environment smoke tests against Vercel/Railway targets
- `test:ui:openclaw` - Starts a stable local frontend/backend pair and runs the browser UI Remotion E2E for the OpenClaw intro video
- `test:ui:product-ad` - Runs the browser UI Remotion E2E harness against a vertical ecommerce promo scenario
- `test:ui:brand-story-video` - Runs the browser UI Remotion E2E harness against a real `video`-layer scenario
- `test:ui:travel-vlog-media` - Runs the browser UI Remotion E2E harness against a media-layer scenario with remote image + audio inputs
- `test:ui:knowledge` - Runs the same browser UI Remotion E2E harness against the Knowledge & Edu template scenario
- `test:ui:all` - Runs the full browser UI Remotion E2E suite across all maintained scenarios
- `install:agent` - Installs Python dependencies for the agent

PPT-specific maintenance commands:
- `bash scripts/vendor/sync_minimax_skills.sh` - refresh vendored MiniMax official `pptx-plugin` + `pptx-generator` snapshot
- `bash scripts/tests/test_minimax_vendor_sync.sh` - verify the vendor snapshot is present and pinned

There is also a manual GitHub Actions workflow, `UI Render E2E`, which installs Playwright plus ffmpeg and runs the same browser-driven Remotion path in CI when you want a release-grade UI render check.
The workflow accepts a `scenario` input so you can run `all`, `openclaw`, `product-ad`, `brand-story-video`, `travel-vlog-media`, or `knowledge-edu`.

## Vercel Deployment

The Next.js frontend compiles on Vercel, but production deployment requires explicit environment variables. The app no longer falls back to `localhost` in production.

Required Vercel env vars:

- `AUTH_SECRET` or `NEXTAUTH_SECRET`
- `NEXTAUTH_URL` or `NEXT_PUBLIC_SITE_URL`
- `AGENT_URL` or `NEXT_PUBLIC_AGENT_URL`

Optional but commonly needed:

- `NEXT_PUBLIC_API_BASE`
- `REMOTION_RENDERER_URL`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `PAYPAL_CLIENT_ID`
- `PAYPAL_CLIENT_SECRET`
- `PAYPAL_PLAN_PRO`
- `PAYPAL_PLAN_ENTERPRISE`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_PRO`
- `STRIPE_PRICE_ENTERPRISE`
- `GENERATION_BILLING_ENABLED`
- `BILLING_RECONCILE_TOKEN` (or `CRON_SECRET`)

Notes:

- The frontend expects the Python backend to be reachable at `AGENT_URL` in production.
- For split deployment, keep Vercel in `web` role (no heavy PPT worker chain):
  - `PPT_EXECUTION_ROLE=web`
  - `PPT_MODULE_RETRY_ENABLED=false`
  - `PPT_INSTALLED_SKILL_EXECUTOR_ENABLED=false`
  - `PPT_EXPORT_SYNC_ENABLED=false`
  - `PPT_EXPORT_WORKER_BASE_URL=https://<your-railway-worker-domain>`
  - optional: `PPT_EXPORT_WORKER_TOKEN=<internal-shared-token>`
  - optional (recommended): `PPT_EXPORT_WORKER_SHARED_SECRET=<shared-hmac-secret>`
- `npm run build` runs `prisma generate` automatically before the Next.js build.
- `npm test` excludes service-dependent integration tests by default so CI and Vercel checks stay deterministic.
- `npm run test:deployed` requires `DEPLOYED_FRONTEND_URL` and `DEPLOYED_BACKEND_URL`; set `ALLOW_PAID_DEPLOYED_E2E=1` plus the digital-human audio env vars only when you want real end-to-end generation against production services.

## Railway Deployment

Deploy the Python backend as a separate Railway service.

- Set the Railway service `Root Directory` to repository root (`.`)
- Use [Dockerfile](d:/github/with-langgraph-fastapi/Dockerfile)
- If you want config-as-code, point Railway to [railway.toml](d:/github/with-langgraph-fastapi/railway.toml)
- Health check path: `/healthz`
- Keep the service at a single replica because the queue worker runs in-process

Canonical backend start command:

```bash
uv run uvicorn main:app --host 0.0.0.0 --port ${PORT}
```

Do not deploy `agent/src/main.py`; it is a legacy compatibility wrapper only.

Recommended Railway worker env for PPT heavy pipeline:

- `PPT_EXECUTION_ROLE=worker`
- `PPT_MODULE_RETRY_ENABLED=true`
- `PPT_MODULE_MAINFLOW_ENABLED` defaults to `true` across roles (set `false` only for temporary rollback)
- `PPT_MODULE_MAINFLOW_RENDER_EACH_ENABLED` defaults to `true` across roles (mainflow runs per-slide + subagent chain)
- S13 installed skill executor is enabled by default across roles.
- Main path now runs skill-driven planning (`ppt-orchestra-skill` + `slide-making-skill` + `design-style-skill` + `color-font-skill` + conditional `pptx`) before visual orchestration/export.
- optional override: `PPT_INSTALLED_SKILL_EXECUTOR_ENABLED=true|false`
- optional override: `PPT_INSTALLED_SKILL_EXECUTOR_BIN=uv`
- optional override: `PPT_INSTALLED_SKILL_EXECUTOR_ARGS=["run","python","-m","src.installed_skill_executor"]`
- optional override: `PPT_INSTALLED_SKILL_EXECUTOR_TIMEOUT_SEC=30`
- optional override: `PPT_INSTALLED_SKILL_EXECUTOR_CWD=<path-to-agent-dir>` (default auto-resolves to `agent/`)
- optional direct runtime bridge: `PPT_DIRECT_SKILL_RUNTIME_ENABLED=true|false`
- optional direct runtime bridge: `PPT_DIRECT_SKILL_RUNTIME_BIN=<external-skill-runtime-bin>`
- optional direct runtime bridge: `PPT_DIRECT_SKILL_RUNTIME_ARGS=[...]`
- optional direct runtime bridge: `PPT_DIRECT_SKILL_RUNTIME_TIMEOUT_SEC=25`
- optional direct runtime bridge: `PPT_DIRECT_SKILL_RUNTIME_CWD=<path>`
- strict mode (default): `PPT_DIRECT_SKILL_RUNTIME_REQUIRE=true` (no builtin fallback; missing/failed direct runtime returns hard skill error)
- recommended local bridge:
  - `PPT_DIRECT_SKILL_RUNTIME_BIN=python`
  - `PPT_DIRECT_SKILL_RUNTIME_ARGS=["-m","src.ppt_direct_skill_runtime"]`
  - `PPT_DIRECT_SKILL_RUNTIME_CWD=<repo>/agent`
- `PPT_EXPORT_SYNC_ENABLED=true`
- optional: `PPT_EXPORT_WORKER_SHARED_SECRET=<same-shared-hmac-secret-as-vercel>`
- optional: `PPT_EXPORT_WORKER_REQUIRE_SIGNATURE=true` (auto-enabled when shared secret exists)

V7 PPT export API in split mode:

- Submit: `POST /api/v1/v7/export/submit`
- Poll: `GET /api/v1/v7/export/status/{task_id}`
- `POST /api/v1/v7/export` stays available on worker, but is disabled by default on web role.

## Documentation

The main UI component is in `src/app/page.tsx`. You can:
- Modify the theme colors and styling
- Add new frontend actions
- Customize the CopilotKit sidebar appearance

## Additional Docs

- [Next.js Documentation](https://nextjs.org/docs) - Learn about Next.js features and API
- [DEPLOYED_TESTING.md](d:/github/with-langgraph-fastapi/docs/DEPLOYED_TESTING.md) - Deployed-environment smoke tests and paid E2E checks
- [VERCEL_RAILWAY_SPLIT_DEPLOYMENT.md](d:/github/with-langgraph-fastapi/docs/VERCEL_RAILWAY_SPLIT_DEPLOYMENT.md) - Production role split and env matrix for Vercel + Railway
- [production-billing-deploy.md](d:/github/with-langgraph-fastapi/docs/runbooks/production-billing-deploy.md) - Supabase SQL + env + billing deployment checklist

## Contributing

Feel free to submit issues and enhancement requests! This starter is designed to be easily extensible.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Troubleshooting

### Encoding Hygiene (No More Garbled Text)

If you work on Windows + PowerShell, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/enable_utf8_terminal.ps1
```

To persist UTF-8 settings in your PowerShell profile:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/enable_utf8_terminal.ps1 -Persist
```

Before pushing, run:

```bash
npm run test:encoding-hygiene
```

Optional local pre-commit hook:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install_git_hooks.ps1
```

CI also enforces UTF-8 and mojibake checks in `.github/workflows/ci.yml`.

### Agent Connection Issues
If you see "I'm having trouble connecting to my tools", make sure:
1. The Python backend is running on port 8123
2. Your backend environment variables are set correctly
3. Both servers started successfully

### UI Remotion E2E
To validate the browser-driven Remotion path end to end, run:

```bash
npm run test:ui:openclaw
```

This command:
- starts a stable renderer backend on `http://127.0.0.1:8124`
- starts a local Next.js frontend on `http://127.0.0.1:3001`
- runs the browser automation in `scripts/ui_openclaw_remotion_e2e.py`
- saves screenshots under `test_outputs/ui_openclaw/`

### Python Dependencies
If you encounter Python import errors:
```bash
cd agent
uv sync
```
