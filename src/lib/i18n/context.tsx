"use client";

import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useMemo,
} from "react";
import zh from "./zh";
import en from "./en";

// ── Types ──

export type Locale = "zh" | "en";

type Dict = typeof zh;

/** Recursively extract dot-separated leaf keys from nested object type */
type Leaves<T, Prefix extends string = ""> = T extends object
  ? {
      [K in keyof T & string]: T[K] extends object
        ? Leaves<T[K], `${Prefix}${K}.`>
        : `${Prefix}${K}`;
    }[keyof T & string]
  : never;

export type TranslationKey = Leaves<Dict>;

// ── Flatten utility ──

function flatten(obj: Record<string, unknown>, prefix = ""): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
      Object.assign(result, flatten(value as Record<string, unknown>, path));
    } else {
      result[path] = String(value);
    }
  }
  return result;
}

// Pre-flatten dictionaries for fast runtime lookup
const DICTS: Record<Locale, Record<string, string>> = {
  zh: flatten(zh as unknown as Record<string, unknown>),
  en: flatten(en as unknown as Record<string, unknown>),
};

const LOCALE_KEY = "autoviralvid-locale";

function getInitialLocale(): Locale {
  if (typeof window === "undefined") return "zh";
  try {
    const stored = localStorage.getItem(LOCALE_KEY);
    if (stored === "zh" || stored === "en") return stored;
    // Auto-detect from browser language
    const browserLang = navigator.language.toLowerCase();
    if (browserLang.startsWith("zh")) return "zh";
    return "en";
  } catch {
    return "zh";
  }
}

// ── Context ──

interface LocaleContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: TranslationKey, params?: Record<string, string | number>) => string;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

// ── Provider ──

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("zh"); // SSR default
  const [hydrated, setHydrated] = useState(false);

  // Hydrate from localStorage after mount
  useEffect(() => {
    setLocaleState(getInitialLocale());
    setHydrated(true);
  }, []);

  const setLocale = useCallback((newLocale: Locale) => {
    setLocaleState(newLocale);
    try {
      localStorage.setItem(LOCALE_KEY, newLocale);
    } catch { /* ignore */ }
    // Update html lang attribute
    document.documentElement.lang = newLocale === "zh" ? "zh-CN" : "en";
  }, []);

  // Update html lang on mount
  useEffect(() => {
    if (hydrated) {
      document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
    }
  }, [locale, hydrated]);

  const t = useCallback(
    (key: TranslationKey, params?: Record<string, string | number>): string => {
      let text = DICTS[locale][key] ?? DICTS.zh[key] ?? key;
      if (params) {
        for (const [k, v] of Object.entries(params)) {
          text = text.replace(`{${k}}`, String(v));
        }
      }
      return text;
    },
    [locale],
  );

  const value = useMemo(
    () => ({ locale, setLocale, t }),
    [locale, setLocale, t],
  );

  return (
    <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
  );
}

// ── Hooks ──

export function useLocale() {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error("useLocale must be used within LocaleProvider");
  return ctx;
}

/** Shorthand: returns just the `t` function */
export function useT() {
  return useLocale().t;
}
