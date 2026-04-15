export const dynamic = "force-dynamic";

import { NextRequest, NextResponse } from "next/server";
import { getErrorMessage } from "@/lib/errors";
import { runBillingReconcile } from "@/lib/billing/reconcile";

function getBearerToken(request: NextRequest): string {
  const authHeader = request.headers.get("authorization") || "";
  const match = authHeader.match(/^Bearer\s+(.+)$/i);
  return match?.[1]?.trim() || "";
}

function isAuthorized(request: NextRequest): boolean {
  const bearer = getBearerToken(request);
  const headerToken = request.headers.get("x-internal-token") || "";
  const queryToken = request.nextUrl.searchParams.get("token") || "";
  const expected =
    process.env.BILLING_RECONCILE_TOKEN || process.env.CRON_SECRET || "";

  if (!expected) return false;
  return bearer === expected || headerToken === expected || queryToken === expected;
}

export async function GET(request: NextRequest) {
  try {
    const expected =
      process.env.BILLING_RECONCILE_TOKEN || process.env.CRON_SECRET || "";
    if (!expected) {
      return NextResponse.json(
        { error: "Billing reconcile token is not configured" },
        { status: 503 },
      );
    }

    if (!isAuthorized(request)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const lookbackHoursRaw = Number(request.nextUrl.searchParams.get("lookbackHours"));
    const staleMinutesRaw = Number(request.nextUrl.searchParams.get("staleMinutes"));

    const report = await runBillingReconcile({
      lookbackHours: Number.isFinite(lookbackHoursRaw) ? lookbackHoursRaw : undefined,
      staleMinutes: Number.isFinite(staleMinutesRaw) ? staleMinutesRaw : undefined,
    });

    return NextResponse.json({
      ok: true,
      report,
      alert: report.summary.hasCritical || report.summary.mismatches > 0,
    });
  } catch (error) {
    return NextResponse.json(
      { error: getErrorMessage(error, "Failed to reconcile billing") },
      { status: 500 },
    );
  }
}
