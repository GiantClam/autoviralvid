export const dynamic = "force-dynamic";

import { NextRequest, NextResponse } from "next/server";
import { Prisma } from "@prisma/client";
import { createHmac, timingSafeEqual } from "crypto";
import { getErrorMessage } from "@/lib/errors";
import { prisma } from "@/lib/prisma";
import { getPlanCatalog } from "@/lib/billing/plan-catalog";
import { beginWebhookEvent, finishWebhookEvent, sha256Hex } from "@/lib/billing/webhook-events";
import { resetMonthlyQuota } from "@/lib/quota";

type StripeEvent = {
  id?: string;
  type?: string;
  data?: {
    object?: Record<string, unknown>;
  };
};

type StripeSignature = {
  timestamp: string;
  v1: string[];
};

function parseStripeSignature(header: string | null): StripeSignature | null {
  if (!header) return null;
  const parts = header.split(",").map((item) => item.trim());
  const timestamp = parts.find((part) => part.startsWith("t="))?.slice(2);
  const v1 = parts
    .filter((part) => part.startsWith("v1="))
    .map((part) => part.slice(3))
    .filter(Boolean);
  if (!timestamp || v1.length === 0) return null;
  return { timestamp, v1 };
}

function verifyStripeSignature(payload: string, signatureHeader: string | null): boolean {
  const secret = process.env.STRIPE_WEBHOOK_SECRET || "";
  if (!secret) {
    // Non-production fallback: allow unsigned events when secret is not configured.
    return true;
  }
  const parsed = parseStripeSignature(signatureHeader);
  if (!parsed) return false;
  const signedPayload = `${parsed.timestamp}.${payload}`;
  const digest = createHmac("sha256", secret).update(signedPayload).digest("hex");
  const expected = Buffer.from(digest, "utf8");
  return parsed.v1.some((candidate) => {
    const actual = Buffer.from(candidate, "utf8");
    return actual.length === expected.length && timingSafeEqual(actual, expected);
  });
}

function unixSecondsToDate(value: unknown): Date | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return new Date(Math.floor(value) * 1000);
}

function resolvePlanFromStripePriceId(priceId: string | undefined, fallback = "free") {
  if (!priceId) return fallback;
  const catalog = getPlanCatalog();
  for (const plan of Object.values(catalog)) {
    if (plan.providerPlanIds.stripe === priceId) {
      return plan.code;
    }
  }
  return fallback;
}

async function resolveStripeUserId(
  object: Record<string, unknown>,
): Promise<string | null> {
  const metadata = (object.metadata as Record<string, unknown> | undefined) || {};
  const metadataUserId = typeof metadata.userId === "string" ? metadata.userId.trim() : "";
  if (metadataUserId) return metadataUserId;

  const clientReferenceId =
    typeof object.client_reference_id === "string" ? object.client_reference_id.trim() : "";
  if (clientReferenceId) return clientReferenceId;

  const customerId = typeof object.customer === "string" ? object.customer.trim() : "";
  if (customerId) {
    const mappedCustomer = await prisma.paymentCustomer.findUnique({
      where: {
        provider_providerCustomerId: {
          provider: "stripe",
          providerCustomerId: customerId,
        },
      },
      select: { userId: true },
    });
    if (mappedCustomer?.userId) return mappedCustomer.userId;
  }

  const customerEmail = typeof object.customer_email === "string" ? object.customer_email.trim() : "";
  if (customerEmail) {
    const user = await prisma.user.findUnique({
      where: { email: customerEmail },
      select: { id: true },
    });
    if (user?.id) return user.id;
  }

  return null;
}

async function upsertStripeCustomer(userId: string, object: Record<string, unknown>) {
  const customerId = typeof object.customer === "string" ? object.customer.trim() : "";
  if (!customerId) return;
  await prisma.paymentCustomer.upsert({
    where: {
      provider_providerCustomerId: {
        provider: "stripe",
        providerCustomerId: customerId,
      },
    },
    create: {
      userId,
      provider: "stripe",
      providerCustomerId: customerId,
    },
    update: {
      userId,
    },
  });
}

async function syncLegacyStripeSubscription(
  userId: string,
  planCode: string,
  status: string,
  currentPeriodEnd: Date | null,
) {
  await prisma.subscription.upsert({
    where: { userId },
    create: {
      userId,
      plan: planCode,
      status,
      currentPeriodEnd,
    },
    update: {
      plan: planCode,
      status,
      currentPeriodEnd,
    },
  });
}

