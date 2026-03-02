"use client";

import React, { useState, useEffect } from "react";
import { Zap, Crown, Sparkles } from "lucide-react";
import { useT } from "@/lib/i18n";

interface QuotaInfo {
    allowed: boolean;
    remaining: number;
    total: number;
    used: number;
    plan: string;
}

export default function QuotaBar({
    onUpgrade,
}: {
    onUpgrade?: () => void;
}) {
    const t = useT();
    const [quota, setQuota] = useState<QuotaInfo | null>(null);

    useEffect(() => {
        fetch("/api/quota")
            .then((r) => (r.ok ? r.json() : null))
            .then((data) => data && setQuota(data))
            .catch(() => {});
    }, []);

    if (!quota) return null;

    if (quota.total === -1) {
        return (
            <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-gradient-to-r from-emerald-500/10 to-emerald-500/5 border border-emerald-500/20">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-emerald-500 to-emerald-600 flex items-center justify-center">
                    <Crown className="w-4 h-4 text-white" />
                </div>
                <div>
                    <span className="text-xs font-bold text-emerald-400">{t("quota.unlimited")}</span>
                    <p className="text-[10px] text-emerald-500/60">Premium Plan</p>
                </div>
            </div>
        );
    }

    const pct = quota.total > 0 ? Math.min(100, Math.round((quota.used / quota.total) * 100)) : 0;
    const isLow = quota.remaining <= 1;
    const isEmpty = quota.remaining === 0;

    return (
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
                <span className="text-[10px] font-semibold text-gray-600 uppercase tracking-wider">{quota.plan}</span>
            </div>

            <div className="relative h-2 rounded-full bg-white/[0.04] overflow-hidden">
                <div 
                    className="absolute inset-0 opacity-30"
                    style={{
                        background: `linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent)`,
                        animation: 'shimmer 2s infinite',
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

            {isEmpty && onUpgrade && (
                <button
                    onClick={onUpgrade}
                    className="w-full group flex items-center justify-center gap-2 py-2.5 rounded-xl bg-gradient-to-r from-[#E11D48]/10 to-purple-500/10 border border-[#E11D48]/20 text-xs font-semibold text-[#E11D48] hover:from-[#E11D48]/20 hover:to-purple-500/20 hover:border-[#E11D48]/40 transition-all duration-300 cursor-pointer"
                >
                    <Sparkles className="w-3.5 h-3.5 group-hover:scale-110 transition-transform" />
                    {t("quota.exhausted")}
                </button>
            )}
        </div>
    );
}
