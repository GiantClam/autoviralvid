import { NextRequest, NextResponse } from "next/server";
import { SignJWT } from "jose";
import http from "node:http";
import https from "node:https";
import { auth } from "@/lib/auth";
import { checkQuota, consumeQuota, refundQuota } from "@/lib/quota";
import { getAgentServiceUrl, getAuthSecret } from "@/lib/runtime-env";
import {
  buildNormalizedProxyPath,
  resolveGenerationChargeRule,
} from "@/lib/billing/charge-policy";

type SessionLike = {
  user?: {
    id?: string | null;
    email?: string | null;
  };
} | null;

const DEFAULT_LONG_REQUEST_TIMEOUT_MS = 45 * 60 * 1000;

function shouldUseLongRequestTransport(method: string, normalizedPath: string): boolean {
  if (method !== "POST") return false;
  return normalizedPath === "/ppt/generate-from-prompt";
}

function normalizeNodeHeaders(headers: http.IncomingHttpHeaders): HeadersInit {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(headers)) {
    if (value === undefined) continue;
    out[key] = Array.isArray(value) ? value.join(", ") : String(value);
  }
  return out;
}

async function requestViaNodeTransport(
  url: URL,
  init: RequestInit,
  timeoutMs: number,
): Promise<Response> {
  const isHttps = url.protocol === "https:";
  const transport = isHttps ? https : http;

  return new Promise<Response>((resolve, reject) => {
    const request = transport.request(
      {
        protocol: url.protocol,
        hostname: url.hostname,
        port: url.port ? Number(url.port) : isHttps ? 443 : 80,
        path: `${url.pathname}${url.search}`,
        method: init.method,
        headers: (init.headers || {}) as http.OutgoingHttpHeaders,
      },
      (response) => {
        const chunks: Buffer[] = [];
        response.on("data", (chunk) => {
          chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
        });
        response.on("end", () => {
          resolve(
            new Response(Buffer.concat(chunks), {
              status: response.statusCode || 502,
              headers: normalizeNodeHeaders(response.headers),
            }),
          );
        });
      },
    );

    request.setTimeout(timeoutMs, () => {
      request.destroy(new Error(`Upstream request timeout after ${timeoutMs}ms`));
    });
    request.on("error", reject);

    if (typeof init.body === "string" && init.body.length > 0) {
      request.write(init.body);
    }
    request.end();
  });
}

function isBackendSuccess(response: Response, text: string): boolean {
  if (!response.ok) return false;

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    return true;
  }

  try {
    const payload = JSON.parse(text) as { success?: boolean };
    if (typeof payload.success === "boolean") {
      return payload.success;
    }
  } catch {
    // Non-JSON or non-enveloped JSON response, keep status-code semantics.
  }
  return true;
}

async function buildBackendHeaders(request: NextRequest, session: SessionLike) {
  const headers: Record<string, string> = {};
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers["Content-Type"] = contentType;
  }

  const userId = session?.user?.id;
  if (userId) {
    const secretKey = new TextEncoder().encode(getAuthSecret());
    const token = await new SignJWT({
      sub: userId,
      email: session?.user?.email || "",
    })
      .setProtectedHeader({ alg: "HS256" })
      .setIssuedAt()
      .setExpirationTime("5m")
      .sign(secretKey);
    headers.Authorization = `Bearer ${token}`;
  }

  return headers;
}

export type ProxyForwardOptions = {
  method: string;
  path: string[];
  upstreamPrefixSegments?: readonly string[];
  billingPrefixSegments?: readonly string[];
};

export async function forwardApiV1Request(
  request: NextRequest,
  options: ProxyForwardOptions,
) {
  const upstreamPrefixSegments = options.upstreamPrefixSegments ?? [];
  const billingPrefixSegments = options.billingPrefixSegments ?? upstreamPrefixSegments;
  const method = options.method.toUpperCase();
  let charged = false;
  let chargedUserId = "";
  let chargedUnits = 0;

  try {
    const backendUrl = getAgentServiceUrl();
    const incomingUrl = new URL(request.url);
    const upstreamSegments = [...upstreamPrefixSegments, ...(options.path || [])];
    const targetPath = upstreamSegments.map(encodeURIComponent).join("/");
    const targetUrl = new URL(`${backendUrl}/api/v1/${targetPath}`);
    targetUrl.search = incomingUrl.search;

    const normalizedBillingPath = buildNormalizedProxyPath(
      options.path || [],
      billingPrefixSegments,
    );

    const session = (await auth()) as SessionLike;
    const userId = (session?.user?.id || "").trim();

    const billingFlag =
      process.env.UI_E2E_GENERATION_BILLING_ENABLED ??
      process.env.GENERATION_BILLING_ENABLED;
    const billingEnabled = billingFlag !== "false";
    const chargeRule = billingEnabled
      ? resolveGenerationChargeRule(method, normalizedBillingPath)
      : null;

    if (chargeRule) {
      if (!userId) {
        return NextResponse.json(
          { error: "Authentication required for generation billing" },
          { status: 401 },
        );
      }

      chargedUnits = chargeRule.units;
      try {
        const consumed = await consumeQuota(userId, chargedUnits);
        if (!consumed) {
          const quota = await checkQuota(userId);
          return NextResponse.json(
            {
              error: "quota_exceeded",
              units: chargedUnits,
              rule: chargeRule.id,
              quota,
            },
            { status: 402 },
          );
        }
        charged = true;
        chargedUserId = userId;
      } catch (billingError) {
        return NextResponse.json(
          {
            error: "billing_unavailable",
            detail:
              billingError instanceof Error
                ? billingError.message
                : String(billingError),
          },
          { status: 503 },
        );
      }
    }

    const headers = await buildBackendHeaders(request, session);
    const init: RequestInit = {
      method,
      headers,
      cache: "no-store",
    };

    if (method !== "GET" && method !== "HEAD") {
      init.body = await request.text();
    }

    const longRequestTransport = shouldUseLongRequestTransport(
      method,
      normalizedBillingPath,
    );
    const timeoutMs = Number(process.env.PROXY_LONG_REQUEST_TIMEOUT_MS) ||
      DEFAULT_LONG_REQUEST_TIMEOUT_MS;
    const response = longRequestTransport
      ? await requestViaNodeTransport(targetUrl, init, timeoutMs)
      : await fetch(targetUrl, init);
    const text = await response.text();

    if (charged && chargedUserId && !isBackendSuccess(response, text)) {
      try {
        await refundQuota(chargedUserId, chargedUnits);
      } catch {
        // Keep original backend response; refund failure should not mask business error.
      }
    }

    return new NextResponse(text, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") || "application/json",
      },
    });
  } catch (error) {
    if (charged && chargedUserId) {
      try {
        await refundQuota(chargedUserId, chargedUnits);
      } catch {
        // ignore secondary refund errors in generic failure path
      }
    }
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unknown proxy error" },
      { status: 500 },
    );
  }
}
