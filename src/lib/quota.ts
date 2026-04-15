/**
 * Quota management helpers.
 *
 * Checks and consumes video generation quotas per user.
 */

import type { Prisma } from "@prisma/client";
import { prisma } from "./prisma";
import { PLANS } from "./paypal";
import { recordPlanGrant, recordUsageDebit, recordUsageRefund } from "./billing/ledger";

export interface QuotaInfo {
  allowed: boolean;
  remaining: number;
  total: number;
  used: number;
  plan: string;
}

type ProfileLite = {
  userId: string;
  plan: string;
  quota_total: number;
  quota_used: number;
  quota_reset: Date | null;
};

const DEFAULT_FREE_TOTAL = 3;

function normalizeUnits(units: number): number {
  if (!Number.isFinite(units)) return 1;
  return Math.max(1, Math.floor(units));
}

/**
 * Check whether the user has remaining quota.
 */
export async function checkQuota(userId: string): Promise<QuotaInfo> {
  const profile = await ensureProfile(userId);
  const refreshed = await resetIfNeeded(profile);

  const plan = refreshed.plan || "free";
  const total = resolvePlanQuotaTotal(plan, refreshed.quota_total);

  if (total === -1) {
    return { allowed: true, remaining: -1, total: -1, used: refreshed.quota_used, plan };
  }

  const remaining = Math.max(0, total - refreshed.quota_used);
  return {
    allowed: remaining > 0,
    remaining,
    total,
    used: refreshed.quota_used,
    plan,
  };
}

/**
 * Consume one unit of quota. Returns false if quota exceeded.
 * Uses atomic update to avoid concurrent over-consumption.
 */
export async function consumeQuota(userId: string, units = 1): Promise<boolean> {
  const normalizedUnits = normalizeUnits(units);
  const profile = await ensureProfile(userId);
  const refreshed = await resetIfNeeded(profile);

  const plan = refreshed.plan || "free";
  const total = resolvePlanQuotaTotal(plan, refreshed.quota_total);

  if (total === -1) {
    return true;
  }

  if (total < normalizedUnits) {
    return false;
  }

  const updated = await prisma.profile.updateMany({
    where: {
      userId,
      quota_used: { lte: total - normalizedUnits },
    },
    data: {
      quota_used: { increment: normalizedUnits },
    },
  });

  const succeeded = updated.count > 0;
  if (succeeded) {
    await recordUsageDebit(userId, normalizedUnits, {
      source: "quota.consume",
    }).catch(() => undefined);
  }
  return succeeded;
}

/**
 * Roll back one quota unit (used when pre-charged request fails).
 */
export async function refundQuota(userId: string, units = 1): Promise<void> {
  const normalizedUnits = normalizeUnits(units);
  const profile = await prisma.profile.findUnique({
    where: { userId },
    select: {
      quota_used: true,
    },
  });
  if (!profile?.quota_used) return;

  const decrement = Math.min(normalizedUnits, profile.quota_used);
  if (decrement <= 0) return;

  await prisma.profile.update({
    where: { userId },
    data: {
      quota_used: { decrement },
    },
  });

  await recordUsageRefund(userId, decrement, {
    source: "quota.refund",
  }).catch(() => undefined);
}

/**
 * Reset quota for a user (called on subscription renewal).
 */
export async function resetMonthlyQuota(userId: string, plan?: string): Promise<void> {
  const planConfig = plan ? PLANS[plan] : undefined;
  const updates: Prisma.ProfileUpdateInput = {
    quota_used: 0,
    quota_reset: getNextResetDate(),
  };

  if (planConfig) {
    updates.plan = plan;
    updates.quota_total = planConfig.quotaTotal;
  }

  await prisma.profile.update({ where: { userId }, data: updates });
  await recordPlanGrant(
    userId,
    updates.plan ? String(updates.plan) : plan || "free",
    `quota-reset:${userId}:${updates.plan ? String(updates.plan) : plan || "free"}:${new Date().toISOString().slice(0, 7)}`,
    {
      source: "quota.reset",
    },
  ).catch(() => undefined);
}

function getNextResetDate(): Date {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth() + 1, 1);
}

function resolvePlanQuotaTotal(plan: string, profileQuotaTotal: number): number {
  const planConfig = PLANS[plan];
  return planConfig?.quotaTotal ?? profileQuotaTotal;
}

async function ensureProfile(userId: string): Promise<ProfileLite> {
  const existing = await prisma.profile.findUnique({
    where: { userId },
    select: {
      userId: true,
      plan: true,
      quota_total: true,
      quota_used: true,
      quota_reset: true,
    },
  });
  if (existing) return existing;

  return prisma.profile.create({
    data: {
      userId,
      plan: "free",
      quota_total: DEFAULT_FREE_TOTAL,
      quota_used: 0,
      quota_reset: getNextResetDate(),
    },
    select: {
      userId: true,
      plan: true,
      quota_total: true,
      quota_used: true,
      quota_reset: true,
    },
  });
}

async function resetIfNeeded(profile: ProfileLite): Promise<ProfileLite> {
  if (!profile.quota_reset || new Date() <= profile.quota_reset) {
    return profile;
  }

  return prisma.profile.update({
    where: { userId: profile.userId },
    data: {
      quota_used: 0,
      quota_reset: getNextResetDate(),
    },
    select: {
      userId: true,
      plan: true,
      quota_total: true,
      quota_used: true,
      quota_reset: true,
    },
  });
}
