export const dynamic = "force-dynamic";

import { NextRequest, NextResponse } from "next/server";
import { Prisma } from "@prisma/client";
import { getErrorMessage } from "@/lib/errors";
import { prisma } from "@/lib/prisma";
import { getPlanCatalog } from "@/lib/billing/plan-catalog";
import { beginWebhookEvent, finishWebhookEvent, sha256Hex } from "@/lib/billing/webhook-events";
import { resetMonthlyQuota } from "@/lib/quota";

type PayPalWebhookBody = {
  id?: string;
  event_type?: string;
  resource?: Record<string, unknown>;
};

function resolvePlanFromPaypalPlanId(planId: string | undefined, fallbackPlan = "free") {
  if (!planId) return fallbackPlan;
  const catalog = getPlanCatalog();
  for (const plan of Object.values(catalog)) {
    if (plan.providerPlanIds.paypal === planId) {
      return plan.code;
    }
  }
  return fallbackPlan;
}

function toDate(value: unknown): Date | null {
  if (typeof value !== "string" || !value.trim()) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

async function resolvePaypalUserId(
  subscriptionId: string,
  resource: Record<string, unknown>,
): Promise<string | null> {
  const customUserId = typeof resource.custom_id === "string" ? resource.custom_id.trim() : "";
  if (customUserId) {
    return customUserId;
  }

  const existingPaymentSub = await prisma.paymentSubscription.findUnique({
    where: {
      provider_providerSubId: {
        provider: "paypal",
        providerSubId: subscriptionId,
      },
    },
    select: { userId: true },
  });
  if (existingPaymentSub?.userId) {
    return existingPaymentSub.userId;
  }

  const legacy = await prisma.subscription.findUnique({
    where: { paypalSubId: subscriptionId },
    select: { userId: true },
  });
  if (legacy?.userId) {
    return legacy.userId;
  }

  const subscriber = resource.subscriber as Record<string, unknown> | undefined;
  const email = typeof subscriber?.email_address === "string" ? subscriber.email_address : "";
  if (!email) return null;

  const user = await prisma.user.findUnique({
    where: { email },
    select: { id: true },
  });
  return user?.id ?? null;
}

async function syncLegacySubscription(
  userId: string,
  paypalSubId: string,
  planCode: string,
  status: string,
  currentPeriodEnd: Date | null,
) {
  await prisma.subscription.upsert({
    where: { userId },
    create: {
      userId,
      paypalSubId,
      plan: planCode,
      status,
      currentPeriodEnd,
    },
    update: {
      paypalSubId,
      plan: planCode,
      status,
      currentPeriodEnd,
    },
  });
}

export async function POST(request: NextRequest) {
  let providerEventId = "";
  try {
    const raw = await request.text();
    const parsed = (raw ? JSON.parse(raw) : {}) as PayPalWebhookBody;
    const eventType = parsed.event_type || "unknown";
    const resource = (parsed.resource || {}) as Record<string, unknown>;
    providerEventId =
      parsed.id ||
      request.headers.get("paypal-transmission-id") ||
      `paypal-fallback-${sha256Hex(raw).slice(0, 16)}`;

    const begin = await beginWebhookEvent("paypal", providerEventId, eventType, raw);
    if (begin.duplicate) {
      return NextResponse.json({ received: true, duplicate: true });
    }

    const subscriptionId = String(
      resource.id || resource.billing_agreement_id || resource.subscription_id || "",
    ).trim();
    if (!subscriptionId) {
      await finishWebhookEvent("paypal", providerEventId, "processed");
      return NextResponse.json({ received: true });
    }

    const userId = await resolvePaypalUserId(subscriptionId, resource);
    if (!userId) {
      await finishWebhookEvent("paypal", providerEventId, "processed");
      return NextResponse.json({ received: true, unresolved_user: true });
    }

    const planCode = resolvePlanFromPaypalPlanId(
      typeof resource.plan_id === "string" ? resource.plan_id : undefined,
      "free",
    );

    if (eventType === "BILLING.SUBSCRIPTION.ACTIVATED") {
      const periodEnd = toDate(
        (resource.billing_info as Record<string, unknown> | undefined)?.next_billing_time,
      );
      await prisma.paymentSubscription.upsert({
        where: {
          provider_providerSubId: {
            provider: "paypal",
            providerSubId: subscriptionId,
          },
        },
        create: {
          userId,
          provider: "paypal",
          providerSubId: subscriptionId,
          planCode,
          status: "active",
          currentPeriodEnd: periodEnd,
          metadata: resource as Prisma.InputJsonValue,
        },
        update: {
          planCode,
          status: "active",
          currentPeriodEnd: periodEnd,
          metadata: resource as Prisma.InputJsonValue,
        },
      });

      await syncLegacySubscription(userId, subscriptionId, planCode, "active", periodEnd);
      await resetMonthlyQuota(userId, planCode);
    } else if (
      eventType === "BILLING.SUBSCRIPTION.CANCELLED" ||
      eventType === "BILLING.SUBSCRIPTION.SUSPENDED"
    ) {
      const status = eventType.includes("CANCELLED") ? "cancelled" : "suspended";
      await prisma.paymentSubscription.upsert({
        where: {
          provider_providerSubId: {
            provider: "paypal",
            providerSubId: subscriptionId,
          },
        },
        create: {
          userId,
          provider: "paypal",
          providerSubId: subscriptionId,
          planCode,
          status,
          metadata: resource as Prisma.InputJsonValue,
        },
        update: {
          status,
          metadata: resource as Prisma.InputJsonValue,
        },
      });

      await syncLegacySubscription(userId, subscriptionId, "free", status, null);
      await prisma.profile.update({
        where: { userId },
        data: {
          plan: "free",
          quota_total: getPlanCatalog().free.quotaTotal,
        },
      });
    } else if (eventType === "PAYMENT.SALE.COMPLETED") {
      const current = await prisma.paymentSubscription.findUnique({
        where: {
          provider_providerSubId: {
            provider: "paypal",
            providerSubId: subscriptionId,
          },
        },
        select: {
          planCode: true,
        },
      });
      const activePlan = current?.planCode || planCode || "free";
      await resetMonthlyQuota(userId, activePlan);
    }

    await finishWebhookEvent("paypal", providerEventId, "processed");
    return NextResponse.json({ received: true });
  } catch (error) {
    await finishWebhookEvent("paypal", providerEventId, "failed").catch(() => undefined);
    return NextResponse.json(
      { error: getErrorMessage(error, "PayPal webhook processing failed") },
      { status: 500 },
    );
  }
}
