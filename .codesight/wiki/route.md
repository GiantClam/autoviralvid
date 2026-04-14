# Route

> **Navigation aid.** Route list and file locations extracted via AST. Read the source files listed below before implementing or modifying this subsystem.

The Route subsystem handles **12 routes** and touches: auth, db, cache.

## Routes

- `POST` `/api/agent/regenerate/[run_id]` params(run_id) → out: { error }
  `src/app/api/agent/regenerate/[run_id]/route.ts`
- `POST` `/api/agent/retry/[run_id]` params(run_id) → out: { error }
  `src/app/api/agent/retry/[run_id]/route.ts`
- `POST` `/api/agent/stitch/[run_id]` params(run_id) → out: { error }
  `src/app/api/agent/stitch/[run_id]/route.ts`
- `GET` `/api/agent/tasks/[run_id]` params(run_id) → out: { error }
  `src/app/api/agent/tasks/[run_id]/route.ts`
- `POST` `/api/paypal/create-subscription` → out: { error } [auth]
  `src/app/api/paypal/create-subscription/route.ts`
- `GET` `/api/paypal/subscription-status` → out: { error } [auth, db]
  `src/app/api/paypal/subscription-status/route.ts`
- `GET` `/api/projects/[...path]` → out: { error } [auth, cache]
  `src/app/api/projects/[...path]/route.ts`
- `POST` `/api/projects/[...path]` → out: { error } [auth, cache]
  `src/app/api/projects/[...path]/route.ts`
- `PUT` `/api/projects/[...path]` → out: { error } [auth, cache]
  `src/app/api/projects/[...path]/route.ts`
- `DELETE` `/api/projects/[...path]` → out: { error } [auth, cache]
  `src/app/api/projects/[...path]/route.ts`
- `GET` `/api/quota` → out: { error } [auth]
  `src/app/api/quota/route.ts`
- `POST` `/api/render/jobs` → out: { error }
  `src/app/api/render/jobs/route.ts`

## Source Files

Read these before implementing or modifying this subsystem:
- `src/app/api/agent/regenerate/[run_id]/route.ts`
- `src/app/api/agent/retry/[run_id]/route.ts`
- `src/app/api/agent/stitch/[run_id]/route.ts`
- `src/app/api/agent/tasks/[run_id]/route.ts`
- `src/app/api/paypal/create-subscription/route.ts`
- `src/app/api/paypal/subscription-status/route.ts`
- `src/app/api/projects/[...path]/route.ts`
- `src/app/api/quota/route.ts`
- `src/app/api/render/jobs/route.ts`

---
_Back to [overview.md](./overview.md)_