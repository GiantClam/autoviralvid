export const dynamic = 'force-dynamic';

import { NextRequest, NextResponse } from "next/server";
import { getErrorMessage } from "@/lib/errors";
import { createSubscription, PLANS } from "@/lib/paypal";

export async function POST(request: NextRequest) {
    try {
        const { auth } = await import("@/lib/auth");

        const session = await auth();
        if (!session?.user?.email) {
            return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
        }

        const { plan } = await request.json();

        if (!plan || !PLANS[plan] || plan === "free") {
            return NextResponse.json({ error: "Invalid plan" }, { status: 400 });
        }

        const origin = request.headers.get("origin") || request.nextUrl.origin;
        const result = await createSubscription(
            plan,
            `${origin}/?paypal_success=true&plan=${plan}`,
            `${origin}/?paypal_cancel=true`
        );

        return NextResponse.json(result);
    } catch (error) {
        console.error("[PayPal] Create subscription error:", error);
        return NextResponse.json(
            { error: getErrorMessage(error, "Failed to create subscription") },
            { status: 500 }
        );
    }
}
