"use client";

import React, { useEffect, useMemo, useState } from "react";
import { X, Check, Zap, Crown, Sparkles } from "lucide-react";

interface PricingModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentPlan?: string;
  quotaUsed?: number;
  quotaTotal?: number;
}

type BillingProvider = "paypal" | "stripe";

type PlanResponseItem = {
  key: string;
  name: string;
  price: number;
  quotaTotal: number;
  features: string[];
  providers?: {
    paypal?: boolean;
    stripe?: boolean;
  };
};

type PlanCard = PlanResponseItem & {
  period: string;
  accent: string;
  popular?: boolean;
  icon: React.ReactNode;
};

const FALLBACK_PLANS: PlanResponseItem[] = [
  {
    key: "free",
    name: "Free",
    price: 0,
    quotaTotal: 3,
    features: ["3 videos / month", "720p quality", "Community support"],
    providers: { paypal: true, stripe: true },
  },
  {
    key: "pro",
    name: "Pro",
    price: 9.9,
    quotaTotal: 30,
    features: [
      "30 videos / month",
      "1080p quality",
      "Priority rendering",
      "Email support",
    ],
    providers: { paypal: true, stripe: true },
  },
  {
    key: "enterprise",
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
    providers: { paypal: true, stripe: true },
  },
];

const PLAN_VISUALS: Record<
  string,
  {
    accent: string;
    icon: React.ReactNode;
    popular?: boolean;
  }
> = {
  free: {
    accent: "from-zinc-500 to-zinc-600",
    icon: <Zap className="w-5 h-5" />,
  },
  pro: {
    accent: "from-[#E11D48] to-[#BE123C]",
    icon: <Crown className="w-5 h-5" />,
    popular: true,
  },
  enterprise: {
    accent: "from-amber-500 to-orange-600",
    icon: <Sparkles className="w-5 h-5" />,
  },
};

const PLAN_ORDER = ["free", "pro", "enterprise"];

function toPlanCards(plans: PlanResponseItem[]): PlanCard[] {
  return [...plans]
    .sort((a, b) => {
      const ia = PLAN_ORDER.indexOf(a.key);
      const ib = PLAN_ORDER.indexOf(b.key);
      const pa = ia === -1 ? 999 : ia;
      const pb = ib === -1 ? 999 : ib;
      return pa - pb;
    })
    .map((plan) => {
      const visual = PLAN_VISUALS[plan.key] || {
        accent: "from-zinc-600 to-zinc-700",
        icon: <Sparkles className="w-5 h-5" />,
      };
      return {
        ...plan,
        period: plan.price > 0 ? "/ month" : "forever",
        accent: visual.accent,
        icon: visual.icon,
        popular: visual.popular,
      };
    });
}

