const LOCAL_AGENT_URL = "http://localhost:8123";
const LOCAL_APP_URL = "http://localhost:3000";
const DEV_AUTH_SECRET = "dev-secret-change-in-production";

function stripTrailingSlash(value: string) {
    return value.replace(/\/+$/, "");
}

export function isProductionDeployment() {
    return process.env.NODE_ENV === "production" || process.env.VERCEL === "1";
}

export function getAuthSecret() {
    const secret = process.env.AUTH_SECRET || process.env.NEXTAUTH_SECRET;
    if (secret) return secret;

    if (isProductionDeployment()) {
        throw new Error("Missing AUTH_SECRET or NEXTAUTH_SECRET for production deployment.");
    }

    return DEV_AUTH_SECRET;
}

export function getAgentServiceUrl() {
    const configured =
        process.env.AGENT_URL ||
        process.env.NEXT_PUBLIC_AGENT_URL ||
        process.env.NEXT_PUBLIC_API_BASE;

    if (configured) return stripTrailingSlash(configured);

    if (isProductionDeployment()) {
        throw new Error(
            "Missing AGENT_URL or NEXT_PUBLIC_AGENT_URL for production deployment.",
        );
    }

    return LOCAL_AGENT_URL;
}

export function getAppOrigin() {
    const configured =
        process.env.NEXTAUTH_URL ||
        process.env.NEXT_PUBLIC_SITE_URL ||
        process.env.SITE_URL;

    if (configured) return stripTrailingSlash(configured);

    const vercelUrl =
        process.env.VERCEL_URL || process.env.VERCEL_PROJECT_PRODUCTION_URL;
    if (vercelUrl) return `https://${stripTrailingSlash(vercelUrl)}`;

    if (isProductionDeployment()) {
        throw new Error(
            "Missing NEXTAUTH_URL or NEXT_PUBLIC_SITE_URL for production deployment.",
        );
    }

    return LOCAL_APP_URL;
}

export function getPublicAgentBaseUrl() {
    const configured =
        process.env.NEXT_PUBLIC_API_BASE ||
        process.env.NEXT_PUBLIC_AGENT_URL ||
        process.env.AGENT_URL;

    if (configured) return stripTrailingSlash(configured);

    if (isProductionDeployment()) {
        throw new Error(
            "Missing NEXT_PUBLIC_API_BASE or NEXT_PUBLIC_AGENT_URL for production deployment.",
        );
    }

    return LOCAL_AGENT_URL;
}
