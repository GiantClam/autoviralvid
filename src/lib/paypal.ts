/**
 * PayPal REST API client for subscription management.
 *
 * When PAYPAL_CLIENT_ID is not set, all functions return mock data
 * so the app can run in dev mode without PayPal credentials.
 */

// --- Plan Configuration ---

export interface PlanConfig {
    name: string;
    price: number;
    quotaTotal: number; // -1 = unlimited
    paypalPlanId: string;
    features: string[];
}

interface PayPalLink {
    rel?: string;
    href?: string;
}

interface PayPalCreateSubscriptionResponse {
    id: string;
    status: string;
    links?: PayPalLink[];
}

export const PLANS: Record<string, PlanConfig> = {
    free: {
        name: "Free",
        price: 0,
        quotaTotal: 3,
        paypalPlanId: "",
        features: ["3 videos / month", "720p quality", "Community support"],
    },
    pro: {
        name: "Pro",
        price: 9.9,
        quotaTotal: 30,
        paypalPlanId: process.env.PAYPAL_PLAN_PRO || "P-xxxPRO",
        features: ["30 videos / month", "1080p quality", "Priority rendering", "Email support"],
    },
    enterprise: {
        name: "Enterprise",
        price: 29.9,
        quotaTotal: -1,
        paypalPlanId: process.env.PAYPAL_PLAN_ENTERPRISE || "P-xxxENTERPRISE",
        features: ["Unlimited videos", "4K quality", "Priority rendering", "Custom branding", "Dedicated support"],
    },
};

// --- Mock mode detection ---

const isMockMode = () => !process.env.PAYPAL_CLIENT_ID;

// --- PayPal API ---

const PAYPAL_BASE =
    (process.env.PAYPAL_MODE || "sandbox") === "live"
        ? "https://api-m.paypal.com"
        : "https://api-m.sandbox.paypal.com";

async function getAccessToken(): Promise<string> {
    const clientId = process.env.PAYPAL_CLIENT_ID;
    const clientSecret = process.env.PAYPAL_CLIENT_SECRET;
    if (!clientId || !clientSecret) throw new Error("PayPal credentials not configured");

    const res = await fetch(`${PAYPAL_BASE}/v1/oauth2/token`, {
        method: "POST",
        headers: {
            Authorization: `Basic ${Buffer.from(`${clientId}:${clientSecret}`).toString("base64")}`,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        body: "grant_type=client_credentials",
    });

    if (!res.ok) throw new Error(`PayPal auth failed: ${res.status}`);
    const data = await res.json();
    return data.access_token;
}

export async function createSubscription(planKey: string, returnUrl: string, cancelUrl: string) {
    const plan = PLANS[planKey];
    if (!plan || !plan.paypalPlanId) throw new Error(`Invalid plan: ${planKey}`);

    // Mock mode — return fake approval URL
    if (isMockMode()) {
        console.log(`[PayPal MOCK] Creating subscription for plan: ${planKey}`);
        return {
            subscriptionId: `MOCK-SUB-${Date.now()}`,
            approvalUrl: `${returnUrl}&mock=true`,
            status: "APPROVAL_PENDING",
        };
    }

    const token = await getAccessToken();
    const res = await fetch(`${PAYPAL_BASE}/v1/billing/subscriptions`, {
        method: "POST",
        headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            plan_id: plan.paypalPlanId,
            application_context: {
                brand_name: "AutoViralVid",
                locale: "en-US",
                user_action: "SUBSCRIBE_NOW",
                return_url: returnUrl,
                cancel_url: cancelUrl,
            },
        }),
    });

    if (!res.ok) {
        const err = await res.text();
        throw new Error(`PayPal create subscription failed: ${res.status} ${err}`);
    }

    const data = (await res.json()) as PayPalCreateSubscriptionResponse;
    const approvalLink = data.links?.find((link) => link.rel === "approve")?.href;

    return {
        subscriptionId: data.id as string,
        approvalUrl: approvalLink as string,
        status: data.status as string,
    };
}

export async function getSubscriptionDetails(subscriptionId: string) {
    if (isMockMode()) {
        return { id: subscriptionId, status: "ACTIVE", plan_id: "P-xxxPRO" };
    }

    const token = await getAccessToken();
    const res = await fetch(`${PAYPAL_BASE}/v1/billing/subscriptions/${subscriptionId}`, {
        headers: { Authorization: `Bearer ${token}` },
    });

    if (!res.ok) throw new Error(`PayPal get subscription failed: ${res.status}`);
    return res.json();
}

export async function cancelSubscription(subscriptionId: string, reason = "User requested cancellation") {
    if (isMockMode()) {
        console.log(`[PayPal MOCK] Cancelling subscription: ${subscriptionId}`);
        return { success: true };
    }

    const token = await getAccessToken();
    const res = await fetch(`${PAYPAL_BASE}/v1/billing/subscriptions/${subscriptionId}/cancel`, {
        method: "POST",
        headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
        },
        body: JSON.stringify({ reason }),
    });

    if (!res.ok && res.status !== 204) {
        throw new Error(`PayPal cancel failed: ${res.status}`);
    }

    return { success: true };
}

