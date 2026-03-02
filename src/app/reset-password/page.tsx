"use client";

import React, { useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

function ResetPasswordForm() {
    const searchParams = useSearchParams();
    const token = searchParams.get("token");
    const email = searchParams.get("email");

    const [password, setPassword] = useState("");
    const [confirm, setConfirm] = useState("");
    const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
    const [errorMsg, setErrorMsg] = useState("");

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (password.length < 6) {
            setErrorMsg("密码至少 6 个字符");
            return;
        }
        if (password !== confirm) {
            setErrorMsg("两次输入的密码不一致");
            return;
        }

        setStatus("loading");
        setErrorMsg("");

        try {
            const res = await fetch("/api/auth/reset-password", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token, email, password }),
            });

            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.error || "重置失败");
            }

            setStatus("success");
        } catch (err) {
            setErrorMsg(err instanceof Error ? err.message : "重置失败");
            setStatus("error");
        }
    };

    if (!token || !email) {
        return (
            <div className="text-center space-y-4">
                <p className="text-gray-400">无效的重置链接</p>
                <Link href="/" className="text-[#E11D48] hover:underline text-sm">返回首页</Link>
            </div>
        );
    }

    if (status === "success") {
        return (
            <div className="text-center space-y-4">
                <div className="w-16 h-16 mx-auto rounded-2xl bg-emerald-500/[0.08] border border-emerald-500/20 flex items-center justify-center">
                    <svg className="w-8 h-8 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                </div>
                <h2 className="text-lg font-semibold text-gray-100">密码已重置</h2>
                <p className="text-sm text-gray-400">请使用新密码登录。</p>
                <Link
                    href="/"
                    className="inline-block px-6 py-2.5 rounded-xl bg-[#E11D48] hover:bg-[#BE123C] text-white text-sm font-medium transition-colors"
                >
                    去登录
                </Link>
            </div>
        );
    }

    return (
        <form onSubmit={handleSubmit} className="space-y-5 w-full max-w-sm">
            <div className="text-center space-y-1">
                <h2 className="text-lg font-semibold text-gray-100">重置密码</h2>
                <p className="text-sm text-gray-500">{email}</p>
            </div>

            {errorMsg && (
                <div className="px-4 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-sm text-red-400">
                    {errorMsg}
                </div>
            )}

            <div className="space-y-3">
                <input
                    type="password"
                    placeholder="新密码（至少 6 位）"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl bg-white/[0.04] border border-white/[0.08] text-sm text-white placeholder:text-gray-600 focus:outline-none focus:border-[#E11D48]/40"
                    required
                    minLength={6}
                />
                <input
                    type="password"
                    placeholder="确认新密码"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl bg-white/[0.04] border border-white/[0.08] text-sm text-white placeholder:text-gray-600 focus:outline-none focus:border-[#E11D48]/40"
                    required
                    minLength={6}
                />
            </div>

            <button
                type="submit"
                disabled={status === "loading"}
                className="w-full py-3 rounded-xl bg-[#E11D48] hover:bg-[#BE123C] disabled:opacity-50 text-white text-sm font-medium transition-colors"
            >
                {status === "loading" ? "处理中…" : "重置密码"}
            </button>
        </form>
    );
}

export default function ResetPasswordPage() {
    return (
        <div className="flex items-center justify-center min-h-screen bg-[#060610] text-white px-6">
            <Suspense fallback={
                <div className="w-8 h-8 border-2 border-[#E11D48] border-t-transparent rounded-full animate-spin" />
            }>
                <ResetPasswordForm />
            </Suspense>
        </div>
    );
}
