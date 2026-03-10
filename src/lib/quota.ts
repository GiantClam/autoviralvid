/**
 * Quota management helpers.
 *
 * Checks and consumes video generation quotas per user.
 */

import { prisma } from "./prisma";
import { PLANS } from "./paypal";
import type { Prisma } from "@prisma/client";

export interface QuotaInfo {
    allowed: boolean;
    remaining: number;
    total: number;
    used: number;
    plan: string;
}

/**
 * Check whether the user has remaining quota.
 */
export async function checkQuota(userId: string): Promise<QuotaInfo> {
    const profile = await prisma.profile.findUnique({ where: { userId } });

    if (!profile) {
        // No profile — treat as free plan with default quota
        return { allowed: true, remaining: 3, total: 3, used: 0, plan: "free" };
    }

    const plan = profile.plan || "free";
    const planConfig = PLANS[plan];
    const total = planConfig?.quotaTotal ?? profile.quota_total;

    // Unlimited plan
    if (total === -1) {
        return { allowed: true, remaining: -1, total: -1, used: profile.quota_used, plan };
    }

    // Check if quota needs monthly reset
    if (profile.quota_reset && new Date() > profile.quota_reset) {
        await prisma.profile.update({
            where: { userId },
            data: { quota_used: 0, quota_reset: getNextResetDate() },
        });
        return { allowed: true, remaining: total, total, used: 0, plan };
    }

    const remaining = Math.max(0, total - profile.quota_used);
    return {
        allowed: remaining > 0,
        remaining,
        total,
        used: profile.quota_used,
        plan,
    };
}

/**
 * Consume one unit of quota. Returns false if quota exceeded.
 */
export async function consumeQuota(userId: string): Promise<boolean> {
    const info = await checkQuota(userId);
    if (!info.allowed) return false;

    // Unlimited — no need to decrement
    if (info.total === -1) return true;

    await prisma.profile.update({
        where: { userId },
        data: { quota_used: { increment: 1 } },
    });

    return true;
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
}

function getNextResetDate(): Date {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth() + 1, 1);
}
