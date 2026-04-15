# Production Deploy Runbook (Billing + Generation Charging)

Scope:
- Web/API proxy: Vercel (Next.js)
- Generation backend: Railway (FastAPI agent)
- Database: Supabase Postgres (Prisma)

## 1. Manual step: Supabase SQL

Run this file in Supabase SQL Editor:
- `docs/sql/2026-04-15-billing-core-supabase.sql`

Notes:
- SQL is idempotent (`IF NOT EXISTS` + guarded constraints), safe to re-run.
- Includes 5 billing tables, indexes, and foreign keys.
- File also includes an optional one-time monthly grant backfill block (commented).

## 2. Manual step: environment variables

Set these vars in production (primarily on Vercel).

Required (Vercel):
- `SUPABASE_URL`
- `AUTH_SECRET` (or `NEXTAUTH_SECRET`)
- `NEXTAUTH_URL`
- `AGENT_URL` (Railway backend URL)
- `PAYPAL_CLIENT_ID`
- `PAYPAL_CLIENT_SECRET`
- `PAYPAL_PLAN_PRO`
- `PAYPAL_PLAN_ENTERPRISE`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_PRO`
- `STRIPE_PRICE_ENTERPRISE`
- `GENERATION_BILLING_ENABLED=true`
- `BILLING_RECONCILE_TOKEN` (or `CRON_SECRET`)

Recommended (Vercel):
- `PROXY_LONG_REQUEST_TIMEOUT_MS=900000`
- `NEXT_PUBLIC_API_BASE` (usually same as `AGENT_URL`)
- `NEXT_PUBLIC_AGENT_URL` (usually same as `AGENT_URL`)
- `NEXT_PUBLIC_SITE_URL`

Railway:
- Keep existing agent runtime env vars (LLM/PPT/export pipeline).
- Keep auth secret aligned with web side JWT config.

## 3. Already automated in code

No manual code edits required for the following:
- Unified payment routes under `/api/billing/*` (Stripe + PayPal)
- Legacy PayPal routes now forward to new billing routes
- Generation charging enforced via Next proxy routes:
  - `/api/projects/[...path]`
  - `/api/ppt/[...path]`
- PPT page now uses `/api/ppt/*` instead of direct agent calls
- Webhook idempotency table is enabled
- Reconcile endpoint is enabled: `/api/internal/billing/reconcile`
- `vercel.json` already includes daily reconcile cron

## 4. Deploy order

1. Apply Supabase SQL (step 1)
2. Update Vercel/Railway env vars (step 2)
3. Deploy Vercel
4. Deploy Railway

## 5. Post-deploy verification

Run locally or in CI:

```bash
npx tsc --noEmit
npx vitest run src/lib/billing/plan-catalog.test.ts src/lib/billing/charge-policy.test.ts src/lib/billing/stripe.test.ts src/lib/billing/webhook-events.test.ts src/app/api/billing/checkout/stripe/route.test.ts src/app/api/billing/checkout/paypal/route.test.ts src/app/api/billing/webhook/stripe/route.test.ts src/app/api/billing/webhook/paypal/route.test.ts src/app/api/billing/plans/route.test.ts src/app/api/internal/billing/reconcile/route.test.ts src/app/api/ppt/[...path]/route.test.ts src/app/api/projects/[...path]/route.test.ts
```

Minimal production smoke checks:
- Pricing modal can open both Stripe and PayPal checkout links.
- One successful `/api/ppt/generate-from-prompt` call consumes quota.
- One forced downstream failure triggers automatic refund.
- `/api/internal/billing/reconcile` (with token) returns `ok: true`.
