"use client";

import React from "react";
import { LocaleProvider } from "@/lib/i18n";
import { ToastProvider } from "@/components/Toast";

/**
 * Client-side providers wrapper.
 * Wraps children with LocaleProvider + ToastProvider.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <LocaleProvider>
      <ToastProvider>{children}</ToastProvider>
    </LocaleProvider>
  );
}
