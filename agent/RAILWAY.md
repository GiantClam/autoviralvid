# Railway Backend Deployment

This backend should be deployed as a dedicated Railway service.

## Service settings

- Recommended:
  - Root Directory: repository root
  - Dockerfile path: `Dockerfile`
- Alternative:
  - Root Directory: `agent`
  - Dockerfile path: `Dockerfile`
- Health check: `/healthz`
- Replicas: `1`

The repository now includes both a repository-root Dockerfile and
`agent/Dockerfile` so either deployment layout can work.

If you deploy from the repository root, Railway should use:

- [Dockerfile](d:/github/with-langgraph-fastapi/Dockerfile)
- [railway.toml](d:/github/with-langgraph-fastapi/railway.toml)

If you deploy from `agent`, Railway should use:

- [agent/Dockerfile](d:/github/with-langgraph-fastapi/agent/Dockerfile)
- [agent/railway.toml](d:/github/with-langgraph-fastapi/agent/railway.toml)

Do not combine `Root Directory = agent` with `Dockerfile path = agent/Dockerfile`,
or Railway will look for `agent/agent/Dockerfile` and fail.

If you use Railway config-as-code, point the service at `agent/railway.toml`.

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
```

## Verification

After deployment, check:

```text
GET /healthz
GET /docs
GET /render/health
```

`/render/health` should report `ffmpeg_available=true`.
