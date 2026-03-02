"use client";

import React from "react";
import { Globe } from "lucide-react";
import { useLocale, type Locale } from "@/lib/i18n";

/**
 * Compact language toggle — cycles between zh and en.
 * Designed to sit in a sidebar, header, or floating position.
 */
export default function LanguageSwitcher({ className = "" }: { className?: string }) {
  const { locale, setLocale, t } = useLocale();

  const toggle = () => {
    const next: Locale = locale === "zh" ? "en" : "zh";
    setLocale(next);
  };

  return (
    <button
      onClick={toggle}
      className={`flex items-center gap-2 px-3 py-2 rounded-xl text-gray-400 hover:text-white
                  hover:bg-white/[0.04] transition-all duration-200 text-sm cursor-pointer ${className}`}
      title={t("language.switchLang")}
    >
      <Globe className="w-4 h-4" />
      <span className="text-xs font-medium">
        {locale === "zh" ? t("language.en") : t("language.zh")}
      </span>
    </button>
  );
}
