import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { Prisma } from "@prisma/client";
import { loadEnvConfig } from "@next/env";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

loadEnvConfig(process.cwd());

function loadEnvFromFile(fileName: string) {
  const filePath = join(process.cwd(), fileName);
  if (!existsSync(filePath)) return;

  const lines = readFileSync(filePath, "utf8").split(/\r?\n/);
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const sepIndex = line.indexOf("=");
    if (sepIndex <= 0) continue;

    const key = line.slice(0, sepIndex).trim();
    if (!key || process.env[key]) continue;

    let value = line.slice(sepIndex + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    process.env[key] = value;
  }
}

if (!process.env.POSTGRES_PRISMA_URL) {
  loadEnvFromFile(".env.local");
}
if (!process.env.POSTGRES_PRISMA_URL) {
  loadEnvFromFile("agent/.env");
}

const RUN_INTEGRATION_TESTS = process.env.RUN_INTEGRATION_TESTS === "1";
const RUN_PAYPAL_SANDBOX_E2E = process.env.RUN_PAYPAL_SANDBOX_E2E === "1";

const sandboxDescribe =
  RUN_INTEGRATION_TESTS && RUN_PAYPAL_SANDBOX_E2E ? describe : describe.skip;

const authMock = vi.fn();

vi.mock("@/lib/auth", () => ({
  auth: authMock,
}));

type TestState = {
  userId: string;
  email: string;
  subscriptionId: string;
  eventPrefix: string;
};

const state: TestState = {
  userId: "",
  email: "",
  subscriptionId: "",
  eventPrefix: "",
};

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function retry<T>(action: () => Promise<T>, retries = 3, delayMs = 2_000): Promise<T> {
  let lastError: unknown;
  for (let index = 0; index < retries; index += 1) {
    try {
      return await action();
    } catch (error) {
      lastError = error;
      if (index < retries - 1) {
        await sleep(delayMs);
      }
    }
  }
  throw lastError;
}

function requireEnv(name: string) {
  const value = process.env[name]?.trim() || "";
  if (!value) {
    throw new Error(`Missing required env var: ${name}`);
  }
  return value;
}

function isMissingTableError(error: unknown): boolean {
  return (
    error instanceof Prisma.PrismaClientKnownRequestError &&
    (error.code === "P2021" || error.code === "P2022")
  );
}

