"use client";

import React, { useState, useEffect, useMemo } from "react";
import { Zap, Crown, Sparkles } from "lucide-react";
import { useT } from "@/lib/i18n";
import PricingModal from "./PricingModal";

interface QuotaInfo {
    allowed: boolean;
    remaining: number;
    total: number;
    used: number;
    plan: string;
}

interface BillingMeInfo {
    plan: string;
    planName?: string;
    price?: number;
    quota: QuotaInfo;
    primarySubscription?: {
        provider?: "paypal" | "stripe" | "legacy";
        status?: string;
        currentPeriodEnd?: string | null;
    } | null;
}

function formatPlanName(planCode: string | undefined): string {
    if (planCode === "enterprise") return "Enterprise";
    if (planCode === "pro") return "Pro";
    return "Free";
}

export default function QuotaBar({
    onUpgrade,
}: {
    onUpgrade?: () => void;
}) {
    const t = useT();
    const [quota, setQuota] = useState<QuotaInfo | null>(null);
    const [plan, setPlan] = useState<string>("free");
    const [planName, setPlanName] = useState<string>("Free");
    const [planPrice, setPlanPrice] = useState<number>(0);
    const [primarySubscription, setPrimarySubscription] = useState<
        BillingMeInfo["primarySubscription"]
    >(null);
    const [showPricing, setShowPricing] = useState(false);

    const openUpgrade = () => {
        if (onUpgrade) {
            onUpgrade();
            return;
        }
        setShowPricing(true);
    };

    useEffect(() => {
        let cancelled = false;

        async function loadBillingState() {
            try {
                const billingRes = await fetch("/api/billing/me");
                if (billingRes.ok) {
                    const data = (await billingRes.json()) as BillingMeInfo;
                    if (!cancelled && data?.quota) {
                        setQuota(data.quota);
                        setPlan(data.plan || data.quota.plan || "free");
                        setPlanName(
                            data.planName || formatPlanName(data.plan || data.quota.plan || "free"),
                        );
                        setPlanPrice(typeof data.price === "number" ? data.price : 0);
                        setPrimarySubscription(data.primarySubscription ?? null);
                        return;
                    }
                }
            } catch {
                // fallback below
            }

            try {
                const quotaRes = await fetch("/api/quota");
                if (!quotaRes.ok) return;
                const data = (await quotaRes.json()) as QuotaInfo;
                if (!cancelled && data) {
                    setQuota(data);
                    setPlan(data.plan || "free");
                    setPlanName(formatPlanName(data.plan));
                    setPlanPrice(0);
                    setPrimarySubscription(null);
                }
            } catch {
                // noop
            }
        }

        void loadBillingState();
        return () => {
            cancelled = true;
        };
    }, []);

    const renewalDate = useMemo(() => {
        const value = primarySubscription?.currentPeriodEnd;
        if (!value) return "";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "";
        return date.toLocaleDateString();
    }, [primarySubscription?.currentPeriodEnd]);

    if (!quota) return null;

    const pct = quota.total > 0 ? Math.min(100, Math.round((quota.used / quota.total) * 100)) : 0;
    const isLow = quota.total > 0 && quota.remaining <= 1;
    const isEmpty = quota.total > 0 && quota.remaining === 0;

    const subscriptionProvider = (() => {
        const provider = primarySubscription?.provider;
        if (provider === "paypal") return "PayPal";
        if (provider === "stripe") return "Stripe";
        if (provider === "legacy") return "Legacy";
        return "No Provider";
    })();

    const subscriptionStatus = (() => {
        const status = String(primarySubscription?.status || "").toLowerCase();
        if (!status) return "Not Subscribed";
        if (status === "active") return "Active";
        if (status === "cancelled") return "Cancelled";
        if (status === "suspended") return "Suspended";
        if (status === "trialing") return "Trialing";
        return status.charAt(0).toUpperCase() + status.slice(1);
    })();

    const subscriptionSummary = primarySubscription
        ? renewalDate
            ? `${subscriptionProvider} · ${subscriptionStatus} · Renews ${renewalDate}`
            : `${subscriptionProvider} · ${subscriptionStatus}`
        : "No active paid subscription";

    const priceLabel = planPrice > 0 ? `$${planPrice}/mo` : "$0/mo";

    if (quota.total === -1) {
        return (
            <>
                <div className="space-y-2.5">
                    <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-gradient-to-r from-emerald-500/10 to-emerald-500/5 border border-emerald-500/20">
                        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-emerald-500 to-emerald-600 flex items-center justify-center">
                            <Crown className="w-4 h-4 text-white" />
                        </div>
                        <div>
                            <span className="text-xs font-bold text-emerald-400">{t("quota.unlimited")}</span>
                            <p className="text-[10px] text-emerald-500/60">Premium Plan</p>
                        </div>
                    </div>

                    <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2">
                        <div className="flex items-center justify-between text-[11px]">
                            <span className="font-semibold text-gray-200">{planName}</span>
                            <span className="text-gray-400">{priceLabel}</span>
                        </div>
                        <p className="mt-1 text-[10px] text-gray-500">{subscriptionSummary}</p>
                    </div>

                    <button
                        onClick={openUpgrade}
                        className="w-full group flex items-center justify-center gap-2 py-2 rounded-xl border border-white/[0.08] bg-white/[0.03] text-[11px] font-semibold text-gray-300 hover:bg-white/[0.06] hover:text-white transition-all duration-300 cursor-pointer"
                    >
                        <Sparkles className="w-3.5 h-3.5 text-[#E11D48]" />
                        Manage Subscription
                    </button>
                </div>
                <PricingModal
                    isOpen={showPricing}
                    onClose={() => setShowPricing(false)}
                    currentPlan={plan}
                    quotaUsed={quota.used}
                    quotaTotal={quota.total}
                />
            </>
        );
    }

    return (
        <>
            <div className="space-y-3">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <div className={`w-6 h-6 rounded-md flex items-center justify-center ${
                            isEmpty
                                ? 'bg-red-500/20'
                                : isLow
                                    ? 'bg-amber-500/20'
                                    : 'bg-[#E11D48]/20'
                        }`}>
                            <Zap className={`w-3 h-3 ${
                                isEmpty
                                    ? 'text-red-400'
                                    : isLow
                                        ? 'text-amber-400'
                                        : 'text-[#E11D48]'
                            }`} />
                        </div>
                        <div>
                            <span className={`text-xs font-semibold ${
                                isEmpty
                                    ? 'text-red-400'
                                    : isLow
                                        ? 'text-amber-400'
                                        : 'text-gray-300'
                            }`}>
                                {quota.used} / {quota.total} {t("common.times")}
                            </span>
                        </div>
                    </div>
                    <span className="text-[10px] font-semibold text-gray-600 uppercase tracking-wider">{plan}</span>
                </div>

                <div className="relative h-2 rounded-full bg-white/[0.04] overflow-hidden">
                    <div
                        className="absolute inset-0 opacity-30"
                        style={{
                            background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent)",
                            animation: "shimmer 2s infinite",
                            transform: `translateX(${pct - 100}%)`,
                        }}
                    />
                    <div
                        className={`h-full rounded-full transition-all duration-700 ease-out ${
                            isEmpty
                                ? 'bg-gradient-to-r from-red-500 to-red-600'
                                : isLow
                                    ? 'bg-gradient-to-r from-amber-500 to-orange-500'
                                    : 'bg-gradient-to-r from-[#E11D48] to-[#9333EA]'
                        }`}
                        style={{ width: `${pct}%` }}
                    />
                </div>

                <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2">
                    <div className="flex items-center justify-between text-[11px]">
                        <span className="font-semibold text-gray-200">{planName}</span>
                        <span className="text-gray-400">{priceLabel}</span>
                    </div>
                    <p className="mt-1 text-[10px] text-gray-500">{subscriptionSummary}</p>
                </div>

                <button
                    onClick={openUpgrade}
                    className={`w-full group flex items-center justify-center gap-2 py-2.5 rounded-xl text-xs font-semibold transition-all duration-300 cursor-pointer ${
                        isEmpty
                            ? "bg-gradient-to-r from-[#E11D48]/10 to-purple-500/10 border border-[#E11D48]/20 text-[#E11D48] hover:from-[#E11D48]/20 hover:to-purple-500/20 hover:border-[#E11D48]/40"
                            : "border border-white/[0.08] bg-white/[0.03] text-gray-300 hover:bg-white/[0.06] hover:text-white"
                    }`}
                >
                    <Sparkles className="w-3.5 h-3.5 text-[#E11D48] group-hover:scale-110 transition-transform" />
                    {isEmpty ? t("quota.exhausted") : plan === "free" ? "View Pricing" : "Manage Subscription"}
                </button>
            </div>
            <PricingModal
                isOpen={showPricing}
                onClose={() => setShowPricing(false)}
                currentPlan={plan}
                quotaUsed={quota.used}
                quotaTotal={quota.total}
            />
        </>
    );
}