export default function PricingModal({
  isOpen,
  onClose,
  currentPlan = "free",
  quotaUsed = 0,
  quotaTotal = 3,
}: PricingModalProps) {
  const [loading, setLoading] = useState<string | null>(null);
  const [loadingPlans, setLoadingPlans] = useState(false);
  const [error, setError] = useState("");
  const [provider, setProvider] = useState<BillingProvider>("paypal");
  const [plans, setPlans] = useState<PlanCard[]>(() => toPlanCards(FALLBACK_PLANS));

  useEffect(() => {
    if (!isOpen) {
      setError("");
      setLoading(null);
      return;
    }

    let cancelled = false;
    async function loadPlans() {
      setLoadingPlans(true);
      try {
        const res = await fetch("/api/billing/plans", { cache: "no-store" });
        if (!res.ok) {
          if (!cancelled) {
            setPlans(toPlanCards(FALLBACK_PLANS));
          }
          return;
        }
        const data = (await res.json()) as { plans?: PlanResponseItem[] };
        const nextPlans =
          data.plans && data.plans.length > 0 ? data.plans : FALLBACK_PLANS;
        if (!cancelled) {
          setPlans(toPlanCards(nextPlans));
        }
      } catch {
        if (!cancelled) {
          setPlans(toPlanCards(FALLBACK_PLANS));
        }
      } finally {
        if (!cancelled) {
          setLoadingPlans(false);
        }
      }
    }

    void loadPlans();
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  const handleSubscribe = async (plan: PlanCard) => {
    if (plan.key === "free" || plan.key === currentPlan) return;

    const providerAvailable = Boolean(plan.providers?.[provider]);
    if (!providerAvailable) {
      setError(
        provider === "paypal"
          ? "PayPal is unavailable for this plan"
          : "Stripe is unavailable for this plan",
      );
      return;
    }

    setLoading(plan.key);
    setError("");

    try {
      const res = await fetch(`/api/billing/checkout/${provider}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan: plan.key }),
      });

      const data = (await res.json()) as {
        error?: string;
        url?: string;
        approvalUrl?: string;
        checkoutUrl?: string;
      };

      if (!res.ok) {
        setError(data.error || "Failed to create subscription");
        return;
      }

      const checkoutUrl = data.url || data.approvalUrl || data.checkoutUrl;
      if (checkoutUrl) {
        window.location.href = checkoutUrl;
      }
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setLoading(null);
    }
  };

  const usagePct = useMemo(
    () => (quotaTotal > 0 ? Math.min(100, (quotaUsed / quotaTotal) * 100) : 0),
    [quotaTotal, quotaUsed],
  );

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <div className="w-full max-w-4xl bg-[#0F0F23] border border-white/[0.08] rounded-2xl p-8 relative max-h-[90vh] overflow-y-auto">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-500 hover:text-white transition-colors"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="text-center mb-8">
          <h2 className="text-3xl font-bold mb-2">Upgrade Your Plan</h2>
          <p className="text-gray-400">Choose the plan that fits your creative needs</p>

          {currentPlan === "free" && (
            <div className="mt-4 max-w-xs mx-auto">
              <div className="flex justify-between text-xs text-gray-500 mb-1">
                <span>Usage this month</span>
                <span>
                  {quotaUsed} / {quotaTotal} videos
                </span>
              </div>
              <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    usagePct >= 100
                      ? "bg-red-500"
                      : usagePct >= 66
                        ? "bg-amber-500"
                        : "bg-[#E11D48]"
                  }`}
                  style={{ width: `${usagePct}%` }}
                />
              </div>
            </div>
          )}
        </div>

        {error && (
          <div className="mb-6 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm text-center">
            {error}
          </div>
        )}

        <div className="mb-4 flex items-center justify-center gap-2">
          <button
            type="button"
            onClick={() => setProvider("paypal")}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
              provider === "paypal"
                ? "bg-white/15 text-white"
                : "bg-white/5 text-gray-400 hover:bg-white/10"
            }`}
          >
            PayPal
          </button>
          <button
            type="button"
            onClick={() => setProvider("stripe")}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
              provider === "stripe"
                ? "bg-white/15 text-white"
                : "bg-white/5 text-gray-400 hover:bg-white/10"
            }`}
          >
            Stripe
          </button>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          {plans.map((plan) => {
            const isCurrent = plan.key === currentPlan;
            const isLoading = loading === plan.key;
            const providerAvailable =
              plan.key === "free" ? true : Boolean(plan.providers?.[provider]);

            return (
              <div
                key={plan.key}
                className={`relative rounded-xl border p-6 flex flex-col transition-all ${
                  plan.popular
                    ? "border-[#E11D48]/50 bg-[#E11D48]/5 shadow-lg shadow-[#E11D48]/10"
                    : "border-white/10 bg-white/[0.02] hover:border-white/20"
                }`}
              >
                {plan.popular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 bg-[#E11D48] rounded-full text-xs font-semibold">
                    Most Popular
                  </div>
                )}

                <div className="flex items-center gap-2 mb-4">
                  <div
                    className={`w-8 h-8 rounded-lg bg-gradient-to-br ${plan.accent} flex items-center justify-center`}
                  >
                    {plan.icon}
                  </div>
                  <h3 className="text-lg font-bold">{plan.name}</h3>
                </div>

                <div className="mb-6">
                  <span className="text-4xl font-bold">
                    {plan.price === 0 ? "Free" : `$${plan.price}`}
                  </span>
                  {plan.price > 0 && (
                    <span className="text-gray-500 ml-1">{plan.period}</span>
                  )}
                </div>

                <ul className="space-y-3 mb-6 flex-1">
                  {plan.features.map((feature) => (
                    <li key={`${plan.key}-${feature}`} className="flex items-start gap-2 text-sm">
                      <Check className="w-4 h-4 text-green-400 mt-0.5 shrink-0" />
                      <span className="text-gray-300">{feature}</span>
                    </li>
                  ))}
                </ul>

                {!providerAvailable && plan.price > 0 && (
                  <p className="mb-3 text-[11px] text-amber-400 text-center">
                    {provider === "paypal"
                      ? "PayPal unavailable for this plan"
                      : "Stripe unavailable for this plan"}
                  </p>
                )}

                <button
                  onClick={() => handleSubscribe(plan)}
                  disabled={
                    isCurrent ||
                    isLoading ||
                    plan.key === "free" ||
                    !providerAvailable ||
                    loadingPlans
                  }
                  className={`w-full py-3 rounded-lg font-semibold text-sm transition-all flex items-center justify-center gap-2 ${
                    isCurrent
                      ? "bg-white/5 text-gray-500 cursor-default"
                      : plan.popular
                        ? "bg-[#E11D48] hover:bg-[#BE123C] text-white"
                        : "bg-white/10 hover:bg-white/20 text-white"
                  } disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  {isLoading && (
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  )}
                  {isCurrent
                    ? "Current Plan"
                    : plan.key === "free"
                      ? "Free Forever"
                      : !providerAvailable
                        ? provider === "paypal"
                          ? "PayPal Unavailable"
                          : "Stripe Unavailable"
                        : provider === "paypal"
                          ? "Subscribe with PayPal"
                          : "Subscribe with Stripe"}
                </button>
              </div>
            );
          })}
        </div>

        <p className="text-center text-xs text-gray-600 mt-6">
          Payments are securely processed by{" "}
          {provider === "paypal" ? "PayPal" : "Stripe"}. Cancel anytime.
        </p>
      </div>
    </div>
  );
}
