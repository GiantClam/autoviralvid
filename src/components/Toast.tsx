"use client";

import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from "react";
import { X, CheckCircle2, AlertTriangle, Info, XCircle } from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ToastVariant = "success" | "error" | "warning" | "info";

interface ToastItem {
    id: string;
    message: string;
    variant: ToastVariant;
    duration: number; // ms, 0 = manual dismiss
}

interface ToastContextType {
    toast: (message: string, variant?: ToastVariant, duration?: number) => void;
    success: (message: string, duration?: number) => void;
    error: (message: string, duration?: number) => void;
    warning: (message: string, duration?: number) => void;
    info: (message: string, duration?: number) => void;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function useToast() {
    const ctx = useContext(ToastContext);
    if (!ctx) throw new Error("useToast must be used within ToastProvider");
    return ctx;
}

// ---------------------------------------------------------------------------
// Styles per variant
// ---------------------------------------------------------------------------

const VARIANT_CONFIG: Record<ToastVariant, { icon: React.FC<{ className?: string }>; bg: string; border: string; text: string; gradient: string }> = {
    success: {
        icon: CheckCircle2,
        bg: "bg-emerald-500/[0.08]",
        border: "border-emerald-500/20",
        text: "text-emerald-400",
        gradient: "from-emerald-500/20 to-transparent",
    },
    error: {
        icon: XCircle,
        bg: "bg-red-500/[0.08]",
        border: "border-red-500/20",
        text: "text-red-400",
        gradient: "from-red-500/20 to-transparent",
    },
    warning: {
        icon: AlertTriangle,
        bg: "bg-amber-500/[0.08]",
        border: "border-amber-500/20",
        text: "text-amber-400",
        gradient: "from-amber-500/20 to-transparent",
    },
    info: {
        icon: Info,
        bg: "bg-sky-500/[0.08]",
        border: "border-sky-500/20",
        text: "text-sky-400",
        gradient: "from-sky-500/20 to-transparent",
    },
};

// ---------------------------------------------------------------------------
// Single toast item
// ---------------------------------------------------------------------------

function ToastItemView({ item, onDismiss }: { item: ToastItem; onDismiss: (id: string) => void }) {
    const cfg = VARIANT_CONFIG[item.variant];
    const Icon = cfg.icon;

    useEffect(() => {
        if (item.duration <= 0) return;
        const timer = setTimeout(() => onDismiss(item.id), item.duration);
        return () => clearTimeout(timer);
    }, [item.id, item.duration, onDismiss]);

    return (
        <div
            className={`relative flex items-center gap-3 px-4 py-3.5 rounded-2xl border backdrop-blur-xl shadow-2xl shadow-black/30 overflow-hidden animate-fade-in-up ${cfg.bg} ${cfg.border}`}
            role="alert"
        >
            <div className={`absolute inset-0 bg-gradient-to-r ${cfg.gradient} pointer-events-none`} />
            <div className={`relative w-8 h-8 rounded-xl flex items-center justify-center ${cfg.bg} ${cfg.border} border`}>
                <Icon className={`w-4 h-4 ${cfg.text}`} />
            </div>
            <p className="relative flex-1 text-sm font-medium text-gray-200">{item.message}</p>
            <button
                onClick={() => onDismiss(item.id)}
                className="relative p-1.5 rounded-lg hover:bg-white/[0.08] transition-colors cursor-pointer"
            >
                <X className="w-4 h-4 text-gray-500 hover:text-white transition-colors" />
            </button>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

let _nextId = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
    const [items, setItems] = useState<ToastItem[]>([]);
    const itemsRef = useRef(items);
    itemsRef.current = items;

    const dismiss = useCallback((id: string) => {
        setItems((prev) => prev.filter((t) => t.id !== id));
    }, []);

    const addToast = useCallback(
        (message: string, variant: ToastVariant = "info", duration = 4000) => {
            const id = `toast-${++_nextId}`;
            setItems((prev) => [...prev.slice(-4), { id, message, variant, duration }]); // keep max 5
        },
        [],
    );

    const ctx: ToastContextType = {
        toast: addToast,
        success: (msg, dur) => addToast(msg, "success", dur),
        error: (msg, dur) => addToast(msg, "error", dur ?? 6000),
        warning: (msg, dur) => addToast(msg, "warning", dur),
        info: (msg, dur) => addToast(msg, "info", dur),
    };

    return (
        <ToastContext.Provider value={ctx}>
            {children}

            {/* Toast container — top-right overlay */}
            {items.length > 0 && (
                <div className="fixed top-4 right-4 z-[9999] flex flex-col gap-2 w-[380px] max-w-[calc(100vw-2rem)]">
                    {items.map((item) => (
                        <ToastItemView key={item.id} item={item} onDismiss={dismiss} />
                    ))}
                </div>
            )}
        </ToastContext.Provider>
    );
}
