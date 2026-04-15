import { Prisma } from "@prisma/client";
import { prisma } from "@/lib/prisma";
import { checkQuota } from "@/lib/quota";
import { getPlanCatalog } from "@/lib/billing/plan-catalog";
import { getBillingBalance, getRecentBillingLedgerEntries } from "@/lib/billing/ledger";

function isMissingTableError(error: unknown): boolean {
  if (
    error instanceof Prisma.PrismaClientKnownRequestError &&
    (error.code === "P2021" || error.code === "P2022")
  ) {
    return true;
  }
  return false;
}

export type BillingSubscriptionView = {
  provider: "paypal" | "stripe" | "legacy";
  providerSubId: string | null;
  planCode: string;
  status: string;
  currentPeriodStart: Date | null;
  currentPeriodEnd: Date | null;
  cancelAtPeriodEnd: boolean;
  metadata?: unknown;
  updatedAt?: Date | null;
};

export type BillingSnapshot = {
  plan: string;
  planName: string;
  price: number;
  features: string[];
  quota: Awaited<ReturnType<typeof checkQuota>>;
  balance: number;
  subscriptions: BillingSubscriptionView[];
  primarySubscription: BillingSubscriptionView | null;
  recentLedger: Awaited<ReturnType<typeof getRecentBillingLedgerEntries>>;
};

async function getPaymentSubscriptions(userId: string): Promise<BillingSubscriptionView[]> {
  try {
    const rows = await prisma.paymentSubscription.findMany({
      where: { userId },
      orderBy: { updatedAt: "desc" },
    });
    return rows.map((row) => ({
      provider: row.provider === "stripe" ? "stripe" : "paypal",
      providerSubId: row.providerSubId,
      planCode: row.planCode,
      status: row.status,
      currentPeriodStart: row.currentPeriodStart ?? null,
      currentPeriodEnd: row.currentPeriodEnd ?? null,
      cancelAtPeriodEnd: row.cancelAtPeriodEnd,
      metadata: row.metadata,
      updatedAt: row.updatedAt,
    }));
  } catch (error) {
    if (isMissingTableError(error)) return [];
    throw error;
  }
}

async function getLegacySubscription(userId: string): Promise<BillingSubscriptionView | null> {
  const legacy = await prisma.subscription.findUnique({
    where: { userId },
  });
  if (!legacy) return null;
  return {
    provider: "legacy",
    providerSubId: legacy.paypalSubId,
    planCode: legacy.plan,
    status: legacy.status,
    currentPeriodStart: null,
    currentPeriodEnd: legacy.currentPeriodEnd ?? null,
    cancelAtPeriodEnd: false,
    metadata: null,
    updatedAt: legacy.updatedAt,
  };
}

function resolvePrimarySubscription(
  paymentSubs: BillingSubscriptionView[],
  legacy: BillingSubscriptionView | null,
): BillingSubscriptionView | null {
  if (paymentSubs.length > 0) {
    return paymentSubs[0] ?? null;
  }
  return legacy;
}

export async function getBillingSnapshot(userId: string): Promise<BillingSnapshot> {
  const quota = await checkQuota(userId);
  const catalog = getPlanCatalog();
  const paymentSubs = await getPaymentSubscriptions(userId);
  const legacySub = await getLegacySubscription(userId);
  const primary = resolvePrimarySubscription(paymentSubs, legacySub);

  const planCode = primary?.planCode || quota.plan || "free";
  const planConfig = catalog[planCode as keyof typeof catalog] || catalog.free;
  const balance = await getBillingBalance(userId);
  const recentLedger = await getRecentBillingLedgerEntries(userId, 20);

  const subscriptions = [...paymentSubs];
  if (legacySub) {
    const duplicated = subscriptions.some(
      (sub) =>
        sub.provider === "paypal" &&
        sub.providerSubId &&
        sub.providerSubId === legacySub.providerSubId,
    );
    if (!duplicated) {
      subscriptions.push(legacySub);
    }
  }

  return {
    plan: planConfig.code,
    planName: planConfig.name,
    price: planConfig.price,
    features: planConfig.features,
    quota,
    balance,
    subscriptions,
    primarySubscription: primary,
    recentLedger,
  };
}

