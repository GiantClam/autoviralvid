"use client";

import React from "react";
import { useT } from "@/lib/i18n";

export default function Error({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    const t = useT();

    React.useEffect(() => {
        console.error("[ErrorBoundary]", error);
    }, [error]);

    return (
        <div className="flex items-center justify-center min-h-screen bg-[#060610] text-white">
            <div className="text-center space-y-6 max-w-md px-6">
                {/* Icon */}
                <div className="mx-auto w-20 h-20 rounded-3xl bg-red-500/[0.08] border border-red-500/20 flex items-center justify-center">
                    <svg className="w-10 h-10 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                    </svg>
                </div>

                <div className="space-y-2">
                    <h2 className="text-xl font-semibold text-gray-100">{t("errorPage.title")}</h2>
                    <p className="text-sm text-gray-400 leading-relaxed">
                        {t("errorPage.desc")}
                    </p>
                    {error.digest && (
                        <p className="text-xs text-gray-600 font-mono">
                            {t("errorPage.errorCode")}: {error.digest}
                        </p>
                    )}
                </div>

                <button
                    onClick={reset}
                    className="px-6 py-2.5 rounded-xl bg-[#E11D48] hover:bg-[#BE123C] text-white text-sm font-medium transition-colors"
                >
                    {t("errorPage.reload")}
                </button>
            </div>
        </div>
    );
}
