/**
 * Sentry error monitoring — placeholder integration.
 *
 * To enable:
 * 1. `npm install @sentry/nextjs`
 * 2. Set NEXT_PUBLIC_SENTRY_DSN in your environment
 * 3. Uncomment the init() call below
 *
 * This file provides a safe no-op when Sentry is not configured,
 * so the rest of the app can always call `captureException()`.
 */

const SENTRY_DSN = process.env.NEXT_PUBLIC_SENTRY_DSN;

let _initialized = false;

export function initSentry() {
    if (_initialized || !SENTRY_DSN) return;
    _initialized = true;

    // Uncomment when @sentry/nextjs is installed:
    // import("@sentry/nextjs").then((Sentry) => {
    //     Sentry.init({
    //         dsn: SENTRY_DSN,
    //         environment: process.env.NODE_ENV,
    //         tracesSampleRate: 0.1,
    //         replaysSessionSampleRate: 0,
    //         replaysOnErrorSampleRate: 1.0,
    //     });
    // });
}

export function captureException(error: unknown, context?: Record<string, unknown>) {
    if (!SENTRY_DSN) {
        console.error("[sentry-placeholder]", error, context);
        return;
    }

    // Uncomment when @sentry/nextjs is installed:
    // import("@sentry/nextjs").then((Sentry) => {
    //     Sentry.captureException(error, { extra: context });
    // });
}

export function captureMessage(message: string, level: "info" | "warning" | "error" = "info") {
    if (!SENTRY_DSN) {
        console.log(`[sentry-placeholder:${level}]`, message);
        return;
    }

    // Uncomment when @sentry/nextjs is installed:
    // import("@sentry/nextjs").then((Sentry) => {
    //     Sentry.captureMessage(message, level);
    // });
}
