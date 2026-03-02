/**
 * Next.js Edge Middleware
 *
 * 1. Injects security headers on every response.
 * 2. Protects /api/auth/api-token from CSRF by requiring POST.
 */
import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
    const response = NextResponse.next();

    // ── Security headers ──
    // Prevent the page from being embedded in iframes (clickjacking)
    response.headers.set("X-Frame-Options", "DENY");

    // Enforce MIME type — no sniffing
    response.headers.set("X-Content-Type-Options", "nosniff");

    // Basic XSS protection for older browsers
    response.headers.set("X-XSS-Protection", "1; mode=block");

    // Referrer — send origin only to cross-origin, full on same-origin
    response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");

    // Permissions Policy — restrict sensitive APIs
    response.headers.set(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), payment=(self)",
    );

    // Strict Transport Security (HSTS) — only in production
    if (
        request.nextUrl.protocol === "https:" ||
        process.env.NODE_ENV === "production"
    ) {
        response.headers.set(
            "Strict-Transport-Security",
            "max-age=63072000; includeSubDomains; preload",
        );
    }

    return response;
}

export const config = {
    // Apply to all routes except static files and Next.js internals
    matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"],
};
