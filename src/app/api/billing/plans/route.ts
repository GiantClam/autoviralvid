export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import { getPlanCatalog } from "@/lib/billing/plan-catalog";

type ProviderAvailability = {
  paypal: boolean;
  stripe: boolean;
};

export async function GET() {
  const catalog = getPlanCatalog();
  const order = ["free", "pro", "enterprise"] as const;

  const plans = order
    .map((code) => catalog[code])
    .filter(Boolean)
    .map((plan) => {
      const providers: ProviderAvailability = {
        paypal: Boolean(plan.providerPlanIds.paypal?.trim()),
        stripe: Boolean(plan.providerPlanIds.stripe?.trim()),
      };
      return {
        key: plan.code,
        name: plan.name,
        price: plan.price,
        quotaTotal: plan.quotaTotal,
        features: plan.features,
        providers,
      };
    });

  return NextResponse.json({ plans });
}
