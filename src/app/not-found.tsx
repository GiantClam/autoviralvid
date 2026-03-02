"use client";

import Link from "next/link";
import { useT } from "@/lib/i18n";

export default function NotFound() {
    const t = useT();

    return (
        <div className="flex items-center justify-center min-h-screen bg-[#060610] text-white">
            <div className="text-center space-y-6 max-w-md px-6">
                {/* 404 graphic */}
                <div className="relative mx-auto w-28 h-28">
                    <div className="absolute inset-0 rounded-full bg-[#E11D48]/[0.06] blur-2xl" />
                    <div className="relative w-28 h-28 rounded-full bg-gradient-to-br from-white/[0.04] to-white/[0.01] border border-white/[0.06] flex items-center justify-center">
                        <span className="text-4xl font-bold text-gray-500 tabular-nums">404</span>
                    </div>
                </div>

                <div className="space-y-2">
                    <h1 className="text-xl font-semibold text-gray-100">{t("notFound.title")}</h1>
                    <p className="text-sm text-gray-400 leading-relaxed">
                        {t("notFound.desc")}
                    </p>
                </div>

                <Link
                    href="/"
                    className="inline-block px-6 py-2.5 rounded-xl bg-[#E11D48] hover:bg-[#BE123C] text-white text-sm font-medium transition-colors"
                >
                    {t("notFound.backToHome")}
                </Link>
            </div>
        </div>
    );
}
