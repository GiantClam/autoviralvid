# autoviralvid — Overview

> **Navigation aid.** This article shows WHERE things live (routes, models, files). Read actual source files before implementing new features or making changes.

**autoviralvid** is a typescript project built with next-app, using prisma for data persistence.

## Scale

16 API routes · 6 database models · 75 UI components · 16 middleware layers · 241 environment variables

## Subsystems

- **[Auth](./auth.md)** — 3 routes — touches: auth, cache, db
- **[Payments](./payments.md)** — 1 routes — touches: db, payment
- **[Route](./route.md)** — 12 routes — touches: auth, db, cache

**Database:** prisma, 6 models — see [database.md](./database.md)

**UI:** 75 components (react) — see [ui.md](./ui.md)

## High-Impact Files

Changes to these files have the widest blast radius across the codebase:

- `src\remotion\compositions\VideoTemplate.tsx` — imported by **11** files
- `src\lib\types.ts` — imported by **8** files
- `/base.py` — imported by **6** files
- `src\contexts\EditorContext.tsx` — imported by **5** files
- `/models.py` — imported by **4** files
- `/drawingml_context.py` — imported by **4** files

## Required Environment Variables

- `ALLOW_PAID_DEPLOYED_E2E` — `src\integration\deployed-environment.test.ts`
- `API_BASE` — `src\integration\deployed-environment.test.ts`
- `AUDIO_SPLITTER_MIN_LAST_SEGMENT_SECONDS` — `agent\src\audio_splitter.py`
- `AWS_REGION` — `agent\src\lambda_renderer.py`
- `CF_NOTIFY_TOKEN` — `agent\.env.example`
- `CF_WORKER_NOTIFY_URL` — `agent\.env.example`
- `DEPLOYED_BACKEND_BEARER_TOKEN` — `src\integration\deployed-environment.test.ts`
- `DEPLOYED_BACKEND_URL` — `src\integration\deployed-environment.test.ts`
- `DEPLOYED_DIGITAL_HUMAN_AUDIO_URL` — `src\integration\deployed-environment.test.ts`
- `DEPLOYED_DIGITAL_HUMAN_AVATAR_URL` — `src\integration\deployed-environment.test.ts`
- `DEPLOYED_DIGITAL_HUMAN_DURATION` — `src\integration\deployed-environment.test.ts`
- `DEPLOYED_DIGITAL_HUMAN_POLL_INTERVAL_MS` — `src\integration\deployed-environment.test.ts`
- _...145 more_

---
_Back to [index.md](./index.md) · Generated 2026-04-08_