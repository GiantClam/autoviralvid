# Billing Reconcile Runbook

## Purpose

Daily verify billing consistency across:

- `PaymentSubscription` (subscription source of truth)
- `PaymentWebhookEvent` (event processing health)
- `BillingUsageRecord` (precharge lifecycle)
- `BillingLedger` (auditable debit/credit ledger)

## Route

- Internal API: `GET /api/internal/billing/reconcile`
- Auth token:
  - Preferred: `BILLING_RECONCILE_TOKEN`
  - Fallback: `CRON_SECRET`
- Provide token by one of:
  - `Authorization: Bearer <token>`
  - `x-internal-token: <token>`
  - `?token=<token>` (for constrained environments)

## Manual Run

```bash
npm run billing:reconcile -- --lookbackHours=72 --staleMinutes=30
```

JSON output:

```bash
npm run billing:reconcile -- --json
```

## Vercel Cron

Add `vercel.json`:

```json
{
  "crons": [
    {
      "path": "/api/internal/billing/reconcile?lookbackHours=72&staleMinutes=30",
      "schedule": "0 3 * * *"
    }
  ]
}
```

Set one of:

- `BILLING_RECONCILE_TOKEN=<secret>`
- or `CRON_SECRET=<secret>`

## Alert Semantics

The API returns:

- `alert: true` when there is any mismatch.
- `report.summary.hasCritical: true` when critical mismatch exists.

Critical mismatch examples:

- Active paid subscription has no matching monthly grant in the current period.

Warning mismatch examples:

- Stale `precharged` usage record not committed/refunded.
- Failed webhook events in lookback window.
- Negative rolling ledger balance in lookback window.

## Investigation Checklist

1. Check failed webhook events first and replay affected events.
2. For stale usage records, inspect generation proxy logs and downstream completion callbacks.
3. For missing grants, verify provider event order and plan mapping IDs.
4. For negative balances, validate if this is expected due to delayed grant or refund lag.

## Recovery Actions

1. Replay failed webhook event (manual endpoint or script, if enabled in your environment).
2. Backfill monthly grant:
   - write `BillingLedger(type=grant, source=subscription, referenceType=monthly_grant)`.
3. Refund orphan precharge:
   - set usage status to `refunded`
   - add `BillingLedger(type=refund, source=api_usage)`.

