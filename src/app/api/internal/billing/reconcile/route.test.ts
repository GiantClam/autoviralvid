import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const runBillingReconcileMock = vi.fn();

vi.mock("@/lib/billing/reconcile", () => ({
  runBillingReconcile: runBillingReconcileMock,
}));

describe("internal billing reconcile route", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    delete process.env.BILLING_RECONCILE_TOKEN;
    delete process.env.CRON_SECRET;
  });

  it("returns 503 when token is not configured", async () => {
    const { GET } = await import("./route");
    const request = new NextRequest("http://localhost/api/internal/billing/reconcile");
    const response = await GET(request);
    const payload = await response.json();

    expect(response.status).toBe(503);
    expect(payload.error).toContain("token");
  });

  it("returns 401 when token does not match", async () => {
    process.env.BILLING_RECONCILE_TOKEN = "secret";
    const { GET } = await import("./route");
    const request = new NextRequest("http://localhost/api/internal/billing/reconcile");
    const response = await GET(request);
    const payload = await response.json();

    expect(response.status).toBe(401);
    expect(payload.error).toBe("Unauthorized");
  });

  it("runs reconcile when request is authorized", async () => {
    process.env.BILLING_RECONCILE_TOKEN = "secret";
    runBillingReconcileMock.mockResolvedValue({
      generatedAt: "2026-04-14T00:00:00.000Z",
      lookbackHours: 24,
      summary: {
        activeSubscriptionsChecked: 0,
        staleUsageRecords: 0,
        failedWebhookEvents: 0,
        negativeBalances: 0,
        mismatches: 0,
        hasCritical: false,
      },
      mismatches: [],
    });

    const { GET } = await import("./route");
    const request = new NextRequest(
      "http://localhost/api/internal/billing/reconcile?lookbackHours=24&staleMinutes=15",
      {
        headers: { authorization: "Bearer secret" },
      },
    );
    const response = await GET(request);
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.ok).toBe(true);
    expect(payload.alert).toBe(false);
    expect(runBillingReconcileMock).toHaveBeenCalledWith({
      lookbackHours: 24,
      staleMinutes: 15,
    });
  });
});
