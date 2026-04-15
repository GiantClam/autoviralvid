-- Billing core rollout for Supabase/Postgres
-- Safe to run multiple times (idempotent DDL).

BEGIN;

CREATE TABLE IF NOT EXISTS "autoviralvid_payment_customers" (
  "id" TEXT NOT NULL,
  "userId" TEXT NOT NULL,
  "provider" TEXT NOT NULL,
  "providerCustomerId" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "autoviralvid_payment_customers_pkey" PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "autoviralvid_payment_subscriptions" (
  "id" TEXT NOT NULL,
  "userId" TEXT NOT NULL,
  "provider" TEXT NOT NULL,
  "providerSubId" TEXT NOT NULL,
  "planCode" TEXT NOT NULL DEFAULT 'free',
  "status" TEXT NOT NULL DEFAULT 'active',
  "currentPeriodStart" TIMESTAMP(3),
  "currentPeriodEnd" TIMESTAMP(3),
  "cancelAtPeriodEnd" BOOLEAN NOT NULL DEFAULT false,
  "metadata" JSONB,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "autoviralvid_payment_subscriptions_pkey" PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "autoviralvid_payment_webhook_events" (
  "id" TEXT NOT NULL,
  "provider" TEXT NOT NULL,
  "eventId" TEXT NOT NULL,
  "eventType" TEXT NOT NULL,
  "payloadHash" TEXT,
  "status" TEXT NOT NULL DEFAULT 'processing',
  "processedAt" TIMESTAMP(3),
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "autoviralvid_payment_webhook_events_pkey" PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "autoviralvid_billing_ledger" (
  "id" TEXT NOT NULL,
  "userId" TEXT NOT NULL,
  "type" TEXT NOT NULL,
  "units" INTEGER NOT NULL,
  "source" TEXT NOT NULL,
  "referenceType" TEXT,
  "referenceId" TEXT,
  "idempotencyKey" TEXT,
  "metadata" JSONB,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "autoviralvid_billing_ledger_pkey" PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "autoviralvid_billing_usage_records" (
  "id" TEXT NOT NULL,
  "userId" TEXT NOT NULL,
  "endpoint" TEXT NOT NULL,
  "method" TEXT NOT NULL,
  "units" INTEGER NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'precharged',
  "requestId" TEXT,
  "runId" TEXT,
  "providerTraceId" TEXT,
  "idempotencyKey" TEXT,
  "metadata" JSONB,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "autoviralvid_billing_usage_records_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "autoviralvid_payment_customers_userId_provider_idx"
  ON "autoviralvid_payment_customers"("userId", "provider");
CREATE UNIQUE INDEX IF NOT EXISTS "autoviralvid_payment_customers_provider_providerCustomerId_key"
  ON "autoviralvid_payment_customers"("provider", "providerCustomerId");

CREATE INDEX IF NOT EXISTS "autoviralvid_payment_subscriptions_userId_provider_idx"
  ON "autoviralvid_payment_subscriptions"("userId", "provider");
CREATE UNIQUE INDEX IF NOT EXISTS "autoviralvid_payment_subscriptions_provider_providerSubId_key"
  ON "autoviralvid_payment_subscriptions"("provider", "providerSubId");

CREATE INDEX IF NOT EXISTS "autoviralvid_payment_webhook_events_provider_status_idx"
  ON "autoviralvid_payment_webhook_events"("provider", "status");
CREATE UNIQUE INDEX IF NOT EXISTS "autoviralvid_payment_webhook_events_provider_eventId_key"
  ON "autoviralvid_payment_webhook_events"("provider", "eventId");

CREATE UNIQUE INDEX IF NOT EXISTS "autoviralvid_billing_ledger_idempotencyKey_key"
  ON "autoviralvid_billing_ledger"("idempotencyKey");
CREATE INDEX IF NOT EXISTS "autoviralvid_billing_ledger_userId_createdAt_idx"
  ON "autoviralvid_billing_ledger"("userId", "createdAt");
CREATE INDEX IF NOT EXISTS "autoviralvid_billing_ledger_source_referenceType_referenceI_idx"
  ON "autoviralvid_billing_ledger"("source", "referenceType", "referenceId");

CREATE UNIQUE INDEX IF NOT EXISTS "autoviralvid_billing_usage_records_idempotencyKey_key"
  ON "autoviralvid_billing_usage_records"("idempotencyKey");
CREATE INDEX IF NOT EXISTS "autoviralvid_billing_usage_records_userId_status_createdAt_idx"
  ON "autoviralvid_billing_usage_records"("userId", "status", "createdAt");
CREATE INDEX IF NOT EXISTS "autoviralvid_billing_usage_records_endpoint_method_createdA_idx"
  ON "autoviralvid_billing_usage_records"("endpoint", "method", "createdAt");

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'autoviralvid_payment_customers_userId_fkey'
  ) THEN
    ALTER TABLE "autoviralvid_payment_customers"
      ADD CONSTRAINT "autoviralvid_payment_customers_userId_fkey"
      FOREIGN KEY ("userId") REFERENCES "autoviralvid_users"("id")
      ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'autoviralvid_payment_subscriptions_userId_fkey'
  ) THEN
    ALTER TABLE "autoviralvid_payment_subscriptions"
      ADD CONSTRAINT "autoviralvid_payment_subscriptions_userId_fkey"
      FOREIGN KEY ("userId") REFERENCES "autoviralvid_users"("id")
      ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'autoviralvid_billing_ledger_userId_fkey'
  ) THEN
    ALTER TABLE "autoviralvid_billing_ledger"
      ADD CONSTRAINT "autoviralvid_billing_ledger_userId_fkey"
      FOREIGN KEY ("userId") REFERENCES "autoviralvid_users"("id")
      ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'autoviralvid_billing_usage_records_userId_fkey'
  ) THEN
    ALTER TABLE "autoviralvid_billing_usage_records"
      ADD CONSTRAINT "autoviralvid_billing_usage_records_userId_fkey"
      FOREIGN KEY ("userId") REFERENCES "autoviralvid_users"("id")
      ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;
END $$;

COMMIT;

-- Optional one-time backfill for already-active paid subscribers.
-- Uncomment and run once if you want an initial monthly_grant ledger entry.
--
-- INSERT INTO "autoviralvid_billing_ledger" (
--   "id",
--   "userId",
--   "type",
--   "units",
--   "source",
--   "referenceType",
--   "referenceId",
--   "idempotencyKey",
--   "metadata",
--   "createdAt"
-- )
-- SELECT
--   'bootstrap_' || md5(s."userId" || ':' || s."plan" || ':2026-04'),
--   s."userId",
--   'grant',
--   CASE
--     WHEN p."quota_total" > 0 THEN p."quota_total"
--     WHEN s."plan" = 'pro' THEN 30
--     ELSE 0
--   END,
--   'subscription',
--   'monthly_grant',
--   s."plan",
--   'bootstrap:monthly-grant:' || s."userId" || ':' || s."plan" || ':2026-04',
--   '{"source":"bootstrap"}'::jsonb,
--   NOW()
-- FROM "autoviralvid_subscriptions" s
-- JOIN "autoviralvid_profiles" p ON p."userId" = s."userId"
-- WHERE lower(coalesce(s."status", '')) = 'active'
--   AND s."plan" IN ('pro', 'enterprise')
--   AND p."quota_total" > 0
-- ON CONFLICT ("idempotencyKey") DO NOTHING;
