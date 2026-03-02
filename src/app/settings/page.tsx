"use client";

import React from "react";
import { SessionProvider, useSession, signOut } from "next-auth/react";
import Link from "next/link";
import { ArrowLeft, User, Mail, Shield, LogOut } from "lucide-react";
import { useT } from "@/lib/i18n";
import LanguageSwitcher from "@/components/LanguageSwitcher";

function SettingsContent() {
    const { data: session, status } = useSession();
    const t = useT();

    if (status === "loading") {
        return (
            <div className="flex items-center justify-center min-h-screen bg-[#060610]">
                <div className="w-8 h-8 border-2 border-[#E11D48] border-t-transparent rounded-full animate-spin" />
            </div>
        );
    }

    if (status === "unauthenticated") {
        return (
            <div className="flex items-center justify-center min-h-screen bg-[#060610] text-white">
                <div className="text-center space-y-4">
                    <p className="text-gray-400">{t("settings.loginRequired")}</p>
                    <Link href="/" className="text-[#E11D48] hover:underline text-sm">{t("settings.backToHome")}</Link>
                </div>
            </div>
        );
    }

    const user = session?.user;

    return (
        <div className="min-h-screen bg-[#060610] text-white">
            {/* Header */}
            <div className="h-16 border-b border-white/[0.08] flex items-center px-4 md:px-8 gap-4">
                <Link href="/" className="p-2 rounded-lg hover:bg-white/[0.04] transition-colors">
                    <ArrowLeft className="w-4 h-4 text-gray-400" />
                </Link>
                <h1 className="font-semibold text-lg flex-1">{t("settings.title")}</h1>
                <LanguageSwitcher />
            </div>

            <div className="max-w-2xl mx-auto px-4 md:px-6 py-10 space-y-8">
                {/* Profile Section */}
                <section className="space-y-4">
                    <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider">{t("settings.profile")}</h2>
                    <div className="rounded-2xl bg-white/[0.02] border border-white/[0.06] divide-y divide-white/[0.06]">
                        <div className="flex items-center justify-between px-5 py-4">
                            <div className="flex items-center gap-3">
                                <User className="w-4 h-4 text-gray-500" />
                                <span className="text-sm text-gray-300">{t("settings.userId")}</span>
                            </div>
                            <span className="text-sm text-gray-500 font-mono">{user?.id || "—"}</span>
                        </div>
                        <div className="flex items-center justify-between px-5 py-4">
                            <div className="flex items-center gap-3">
                                <Mail className="w-4 h-4 text-gray-500" />
                                <span className="text-sm text-gray-300">{t("settings.email")}</span>
                            </div>
                            <span className="text-sm text-gray-400">{user?.email || "—"}</span>
                        </div>
                    </div>
                </section>

                {/* Security Section */}
                <section className="space-y-4">
                    <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider">{t("settings.security")}</h2>
                    <div className="rounded-2xl bg-white/[0.02] border border-white/[0.06]">
                        <div className="flex items-center justify-between px-5 py-4">
                            <div className="flex items-center gap-3">
                                <Shield className="w-4 h-4 text-gray-500" />
                                <span className="text-sm text-gray-300">{t("settings.changePassword")}</span>
                            </div>
                            <span className="text-xs text-gray-600">{t("settings.comingSoon")}</span>
                        </div>
                    </div>
                </section>

                {/* Legal links */}
                <section className="space-y-4">
                    <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider">{t("settings.legal")}</h2>
                    <div className="flex gap-4">
                        <Link href="/legal/terms" className="text-sm text-gray-500 hover:text-gray-300 transition-colors">
                            {t("settings.termsOfService")}
                        </Link>
                        <Link href="/legal/privacy" className="text-sm text-gray-500 hover:text-gray-300 transition-colors">
                            {t("settings.privacyPolicy")}
                        </Link>
                    </div>
                </section>

                {/* Sign out */}
                <div className="pt-4">
                    <button
                        onClick={() => signOut({ callbackUrl: "/" })}
                        className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white/[0.04] border border-white/[0.06] hover:bg-red-500/10 hover:border-red-500/20 text-gray-400 hover:text-red-400 text-sm transition-colors"
                    >
                        <LogOut className="w-4 h-4" />
                        {t("settings.signOut")}
                    </button>
                </div>
            </div>
        </div>
    );
}

export default function SettingsPage() {
    return (
        <SessionProvider>
            <SettingsContent />
        </SessionProvider>
    );
}
