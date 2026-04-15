export type PlanCode = "free" | "pro" | "enterprise";

export interface BillingPlan {
  code: PlanCode;
  name: string;
  price: number;
  quotaTotal: number;
  features: string[];
  providerPlanIds: {
    paypal?: string;
    stripe?: string;
  };
}

export function getPlanCatalog(): Record<PlanCode, BillingPlan> {
  return {
    free: {
      code: "free",
      name: "Free",
      price: 0,
      quotaTotal: 3,
      features: ["3 videos / month", "720p quality", "Community support"],
      providerPlanIds: {},
    },
    pro: {
      code: "pro",
      name: "Pro",
      price: 9.9,
      quotaTotal: 30,
      features: [
        "30 videos / month",
        "1080p quality",
        "Priority rendering",
        "Email support",
      ],
      providerPlanIds: {
        paypal: process.env.PAYPAL_PLAN_PRO || "P-xxxPRO",
        stripe: process.env.STRIPE_PRICE_PRO || "",
      },
    },
    enterprise: {
      code: "enterprise",
      name: "Enterprise",
      price: 29.9,
      quotaTotal: -1,
      features: [
        "Unlimited videos",
        "4K quality",
        "Priority rendering",
        "Custom branding",
        "Dedicated support",
      ],
      providerPlanIds: {
        paypal: process.env.PAYPAL_PLAN_ENTERPRISE || "P-xxxENTERPRISE",
        stripe: process.env.STRIPE_PRICE_ENTERPRISE || "",
      },
    },
  };
}

