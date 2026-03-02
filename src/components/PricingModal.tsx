"use client";

import React, { useState, useEffect } from "react";
import { X, Check, Zap, Crown, Sparkles } from "lucide-react";

interface PricingModalProps {
    isOpen: boolean;
    onClose: () => void;
    currentPlan?: string;
    quotaUsed?: number;
    quotaTotal?: number;
}

interface PlanCard {
    key: string;
    name: string;
    price: number;
    period: string;
    features: string[];
    icon: React.ReactNode;
    accent: string;
    popular?: boolean;
}

const plans: PlanCard[] = [
    {
        key: "free",
        name: "Free",
        price: 0,
        period: "forever",
        features: ["3 videos / month", "720p quality", "Community support"],
        icon: <Zap className="w-5 h-5" />,
        accent: "from-zinc-500 to-zinc-600",
    },
    {
        key: "pro",
        name: "Pro",
        price: 9.9,
        period: "/ month",
        features: [
            "30 videos / month",
            "1080p quality",
            "Priority rendering",
            "Email support",
        ],
        icon: <Crown className="w-5 h-5" />,
        accent: "from-[#E11D48] to-[#BE123C]",
        popular: true,
    },
    {
        key: "enterprise",
        name: "Enterprise",
        price: 29.9,
        period: "/ month",
        features: [
            "Unlimited videos",
            "4K quality",
            "Priority rendering",
            "Custom branding",
            "Dedicated support",
        ],
        icon: <Sparkles className="w-5 h-5" />,
        accent: "from-amber-500 to-orange-600",
    },
];

export default function PricingModal({
    isOpen,
    onClose,
    currentPlan = "free",
    quotaUsed = 0,
    quotaTotal = 3,
}: PricingModalProps) {
    const [loading, setLoading] = useState<string | null>(null);
    const [error, setError] = useState("");

    useEffect(() => {
        if (!isOpen) {
            setError("");
            setLoading(null);
        }
    }, [isOpen]);

    const handleSubscribe = async (planKey: string) => {
        if (planKey === "free" || planKey === currentPlan) return;

        setLoading(planKey);
        setError("");

        try {
            const res = await fetch("/api/paypal/create-subscription", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ plan: planKey }),
            });

            const data = await res.json();

            if (!res.ok) {
                setError(data.error || "Failed to create subscription");
                return;
            }

            if (data.approvalUrl) {
                window.location.href = data.approvalUrl;
            }
        } catch {
            setError("Network error. Please try again.");
        } finally {
            setLoading(null);
        }
    };

    if (!isOpen) return null;

    const usagePct = quotaTotal > 0 ? Math.min(100, (quotaUsed / quotaTotal) * 100) : 0;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
            <div className="w-full max-w-4xl bg-[#0F0F23] border border-white/[0.08] rounded-2xl p-8 relative max-h-[90vh] overflow-y-auto">
                {/* Close */}
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 text-gray-500 hover:text-white transition-colors"
                >
                    <X className="w-5 h-5" />
                </button>

                {/* Header */}
                <div className="text-center mb-8">
                    <h2 className="text-3xl font-bold mb-2">Upgrade Your Plan</h2>
                    <p className="text-gray-400">
                        Choose the plan that fits your creative needs
                    </p>

                    {/* Usage bar */}
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
                                    className={`h-full rounded-full transition-all ${usagePct >= 100
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

                {/* Error */}
                {error && (
                    <div className="mb-6 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm text-center">
                        {error}
                    </div>
                )}

                {/* Plans Grid */}
                <div className="grid md:grid-cols-3 gap-6">
                    {plans.map((plan) => {
                        const isCurrent = plan.key === currentPlan;
                        const isLoading = loading === plan.key;

                        return (
                            <div
                                key={plan.key}
                                className={`relative rounded-xl border p-6 flex flex-col transition-all ${plan.popular
                                        ? "border-[#E11D48]/50 bg-[#E11D48]/5 shadow-lg shadow-[#E11D48]/10"
                                        : "border-white/10 bg-white/[0.02] hover:border-white/20"
                                    }`}
                            >
                                {/* Popular badge */}
                                {plan.popular && (
                                    <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 bg-[#E11D48] rounded-full text-xs font-semibold">
                                        Most Popular
                                    </div>
                                )}

                                {/* Plan icon & name */}
                                <div className="flex items-center gap-2 mb-4">
                                    <div
                                        className={`w-8 h-8 rounded-lg bg-gradient-to-br ${plan.accent} flex items-center justify-center`}
                                    >
                                        {plan.icon}
                                    </div>
                                    <h3 className="text-lg font-bold">{plan.name}</h3>
                                </div>

                                {/* Price */}
                                <div className="mb-6">
                                    <span className="text-4xl font-bold">
                                        {plan.price === 0 ? "Free" : `$${plan.price}`}
                                    </span>
                                    {plan.price > 0 && (
                                        <span className="text-gray-500 ml-1">{plan.period}</span>
                                    )}
                                </div>

                                {/* Features */}
                                <ul className="space-y-3 mb-6 flex-1">
                                    {plan.features.map((feature, i) => (
                                        <li key={i} className="flex items-start gap-2 text-sm">
                                            <Check className="w-4 h-4 text-green-400 mt-0.5 shrink-0" />
                                            <span className="text-gray-300">{feature}</span>
                                        </li>
                                    ))}
                                </ul>

                                {/* CTA */}
                                <button
                                    onClick={() => handleSubscribe(plan.key)}
                                    disabled={isCurrent || isLoading || plan.key === "free"}
                                    className={`w-full py-3 rounded-lg font-semibold text-sm transition-all flex items-center justify-center gap-2 ${isCurrent
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
                                            : "Subscribe with PayPal"}
                                </button>
                            </div>
                        );
                    })}
                </div>

                <p className="text-center text-xs text-gray-600 mt-6">
                    Payments are securely processed by PayPal. Cancel anytime.
                </p>
            </div>
        </div>
    );
}