async function assertBillingTablesReady() {
  const { prisma } = await import("@/lib/prisma");
  try {
    await Promise.all([
      prisma.paymentSubscription.count(),
      prisma.paymentWebhookEvent.count(),
      prisma.billingLedger.count(),
      prisma.profile.count(),
    ]);

    const profileCols = await prisma.$queryRaw<Array<{ column_name: string }>>`
      SELECT column_name
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'autoviralvid_profiles'
        AND column_name IN ('plan', 'quota_total', 'quota_used')
    `;
    const profileColumnSet = new Set(profileCols.map((row) => row.column_name));
    for (const required of ["plan", "quota_total", "quota_used"]) {
      if (!profileColumnSet.has(required)) {
        throw new Error(
          `Database schema is outdated: missing autoviralvid_profiles.${required}. ` +
            "Apply docs/sql/2026-04-15-billing-core-supabase.sql before running PayPal sandbox E2E.",
        );
      }
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (message.includes("Can't reach database server")) {
      throw new Error(
        "Database is unreachable for PayPal sandbox E2E. Check POSTGRES_PRISMA_URL network access and retry.",
      );
    }
    if (isMissingTableError(error)) {
      throw new Error(
        "Billing tables are missing. Run docs/sql/2026-04-15-billing-core-supabase.sql first.",
      );
    }
    throw error;
  }
}

async function postPaypalWebhook(payload: Record<string, unknown>) {
  const { POST } = await import("@/app/api/billing/webhook/paypal/route");
  const request = new NextRequest("http://localhost/api/billing/webhook/paypal", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  const response = await POST(request);
  const body = await response.json();
  return { response, body };
}

sandboxDescribe("PayPal sandbox billing e2e", { timeout: 120_000 }, () => {
  beforeAll(async () => {
    requireEnv("POSTGRES_PRISMA_URL");
    requireEnv("PAYPAL_CLIENT_ID");
    requireEnv("PAYPAL_CLIENT_SECRET");
    requireEnv("PAYPAL_PLAN_PRO");

    const mode = (process.env.PAYPAL_MODE || "sandbox").trim().toLowerCase();
    if (mode !== "sandbox") {
      throw new Error(`Expected PAYPAL_MODE=sandbox, got: ${mode || "unset"}`);
    }

    await retry(() => assertBillingTablesReady(), 3, 2_500);

    const runId = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    state.eventPrefix = `PAYPAL-E2E-${runId}`;
    state.email = `paypal-sandbox-e2e+${runId}@example.com`;

    const { prisma } = await import("@/lib/prisma");
    const user = await prisma.user.create({
      data: { email: state.email },
      select: { id: true },
    });
    state.userId = user.id;

    await prisma.profile.create({
      data: {
        userId: state.userId,
        is_allowed: true,
        plan: "free",
        quota_total: 3,
        quota_used: 0,
        quota_reset: new Date(),
      },
    });

    authMock.mockResolvedValue({ user: { id: state.userId, email: state.email } });
  }, 120_000);

  beforeEach(() => {
    authMock.mockResolvedValue({ user: { id: state.userId, email: state.email } });
  });

  afterAll(async () => {
    if (!process.env.POSTGRES_PRISMA_URL) {
      return;
    }
    if (!state.userId) {
      return;
    }

    const { prisma } = await import("@/lib/prisma");

    if (state.subscriptionId) {
      try {
        const { cancelSubscription } = await import("@/lib/paypal");
        await cancelSubscription(state.subscriptionId, "integration test cleanup");
      } catch {
        // no-op
      }
    }

    try {
      await prisma.billingUsageRecord.deleteMany({ where: { userId: state.userId } });
      await prisma.billingLedger.deleteMany({ where: { userId: state.userId } });
      await prisma.paymentSubscription.deleteMany({ where: { userId: state.userId } });
      await prisma.paymentCustomer.deleteMany({ where: { userId: state.userId } });
      await prisma.subscription.deleteMany({ where: { userId: state.userId } });
      await prisma.profile.deleteMany({ where: { userId: state.userId } });
      await prisma.paymentWebhookEvent.deleteMany({
        where: {
          provider: "paypal",
          eventId: {
            startsWith: state.eventPrefix,
          },
        },
      });
      await prisma.user.deleteMany({ where: { id: state.userId } });
    } catch {
      // no-op
    }
  }, 120_000);

  it("creates sandbox checkout and returns approval url", async () => {
    const { POST } = await import("@/app/api/billing/checkout/paypal/route");

    const request = new NextRequest("http://localhost/api/billing/checkout/paypal", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        origin: "http://localhost",
      },
      body: JSON.stringify({ plan: "pro" }),
    });

    const response = await POST(request);
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.provider).toBe("paypal");
    expect(payload.subscriptionId).toEqual(expect.any(String));
    expect(payload.subscriptionId.length).toBeGreaterThan(6);
    expect(payload.url).toMatch(/^https:\/\/.*paypal\.com\//i);

    state.subscriptionId = String(payload.subscriptionId);
  });

  it("handles activation webhook and upgrades subscription/profile", async () => {
    expect(state.subscriptionId).toBeTruthy();

    const eventId = `${state.eventPrefix}-activated`;
    const periodEnd = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString();
    const payload = {
      id: eventId,
      event_type: "BILLING.SUBSCRIPTION.ACTIVATED",
      resource: {
        id: state.subscriptionId,
        plan_id: process.env.PAYPAL_PLAN_PRO,
        custom_id: state.userId,
        subscriber: { email_address: state.email },
        billing_info: {
          next_billing_time: periodEnd,
        },
      },
    };

    const result = await postPaypalWebhook(payload);
    expect(result.response.status).toBe(200);
    expect(result.body.received).toBe(true);
    expect(result.body.duplicate).not.toBe(true);

    const { prisma } = await import("@/lib/prisma");

    const paymentSub = await prisma.paymentSubscription.findUnique({
      where: {
        provider_providerSubId: {
          provider: "paypal",
          providerSubId: state.subscriptionId,
        },
      },
    });
    expect(paymentSub?.userId).toBe(state.userId);
    expect(paymentSub?.planCode).toBe("pro");
    expect(paymentSub?.status).toBe("active");

    const legacySub = await prisma.subscription.findUnique({
      where: { userId: state.userId },
    });
    expect(legacySub?.paypalSubId).toBe(state.subscriptionId);
    expect(legacySub?.plan).toBe("pro");
    expect(legacySub?.status).toBe("active");

    const profile = await prisma.profile.findUnique({
      where: { userId: state.userId },
    });
    expect(profile?.plan).toBe("pro");
    expect(profile?.quota_total).toBe(30);
    expect(profile?.quota_used).toBe(0);
  });

  it("deduplicates webhook replay by event id", async () => {
    const duplicatedEventId = `${state.eventPrefix}-activated`;
    const payload = {
      id: duplicatedEventId,
      event_type: "BILLING.SUBSCRIPTION.ACTIVATED",
      resource: {
        id: state.subscriptionId,
        plan_id: process.env.PAYPAL_PLAN_PRO,
        custom_id: state.userId,
      },
    };

    const result = await postPaypalWebhook(payload);
    expect(result.response.status).toBe(200);
    expect(result.body).toEqual({ received: true, duplicate: true });
  });

  it("resets used quota when payment sale completed webhook arrives", async () => {
    const { prisma } = await import("@/lib/prisma");
    await prisma.profile.update({
      where: { userId: state.userId },
      data: {
        plan: "pro",
        quota_total: 30,
        quota_used: 9,
      },
    });

    const eventId = `${state.eventPrefix}-sale-completed`;
    const payload = {
      id: eventId,
      event_type: "PAYMENT.SALE.COMPLETED",
      resource: {
        id: state.subscriptionId,
        plan_id: process.env.PAYPAL_PLAN_PRO,
        custom_id: state.userId,
      },
    };

    const result = await postPaypalWebhook(payload);
    expect(result.response.status).toBe(200);
    expect(result.body.received).toBe(true);

    const profile = await prisma.profile.findUnique({
      where: { userId: state.userId },
    });
    expect(profile?.plan).toBe("pro");
    expect(profile?.quota_total).toBe(30);
    expect(profile?.quota_used).toBe(0);
  });

  it("downgrades to free after cancellation webhook", async () => {
    const eventId = `${state.eventPrefix}-cancelled`;
    const payload = {
      id: eventId,
      event_type: "BILLING.SUBSCRIPTION.CANCELLED",
      resource: {
        id: state.subscriptionId,
        plan_id: process.env.PAYPAL_PLAN_PRO,
        custom_id: state.userId,
      },
    };

    const result = await postPaypalWebhook(payload);
    expect(result.response.status).toBe(200);
    expect(result.body.received).toBe(true);

    const { prisma } = await import("@/lib/prisma");
    const paymentSub = await prisma.paymentSubscription.findUnique({
      where: {
        provider_providerSubId: {
          provider: "paypal",
          providerSubId: state.subscriptionId,
        },
      },
    });
    expect(paymentSub?.status).toBe("cancelled");

    const legacySub = await prisma.subscription.findUnique({
      where: { userId: state.userId },
    });
    expect(legacySub?.plan).toBe("free");
    expect(legacySub?.status).toBe("cancelled");

    const profile = await prisma.profile.findUnique({
      where: { userId: state.userId },
    });
    expect(profile?.plan).toBe("free");
    expect(profile?.quota_total).toBe(3);
  });
});
