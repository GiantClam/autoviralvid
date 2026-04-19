export const dynamic = "force-dynamic";

import { NextRequest, NextResponse } from "next/server";
import { getAgentServiceUrl } from "@/lib/runtime-env";

function getBearerToken(request: NextRequest): string {
  const authHeader = request.headers.get("authorization") || "";
  const match = authHeader.match(/^Bearer\s+(.+)$/i);
  return match?.[1]?.trim() || "";
}

function getExpectedTokens(): string[] {
  const tokens = [
    process.env.PPT_PROMPT_DISPATCH_TOKEN,
    process.env.PPT_EXPORT_WORKER_TOKEN,
    process.env.CRON_SECRET,
    process.env.BILLING_RECONCILE_TOKEN,
  ]
    .map((token) => token?.trim() || "")
    .filter(Boolean);
  return Array.from(new Set(tokens));
}

function getDispatchToken(): string {
  const tokens = getExpectedTokens();
  return tokens[0] || "";
}

function isAuthorized(request: NextRequest): boolean {
  const expectedTokens = getExpectedTokens();
  if (!expectedTokens.length) return false;
  const bearer = getBearerToken(request);
  const headerToken = request.headers.get("x-internal-token") || "";
  const queryToken = request.nextUrl.searchParams.get("token") || "";
  return (
    expectedTokens.includes(bearer) ||
    expectedTokens.includes(headerToken) ||
    expectedTokens.includes(queryToken)
  );
}

function getDispatchBaseUrl(): string {
  const raw = process.env.PPT_EXPORT_WORKER_BASE_URL || getAgentServiceUrl();
  return raw.replace(/\/+$/, "");
}

async function forwardDispatch(request: NextRequest) {
  const expected = getDispatchToken();
  if (!expected) {
    return NextResponse.json(
      { error: "PPT dispatch token is not configured" },
      { status: 503 },
    );
  }
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const jobId = request.nextUrl.searchParams.get("job_id")?.trim() || "";
  const limitRaw = Number(request.nextUrl.searchParams.get("limit"));
  const limit = Number.isFinite(limitRaw) ? Math.max(1, Math.min(20, limitRaw)) : 1;

  const target = `${getDispatchBaseUrl()}/api/v1/ppt/internal/prompt-jobs/dispatch`;
  const response = await fetch(target, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-internal-token": expected,
    },
    body: JSON.stringify({
      job_id: jobId || null,
      limit,
    }),
    cache: "no-store",
  });
  const text = await response.text();
  return new NextResponse(text, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "application/json",
    },
  });
}

export async function GET(request: NextRequest) {
  try {
    return await forwardDispatch(request);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to dispatch prompt jobs" },
      { status: 500 },
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    return await forwardDispatch(request);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to dispatch prompt jobs" },
      { status: 500 },
    );
  }
}
