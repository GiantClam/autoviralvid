export const dynamic = 'force-dynamic';

import { NextResponse } from "next/server";
import { getErrorMessage } from "@/lib/errors";
import { PLANS } from "@/lib/paypal";

export async function GET() {
    try {
        const { auth } = await import("@/lib/auth");
        const { prisma } = await import("@/lib/prisma");
        const { checkQuota } = await import("@/lib/quota");

        const session = await auth();
        if (!session?.user?.email) {
            return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
        }

        const user = await prisma.user.findUnique({
            where: { email: session.user.email },
            include: { profile: true, subscription: true },
        });

        if (!user) {
            return NextResponse.json({ error: "User not found" }, { status: 404 });
        }

        const quota = await checkQuota(user.id);
        const plan = user.profile?.plan || "free";
        const planConfig = PLANS[plan];

        return NextResponse.json({
            plan,
            planName: planConfig?.name || "Free",
            price: planConfig?.price || 0,
            features: planConfig?.features || [],
            quota,
            subscription: user.subscription
                ? {
                    status: user.subscription.status,
                    paypalSubId: user.subscription.paypalSubId,
                    currentPeriodEnd: user.subscription.currentPeriodEnd,
                }
                : null,
        });
    } catch (error) {
        console.error("[Subscription Status] Error:", error);
        return NextResponse.json(
            { error: getErrorMessage(error, "Failed to get subscription status") },
            { status: 500 }
        );
    }
}
