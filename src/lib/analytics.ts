/**
 * Analytics abstraction layer.
 *
 * Provides a unified `track()` API for event-based analytics.
 * Replace the `_send` implementation with your preferred provider
 * (Google Analytics, Mixpanel, PostHog, Plausible, etc.).
 *
 * Usage:
 *   import { analytics } from '@/lib/analytics';
 *   analytics.track('project_created', { template: 'digital-human' });
 */

type EventProperties = Record<string, string | number | boolean | null>;

// ---------------------------------------------------------------------------
// Provider implementation — swap this for production
// ---------------------------------------------------------------------------

function _send(event: string, properties?: EventProperties) {
    // Google Analytics (gtag) example:
    if (typeof window !== "undefined" && "gtag" in window) {
        (window as any).gtag("event", event, properties);
        return;
    }

    // Fallback: log to console in development
    if (process.env.NODE_ENV === "development") {
        console.debug(`[analytics] ${event}`, properties);
    }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export const analytics = {
    /** Track a custom event */
    track(event: string, properties?: EventProperties) {
        try {
            _send(event, properties);
        } catch {
            // Never let analytics errors break the app
        }
    },

    /** Track a page view (called automatically by AnalyticsProvider) */
    pageView(url: string) {
        this.track("page_view", { page_path: url });
    },

    // ── Convenience methods for common events ──

    projectCreated(templateId: string) {
        this.track("project_created", { template_id: templateId });
    },

    videoGenerated(runId: string, segmentCount: number) {
        this.track("video_generated", { run_id: runId, segment_count: segmentCount });
    },

    videoCompleted(runId: string) {
        this.track("video_completed", { run_id: runId });
    },

    userSignedUp(method: string) {
        this.track("sign_up", { method });
    },

    userSignedIn(method: string) {
        this.track("sign_in", { method });
    },

    subscriptionStarted(plan: string) {
        this.track("subscription_started", { plan });
    },

    fileUploaded(type: "image" | "audio", sizeMB: number) {
        this.track("file_uploaded", { file_type: type, size_mb: sizeMB });
    },
};
