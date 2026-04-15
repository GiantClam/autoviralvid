-- CreateTable
CREATE TABLE "autoviralvid_payment_customers" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "provider" TEXT NOT NULL,
    "providerCustomerId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "autoviralvid_payment_customers_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "autoviralvid_payment_subscriptions" (
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

-- CreateTable
CREATE TABLE "autoviralvid_payment_webhook_events" (
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

-- CreateTable
CREATE TABLE "autoviralvid_billing_ledger" (
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

-- CreateTable
CREATE TABLE "autoviralvid_billing_usage_records" (
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

-- CreateIndex
CREATE INDEX "autoviralvid_payment_customers_userId_provider_idx" ON "autoviralvid_payment_customers"("userId", "provider");

-- CreateIndex
CREATE UNIQUE INDEX "autoviralvid_payment_customers_provider_providerCustomerId_key" ON "autoviralvid_payment_customers"("provider", "providerCustomerId");

-- CreateIndex
CREATE INDEX "autoviralvid_payment_subscriptions_userId_provider_idx" ON "autoviralvid_payment_subscriptions"("userId", "provider");

-- CreateIndex
CREATE UNIQUE INDEX "autoviralvid_payment_subscriptions_provider_providerSubId_key" ON "autoviralvid_payment_subscriptions"("provider", "providerSubId");

-- CreateIndex
CREATE INDEX "autoviralvid_payment_webhook_events_provider_status_idx" ON "autoviralvid_payment_webhook_events"("provider", "status");

-- CreateIndex
CREATE UNIQUE INDEX "autoviralvid_payment_webhook_events_provider_eventId_key" ON "autoviralvid_payment_webhook_events"("provider", "eventId");

-- CreateIndex
CREATE UNIQUE INDEX "autoviralvid_billing_ledger_idempotencyKey_key" ON "autoviralvid_billing_ledger"("idempotencyKey");

-- CreateIndex
CREATE INDEX "autoviralvid_billing_ledger_userId_createdAt_idx" ON "autoviralvid_billing_ledger"("userId", "createdAt");

-- CreateIndex
CREATE INDEX "autoviralvid_billing_ledger_source_referenceType_referenceI_idx" ON "autoviralvid_billing_ledger"("source", "referenceType", "referenceId");

-- CreateIndex
CREATE UNIQUE INDEX "autoviralvid_billing_usage_records_idempotencyKey_key" ON "autoviralvid_billing_usage_records"("idempotencyKey");

-- CreateIndex
CREATE INDEX "autoviralvid_billing_usage_records_userId_status_createdAt_idx" ON "autoviralvid_billing_usage_records"("userId", "status", "createdAt");

-- CreateIndex
CREATE INDEX "autoviralvid_billing_usage_records_endpoint_method_createdA_idx" ON "autoviralvid_billing_usage_records"("endpoint", "method", "createdAt");

-- AddForeignKey
ALTER TABLE "autoviralvid_payment_customers" ADD CONSTRAINT "autoviralvid_payment_customers_userId_fkey" FOREIGN KEY ("userId") REFERENCES "autoviralvid_users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "autoviralvid_payment_subscriptions" ADD CONSTRAINT "autoviralvid_payment_subscriptions_userId_fkey" FOREIGN KEY ("userId") REFERENCES "autoviralvid_users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "autoviralvid_billing_ledger" ADD CONSTRAINT "autoviralvid_billing_ledger_userId_fkey" FOREIGN KEY ("userId") REFERENCES "autoviralvid_users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "autoviralvid_billing_usage_records" ADD CONSTRAINT "autoviralvid_billing_usage_records_userId_fkey" FOREIGN KEY ("userId") REFERENCES "autoviralvid_users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

