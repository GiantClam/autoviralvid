import { describe, expect, it, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

const authMock = vi.fn();
const createStripeCheckoutSessionMock = vi.fn();
const getPlanCatalogMock = vi.fn();

vi.mock("@/lib/auth", () => ({
  auth: authMock,
}));

vi.mock("@/lib/billing/stripe", () => ({
  createStripeCheckoutSession: createStripeCheckoutSessionMock,
}));

vi.mock("@/lib/billing/plan-catalog", () => ({
  getPlanCatalog: getPlanCatalogMock,
}));

describe("billing stripe checkout route", () => {
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

  it("returns provider_unavailable when stripe price id is missing", async () => {
    getPlanCatalogMock.mockReturnValueOnce({
      free: { code: "free", providerPlanIds: {} },
      pro: { code: "pro", providerPlanIds: { paypal: "P-1", stripe: "" } },
      enterprise: {
        code: "enterprise",
        providerPlanIds: { paypal: "P-2", stripe: "price_2" },
      },
    });

    const { POST } = await import("./route");
    const req = new NextRequest("http://localhost/api/billing/checkout/stripe", {
      method: "POST",
      headers: { "content-type": "application/json", origin: "http://localhost" },
      body: JSON.stringify({ plan: "pro" }),
    });

    const response = await POST(req);
    const payload = await response.json();

    expect(response.status).toBe(400);
    expect(payload.error).toBe("provider_unavailable");
    expect(createStripeCheckoutSessionMock).not.toHaveBeenCalled();
  });

  it("creates stripe checkout when plan is valid", async () => {
    createStripeCheckoutSessionMock.mockResolvedValue({
      checkoutUrl: "https://stripe.test/checkout",
      sessionId: "cs_123",
      status: "open",
    });

    const { POST } = await import("./route");
    const req = new NextRequest("http://localhost/api/billing/checkout/stripe", {
      method: "POST",
      headers: { "content-type": "application/json", origin: "http://localhost" },
      body: JSON.stringify({ plan: "pro" }),
    });

    const response = await POST(req);
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.provider).toBe("stripe");
    expect(payload.url).toBe("https://stripe.test/checkout");
    expect(createStripeCheckoutSessionMock).toHaveBeenCalledTimes(1);
  });
});
