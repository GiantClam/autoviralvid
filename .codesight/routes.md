# Routes

- `POST` `/api/agent/regenerate/[run_id]` params(run_id) → out: { error }
- `POST` `/api/agent/retry/[run_id]` params(run_id) → out: { error }
- `POST` `/api/agent/stitch/[run_id]` params(run_id) → out: { error }
- `GET` `/api/agent/tasks/[run_id]` params(run_id) → out: { error }
- `POST` `/api/auth/api-token` → out: { error } [auth, cache]
- `POST` `/api/auth/forgot-password` → out: { error } [auth, db]
- `POST` `/api/auth/reset-password` → out: { error } [auth, db]
- `POST` `/api/paypal/create-subscription` → out: { error } [auth]
- `GET` `/api/paypal/subscription-status` → out: { error } [auth, db]
- `POST` `/api/paypal/webhook` → out: { received } [db, payment]
- `GET` `/api/projects/[...path]` → out: { error } [auth, cache]
- `POST` `/api/projects/[...path]` → out: { error } [auth, cache]
- `PUT` `/api/projects/[...path]` → out: { error } [auth, cache]
- `DELETE` `/api/projects/[...path]` → out: { error } [auth, cache]
- `GET` `/api/quota` → out: { error } [auth]
- `POST` `/api/render/jobs` → out: { error }
