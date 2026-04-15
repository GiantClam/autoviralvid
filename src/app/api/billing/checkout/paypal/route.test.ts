import { describe, expect, it, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

const authMock = vi.fn();
const createSubscriptionMock = vi.fn();
const getPlanCatalogMock = vi.fn();

vi.mock("@/lib/auth", () => ({
  auth: authMock,
}));

vi.mock("@/lib/paypal", () => ({
  createSubscription: createSubscriptionMock,
}));

vi.mock("@/lib/billing/plan-catalog", () => ({
  getPlanCatalog: getPlanCatalogMock,
}));

describe("billing paypal checkout route", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authMock.mockResolvedValue({ user: { id: "u1", email: "a@example.com" } });
    getPlanCatalogMock.mockReturnValue({
      free: { code: "free", providerPlanIds: {} },
      pro: { code: "pro", providerPlanIds: { paypal: "P-1", stripe: "price_1" } },
      enterprise: {
        code: "enterprise",
        providerPlanIds: { paypal: "P-2", stripe: "price_2" },
      },
    });
  });

  it("returns provider_unavailable when paypal plan id is missing", async () => {
    getPlanCatalogMock.mockReturnValueOnce({
      free: { code: "free", providerPlanIds: {} },
      pro: { code: "pro", providerPlanIds: { paypal: "", stripe: "price_1" } },
      enterprise: {
        code: "enterprise",
        providerPlanIds: { paypal: "P-2", stripe: "price_2" },
      },
    });

    const { POST } = await import("./route");
    const req = new NextRequest("http://localhost/api/billing/checkout/paypal", {
      method: "POST",
      headers: { "content-type": "application/json", origin: "http://localhost" },
      body: JSON.stringify({ plan: "pro" }),
    });

    const response = await POST(req);
    const payload = await response.json();

    expect(response.status).toBe(400);
    expect(payload.error).toBe("provider_unavailable");
    expect(createSubscriptionMock).not.toHaveBeenCalled();
  });

  it("creates paypal checkout when plan is valid", async () => {
    createSubscriptionMock.mockResolvedValue({
      subscriptionId: "I-123",
      approvalUrl: "https://paypal.test/approve",
      status: "APPROVAL_PENDING",
    });

    const { POST } = await import("./route");
    const req = new NextRequest("http://localhost/api/billing/checkout/paypal", {
      method: "POST",
      headers: { "content-type": "application/json", origin: "http://localhost" },
      body: JSON.stringify({ plan: "pro" }),
    });

    const response = await POST(req);
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.provider).toBe("paypal");
    expect(payload.url).toBe("https://paypal.test/approve");
    expect(createSubscriptionMock).toHaveBeenCalledTimes(1);
    expect(createSubscriptionMock).toHaveBeenCalledWith(
      "pro",
      "http://localhost/?billing_success=1&provider=paypal&plan=pro",
      "http://localhost/?billing_cancel=1&provider=paypal",
      "u1",
    );
  });
});
