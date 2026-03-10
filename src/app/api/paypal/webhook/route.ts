export const dynamic = 'force-dynamic';

import { NextRequest, NextResponse } from "next/server";
import { getErrorMessage } from "@/lib/errors";
import { PLANS } from "@/lib/paypal";

/**
 * PayPal Webhook handler.
 */
export async function POST(request: NextRequest) {
    try {
        const { prisma } = await import("@/lib/prisma");
        const { resetMonthlyQuota } = await import("@/lib/quota");

        const body = await request.json();
        const eventType = body.event_type as string;
        const resource = body.resource || {};

        console.log(`[PayPal Webhook] Event: ${eventType}`);

        const subscriptionId =
            resource.id || resource.billing_agreement_id || resource.subscription_id;

        if (!subscriptionId) {
            console.warn("[PayPal Webhook] No subscription ID in event");
            return NextResponse.json({ received: true });
        }

        const subscription = await prisma.subscription.findUnique({
            where: { paypalSubId: subscriptionId },
            include: { user: true },
        });

        if (!subscription) {
            console.warn(`[PayPal Webhook] Unknown subscription: ${subscriptionId}`);
            return NextResponse.json({ received: true });
        }

        switch (eventType) {
            case "BILLING.SUBSCRIPTION.ACTIVATED": {
                const planId = resource.plan_id;
                const planKey =
                    Object.entries(PLANS).find(([, p]) => p.paypalPlanId === planId)?.[0] || subscription.plan;

                await prisma.subscription.update({
                    where: { id: subscription.id },
                    data: {
                        status: "active",
                        plan: planKey,
                        currentPeriodEnd: resource.billing_info?.next_billing_time
                            ? new Date(resource.billing_info.next_billing_time)
                            : null,
                    },
                });

                await resetMonthlyQuota(subscription.userId, planKey);
                console.log(`[PayPal Webhook] Subscription activated: ${planKey} for user ${subscription.userId}`);
                break;
            }

            case "BILLING.SUBSCRIPTION.CANCELLED":
            case "BILLING.SUBSCRIPTION.SUSPENDED": {
                await prisma.subscription.update({
                    where: { id: subscription.id },
                    data: { status: eventType.includes("CANCELLED") ? "cancelled" : "suspended" },
                });

                await prisma.profile.update({
                    where: { userId: subscription.userId },
                    data: { plan: "free", quota_total: PLANS.free.quotaTotal },
                });

                console.log(`[PayPal Webhook] Subscription ${eventType.includes("CANCELLED") ? "cancelled" : "suspended"}: ${subscription.userId}`);
                break;
            }

            case "PAYMENT.SALE.COMPLETED": {
                await resetMonthlyQuota(subscription.userId, subscription.plan);

                if (resource.billing_agreement_id) {
                    await prisma.subscription.update({
                        where: { id: subscription.id },
                        data: {
                            status: "active",
                            currentPeriodEnd: new Date(
                                Date.now() + 30 * 24 * 60 * 60 * 1000
                            ),
                        },
                    });
                }

                console.log(`[PayPal Webhook] Payment completed, quota reset for user ${subscription.userId}`);
                break;
            }

            default:
                console.log(`[PayPal Webhook] Unhandled event: ${eventType}`);
        }

        return NextResponse.json({ received: true });
    } catch (error) {
        console.error("[PayPal Webhook] Error:", error);
        return NextResponse.json(
            { error: getErrorMessage(error, "Webhook processing failed") },
            { status: 500 },
        );
    }
}
