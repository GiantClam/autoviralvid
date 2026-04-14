# Auth

> **Navigation aid.** Route list and file locations extracted via AST. Read the source files listed below before implementing or modifying this subsystem.

The Auth subsystem handles **3 routes** and touches: auth, cache, db.

## Routes

- `POST` `/api/auth/api-token` → out: { error } [auth, cache]
  `src/app/api/auth/api-token/route.ts`
- `POST` `/api/auth/forgot-password` → out: { error } [auth, db]
  `src/app/api/auth/forgot-password/route.ts`
- `POST` `/api/auth/reset-password` → out: { error } [auth, db]
  `src/app/api/auth/reset-password/route.ts`

## Middleware

- **auth** (auth) — `agent\src\auth.py`
- **rate_limiter** (auth) — `agent\src\rate_limiter.py`
- **auth** (auth) — `src\lib\auth.ts`

## Source Files

Read these before implementing or modifying this subsystem:
- `src/app/api/auth/api-token/route.ts`
- `src/app/api/auth/forgot-password/route.ts`
- `src/app/api/auth/reset-password/route.ts`

---
_Back to [overview.md](./overview.md)_