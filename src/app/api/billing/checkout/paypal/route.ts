export const dynamic = "force-dynamic";

import { NextRequest, NextResponse } from "next/server";
import { getErrorMessage } from "@/lib/errors";
import { createSubscription } from "@/lib/paypal";
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
    if (!config.providerPlanIds.paypal?.trim()) {
      return NextResponse.json(
        { error: "provider_unavailable", provider: "paypal", plan },
        { status: 400 },
      );
    }

    const origin = request.headers.get("origin") || request.nextUrl.origin;
    const result = await createSubscription(
      plan,
      `${origin}/?billing_success=1&provider=paypal&plan=${plan}`,
      `${origin}/?billing_cancel=1&provider=paypal`,
      session.user.id,
    );

    return NextResponse.json({
      provider: "paypal",
      url: result.approvalUrl,
      subscriptionId: result.subscriptionId,
      status: result.status,
    });
  } catch (error) {
    return NextResponse.json(
      { error: getErrorMessage(error, "Failed to create PayPal checkout") },
      { status: 500 },
    );
  }
}
