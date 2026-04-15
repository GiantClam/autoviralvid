import { Prisma } from "@prisma/client";
import { prisma } from "@/lib/prisma";
import { getPlanCatalog } from "@/lib/billing/plan-catalog";

export type BillingReconcileSeverity = "warning" | "critical";

export type BillingReconcileMismatch = {
  code:
    | "missing_monthly_grant"
    | "stale_precharge_usage"
    | "failed_webhook_event"
    | "negative_rolling_balance"
    | "table_missing";
  severity: BillingReconcileSeverity;
  userId?: string;
  provider?: string;
  referenceId?: string;
  detail: string;
};

export type BillingReconcileReport = {
  generatedAt: string;
  lookbackHours: number;
  summary: {
    activeSubscriptionsChecked: number;
    staleUsageRecords: number;
    failedWebhookEvents: number;
    negativeBalances: number;
    mismatches: number;
    hasCritical: boolean;
  };
  mismatches: BillingReconcileMismatch[];
};

function isMissingTableError(error: unknown): boolean {
  return (
    error instanceof Prisma.PrismaClientKnownRequestError &&
    (error.code === "P2021" || error.code === "P2022")
  );
}

function parseLookbackHours(raw?: number): number {
  if (!Number.isFinite(raw) || !raw) return 72;
  return Math.min(24 * 30, Math.max(1, Math.floor(raw)));
}

export async function runBillingReconcile(
  options?: {
    lookbackHours?: number;
    staleMinutes?: number;
  },
): Promise<BillingReconcileReport> {
  const lookbackHours = parseLookbackHours(options?.lookbackHours);
  const staleMinutes = Math.min(
    24 * 60,
    Math.max(5, Math.floor(options?.staleMinutes ?? 30)),
  );
  const now = new Date();
  const since = new Date(now.getTime() - lookbackHours * 60 * 60 * 1000);
  const staleBefore = new Date(now.getTime() - staleMinutes * 60 * 1000);
  const catalog = getPlanCatalog();

  const mismatches: BillingReconcileMismatch[] = [];
  let activeSubscriptionsChecked = 0;
  let staleUsageRecords = 0;
  let failedWebhookEvents = 0;
  let negativeBalances = 0;

  if (!process.env.DATABASE_URL) {
    mismatches.push({
      code: "table_missing",
      severity: "warning",
      detail: "DATABASE_URL is not configured. Reconcile checks are skipped.",
    });
    return {
      generatedAt: now.toISOString(),
      lookbackHours,
      summary: {
        activeSubscriptionsChecked,
        staleUsageRecords,
        failedWebhookEvents,
        negativeBalances,
        mismatches: mismatches.length,
        hasCritical: false,
      },
      mismatches,
    };
  }

  try {
    const activeSubs = await prisma.paymentSubscription.findMany({
      where: {
        status: { in: ["active", "ACTIVE"] },
      },
      select: {
        userId: true,
        provider: true,
        providerSubId: true,
        planCode: true,
        currentPeriodStart: true,
      },
      orderBy: { updatedAt: "desc" },
    });

    activeSubscriptionsChecked = activeSubs.length;

    for (const sub of activeSubs) {
      const plan = catalog[sub.planCode as keyof typeof catalog];
      if (!plan || plan.quotaTotal <= 0) continue;

      const grantSince = sub.currentPeriodStart && sub.currentPeriodStart > since
        ? sub.currentPeriodStart
        : since;

      const grantCount = await prisma.billingLedger.count({
        where: {
          userId: sub.userId,
          type: { in: ["grant", "credit"] },
          source: "subscription",
          referenceType: "monthly_grant",
          referenceId: sub.planCode,
          createdAt: { gte: grantSince },
        },
      });

      if (grantCount === 0) {
        mismatches.push({
          code: "missing_monthly_grant",
          severity: "critical",
          userId: sub.userId,
          provider: sub.provider,
          referenceId: sub.providerSubId,
          detail:
            "Active paid subscription has no monthly grant entry in the current window.",
        });
      }
    }

    const staleUsage = await prisma.billingUsageRecord.findMany({
      where: {
        status: "precharged",
        createdAt: { lte: staleBefore, gte: since },
      },
      select: {
        userId: true,
        id: true,
        endpoint: true,
      },
      take: 200,
      orderBy: { createdAt: "asc" },
    });

    staleUsageRecords = staleUsage.length;
    for (const row of staleUsage) {
      mismatches.push({
        code: "stale_precharge_usage",
        severity: "warning",
        userId: row.userId,
        referenceId: row.id,
        detail: `Usage record remains precharged beyond ${staleMinutes} minutes: ${row.endpoint}`,
      });
    }

    const failedEvents = await prisma.paymentWebhookEvent.findMany({
      where: {
        status: "failed",
        createdAt: { gte: since },
      },
      select: {
        provider: true,
        eventId: true,
        eventType: true,
      },
      orderBy: { createdAt: "desc" },
      take: 200,
    });

    failedWebhookEvents = failedEvents.length;
    for (const event of failedEvents) {
      mismatches.push({
        code: "failed_webhook_event",
        severity: "warning",
        provider: event.provider,
        referenceId: event.eventId,
        detail: `Webhook event failed: ${event.eventType}`,
      });
    }

    const recentLedger = await prisma.billingLedger.findMany({
      where: {
        createdAt: { gte: since },
      },
      select: {
        userId: true,
        type: true,
        units: true,
      },
      take: 5000,
      orderBy: { createdAt: "desc" },
    });

    const balances = new Map<string, number>();
    for (const entry of recentLedger) {
      const prev = balances.get(entry.userId) ?? 0;
      const delta = entry.type === "debit" ? -entry.units : entry.units;
      balances.set(entry.userId, prev + delta);
    }

    for (const [userId, balance] of balances.entries()) {
      if (balance < 0) {
        negativeBalances += 1;
        mismatches.push({
          code: "negative_rolling_balance",
          severity: "warning",
          userId,
          detail: `Rolling ${lookbackHours}h ledger balance is negative: ${balance}`,
        });
      }
    }
  } catch (error) {
    if (isMissingTableError(error)) {
      mismatches.push({
        code: "table_missing",
        severity: "warning",
        detail:
          "Billing tables are not fully migrated yet. Reconcile checks are partially skipped.",
      });
    } else {
      throw error;
    }
  }

  return {
    generatedAt: now.toISOString(),
    lookbackHours,
    summary: {
      activeSubscriptionsChecked,
      staleUsageRecords,
      failedWebhookEvents,
      negativeBalances,
      mismatches: mismatches.length,
      hasCritical: mismatches.some((m) => m.severity === "critical"),
    },
    mismatches,
  };
}