export async function POST(request: NextRequest) {
  let eventId = "";
  try {
    const raw = await request.text();
    const signatureHeader = request.headers.get("stripe-signature");
    if (!verifyStripeSignature(raw, signatureHeader)) {
      return NextResponse.json({ error: "Invalid Stripe signature" }, { status: 400 });
    }

    const event = (raw ? JSON.parse(raw) : {}) as StripeEvent;
    const eventType = event.type || "unknown";
    eventId = event.id || `stripe-fallback-${sha256Hex(raw).slice(0, 16)}`;

    const begin = await beginWebhookEvent("stripe", eventId, eventType, raw);
    if (begin.duplicate) {
      return NextResponse.json({ received: true, duplicate: true });
    }

    const object = (event.data?.object || {}) as Record<string, unknown>;
    const userId = await resolveStripeUserId(object);

    if (!userId) {
      await finishWebhookEvent("stripe", eventId, "processed");
      return NextResponse.json({ received: true, unresolved_user: true });
    }

    await upsertStripeCustomer(userId, object);

    if (eventType === "checkout.session.completed") {
      const metadata = (object.metadata as Record<string, unknown> | undefined) || {};
      const subscriptionId =
        typeof object.subscription === "string" ? object.subscription : "";
      const planCode = typeof metadata.plan === "string" ? metadata.plan : "free";
      if (subscriptionId) {
        await prisma.paymentSubscription.upsert({
          where: {
            provider_providerSubId: {
              provider: "stripe",
              providerSubId: subscriptionId,
            },
          },
          create: {
            userId,
            provider: "stripe",
            providerSubId: subscriptionId,
            planCode,
            status: "active",
            metadata: object as Prisma.InputJsonValue,
          },
          update: {
            userId,
            planCode,
            status: "active",
            metadata: object as Prisma.InputJsonValue,
          },
        });
      }
    } else if (
      eventType === "customer.subscription.created" ||
      eventType === "customer.subscription.updated" ||
      eventType === "customer.subscription.deleted"
    ) {
      const subscriptionId = typeof object.id === "string" ? object.id : "";
      const status = typeof object.status === "string" ? object.status : "active";
      const cancelAtPeriodEnd = Boolean(object.cancel_at_period_end);
      const currentPeriodStart = unixSecondsToDate(object.current_period_start);
      const currentPeriodEnd = unixSecondsToDate(object.current_period_end);
      const items = object.items as Record<string, unknown> | undefined;
      const itemData = Array.isArray(items?.data)
        ? (items?.data as Array<Record<string, unknown>>)
        : [];
      const price =
        (itemData[0]?.price as Record<string, unknown> | undefined) || undefined;
      const priceId = typeof price?.id === "string" ? price.id : undefined;
      const planCode = resolvePlanFromStripePriceId(priceId, "free");

      if (subscriptionId) {
        await prisma.paymentSubscription.upsert({
          where: {
            provider_providerSubId: {
              provider: "stripe",
              providerSubId: subscriptionId,
            },
          },
          create: {
            userId,
            provider: "stripe",
            providerSubId: subscriptionId,
            planCode,
            status,
            currentPeriodStart,
            currentPeriodEnd,
            cancelAtPeriodEnd,
            metadata: object as Prisma.InputJsonValue,
          },
          update: {
            planCode,
            status,
            currentPeriodStart,
            currentPeriodEnd,
            cancelAtPeriodEnd,
            metadata: object as Prisma.InputJsonValue,
          },
        });
      }

      await syncLegacyStripeSubscription(userId, planCode, status, currentPeriodEnd);
    } else if (eventType === "invoice.payment_succeeded") {
      const lines = object.lines as Record<string, unknown> | undefined;
      const lineItems = Array.isArray(lines?.data)
        ? (lines?.data as Array<Record<string, unknown>>)
        : [];
      const firstLinePrice = (lineItems[0]?.price as Record<string, unknown> | undefined) || undefined;
      const planCode = resolvePlanFromStripePriceId(
        typeof firstLinePrice?.id === "string" ? firstLinePrice.id : undefined,
        "free",
      );
      await resetMonthlyQuota(userId, planCode);
    }

    await finishWebhookEvent("stripe", eventId, "processed");
    return NextResponse.json({ received: true });
  } catch (error) {
    await finishWebhookEvent("stripe", eventId, "failed").catch(() => undefined);
    return NextResponse.json(
      { error: getErrorMessage(error, "Stripe webhook processing failed") },
      { status: 500 },
    );
  }
}
