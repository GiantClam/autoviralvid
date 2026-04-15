import { Prisma } from "@prisma/client";
import { prisma } from "@/lib/prisma";
import { getPlanCatalog } from "./plan-catalog";

type LedgerEntryInput = {
  userId: string;
  type: "debit" | "credit" | "refund" | "grant";
  units: number;
  source: "api_usage" | "subscription" | "manual";
  referenceType?: string;
  referenceId?: string;
  idempotencyKey?: string;
  metadata?: Record<string, unknown>;
};

function normalizeUnits(units: number): number {
  if (!Number.isFinite(units)) return 0;
  return Math.max(0, Math.floor(units));
}

function isMissingTableError(error: unknown): boolean {
  if (
    error instanceof Prisma.PrismaClientKnownRequestError &&
    (error.code === "P2021" || error.code === "P2022")
  ) {
    return true;
  }
  return false;
}

export function isBillingTableMissingError(error: unknown): boolean {
  return isMissingTableError(error);
}

export async function appendBillingLedgerEntry(input: LedgerEntryInput) {
  const units = normalizeUnits(input.units);
  if (!input.userId || units <= 0) return null;

  try {
    return await prisma.billingLedger.create({
      data: {
        userId: input.userId,
        type: input.type,
        units,
        source: input.source,
        referenceType: input.referenceType,
        referenceId: input.referenceId,
        idempotencyKey: input.idempotencyKey,
        metadata: input.metadata ? (input.metadata as Prisma.InputJsonValue) : undefined,
      },
    });
  } catch (error) {
    if (
      error instanceof Prisma.PrismaClientKnownRequestError &&
      error.code === "P2002" &&
      input.idempotencyKey
    ) {
      return prisma.billingLedger.findUnique({
        where: { idempotencyKey: input.idempotencyKey },
      });
    }
    if (isMissingTableError(error)) {
      return null;
    }
    throw error;
  }
}

export async function recordUsageDebit(
  userId: string,
  units: number,
  metadata?: Record<string, unknown>,
) {
  return appendBillingLedgerEntry({
    userId,
    type: "debit",
    units,
    source: "api_usage",
    referenceType: "usage",
    metadata,
  });
}

export async function recordUsageRefund(
  userId: string,
  units: number,
  metadata?: Record<string, unknown>,
) {
  return appendBillingLedgerEntry({
    userId,
    type: "refund",
    units,
    source: "api_usage",
    referenceType: "usage_refund",
    metadata,
  });
}

export async function recordPlanGrant(
  userId: string,
  planCode: string,
  idempotencyKey?: string,
  metadata?: Record<string, unknown>,
) {
  const plan = getPlanCatalog()[planCode as keyof ReturnType<typeof getPlanCatalog>];
  if (!plan || plan.quotaTotal <= 0) return null;
  return appendBillingLedgerEntry({
    userId,
    type: "grant",
    units: plan.quotaTotal,
    source: "subscription",
    referenceType: "monthly_grant",
    referenceId: planCode,
    idempotencyKey,
    metadata,
  });
}

export async function getBillingBalance(userId: string): Promise<number> {
  if (!userId) return 0;
  try {
    const rows = await prisma.billingLedger.findMany({
      where: { userId },
      select: {
        type: true,
        units: true,
      },
    });
    let balance = 0;
    for (const row of rows) {
      if (row.type === "debit") {
        balance -= row.units;
      } else {
        balance += row.units;
      }
    }
    return balance;
  } catch (error) {
    if (isMissingTableError(error)) return 0;
    throw error;
  }
}

export async function getRecentBillingLedgerEntries(userId: string, limit = 20) {
  if (!userId) return [];
  try {
    return await prisma.billingLedger.findMany({
      where: { userId },
      orderBy: { createdAt: "desc" },
      take: Math.max(1, Math.min(100, limit)),
      select: {
        id: true,
        type: true,
        units: true,
        source: true,
        referenceType: true,
        referenceId: true,
        metadata: true,
        createdAt: true,
      },
    });
  } catch (error) {
    if (isMissingTableError(error)) return [];
    throw error;
  }
}
