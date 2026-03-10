"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
} from "react";
import en from "./en";
import zh from "./zh";

export type Locale = "zh" | "en";

type Dict = typeof zh;

type Leaves<T, Prefix extends string = ""> = T extends object
  ? {
      [K in keyof T & string]: T[K] extends object
        ? Leaves<T[K], `${Prefix}${K}.`>
        : `${Prefix}${K}`;
    }[keyof T & string]
  : never;

export type TranslationKey = Leaves<Dict>;

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

const DICTS: Record<Locale, Record<string, string>> = {
  zh: flatten(zh as unknown as Record<string, unknown>),
  en: flatten(en as unknown as Record<string, unknown>),
};

const LOCALE_KEY = "autoviralvid-locale";
const LOCALE_EVENT = "autoviralvid-locale-change";

function getInitialLocale(): Locale {
  if (typeof window === "undefined") return "zh";
  try {
    const stored = localStorage.getItem(LOCALE_KEY);
    if (stored === "zh" || stored === "en") return stored;

    return navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en";
  } catch {
    return "zh";
  }
}

interface LocaleContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: TranslationKey, params?: Record<string, string | number>) => string;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

function subscribeLocaleChange(onStoreChange: () => void) {
  if (typeof window === "undefined") {
    return () => {};
  }

  const handleChange = () => onStoreChange();
  window.addEventListener("storage", handleChange);
  window.addEventListener(LOCALE_EVENT, handleChange);

  return () => {
    window.removeEventListener("storage", handleChange);
    window.removeEventListener(LOCALE_EVENT, handleChange);
  };
}

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const locale = useSyncExternalStore<Locale>(
    subscribeLocaleChange,
    getInitialLocale,
    () => "zh",
  );

  const setLocale = useCallback((newLocale: Locale) => {
    try {
      localStorage.setItem(LOCALE_KEY, newLocale);
    } catch {
      // ignore storage failures
    }

    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event(LOCALE_EVENT));
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
  }, [locale]);

  const t = useCallback(
    (key: TranslationKey, params?: Record<string, string | number>): string => {
      const localeDict = DICTS[locale];
      let text = localeDict[key] ?? DICTS.zh[key] ?? key;
      if (params) {
        for (const [paramKey, value] of Object.entries(params)) {
          text = text.replace(`{${paramKey}}`, String(value));
        }
      }
      return text;
    },
    [locale],
  );

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const ctx = useContext(LocaleContext);
  if (!ctx) {
    throw new Error("useLocale must be used within LocaleProvider");
  }
  return ctx;
}

export function useT() {
  return useLocale().t;
}
