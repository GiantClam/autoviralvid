export const dynamic = "force-dynamic";

import { NextRequest, NextResponse } from "next/server";
import { getErrorMessage } from "@/lib/errors";
import { createStripeCheckoutSession } from "@/lib/billing/stripe";
import { getPlanCatalog } from "@/lib/billing/plan-catalog";

export async function POST(request: NextRequest) {
  try {
    const { auth } = await import("@/lib/auth");

    const session = await auth();
    if (!session?.user?.email) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { plan } = await request.json();
    const catalog = getPlanCatalog();
    const config = catalog[plan as keyof typeof catalog];
    if (!plan || !config || plan === "free") {
      return NextResponse.json({ error: "Invalid plan" }, { status: 400 });
    }
    if (!config.providerPlanIds.stripe?.trim()) {
      return NextResponse.json(
        { error: "provider_unavailable", provider: "stripe", plan },
        { status: 400 },
      );
    }

    const origin = request.headers.get("origin") || request.nextUrl.origin;
    const result = await createStripeCheckoutSession(
      plan,
      `${origin}/?billing_success=1&provider=stripe&plan=${plan}&session_id={CHECKOUT_SESSION_ID}`,
      `${origin}/?billing_cancel=1&provider=stripe`,
      session.user.email,
      session.user.id,
    );

    return NextResponse.json({
      provider: "stripe",
      url: result.checkoutUrl,
      sessionId: result.sessionId,
      status: result.status,
    });
  } catch (error) {
    return NextResponse.json(
      { error: getErrorMessage(error, "Failed to create Stripe checkout") },
      { status: 500 },
    );
  }
}
