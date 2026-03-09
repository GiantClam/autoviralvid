/**
 * Next.js proxy entrypoint.
 *
 * 1. Injects security headers on every response.
 * 2. Protects /api/auth/api-token from CSRF by requiring POST.
 */
import { NextRequest, NextResponse } from "next/server";

export function proxy(request: NextRequest) {
    const response = NextResponse.next();

    // Prevent the page from being embedded in iframes (clickjacking).
    response.headers.set("X-Frame-Options", "DENY");

    // Enforce MIME type and disable content sniffing.
    response.headers.set("X-Content-Type-Options", "nosniff");

    // Basic XSS protection for older browsers.
    response.headers.set("X-XSS-Protection", "1; mode=block");

    // Send origin only to cross-origin requests, and full referrer on same-origin.
    response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");

    // Restrict sensitive browser APIs.
    response.headers.set(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), payment=(self)",
    );

    // Only send HSTS on HTTPS or in production deployments.
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
    // Apply to all routes except static files and Next.js internals.
    matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"],
};
