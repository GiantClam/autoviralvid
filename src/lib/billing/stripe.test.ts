import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createStripeCheckoutSession } from "./stripe";

describe("stripe checkout", () => {
  beforeEach(() => {
    process.env.STRIPE_SECRET_KEY = "sk_test_123";
    process.env.STRIPE_PRICE_PRO = "price_pro_123";
    process.env.STRIPE_PRICE_ENTERPRISE = "price_ent_123";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("creates a subscription checkout session", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id: "cs_test_123",
        url: "https://checkout.stripe.com/c/pay/cs_test_123",
        status: "open",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await createStripeCheckoutSession(
      "pro",
      "https://app.example/success",
      "https://app.example/cancel",
      "demo@example.com",
    );

    expect(result.sessionId).toBe("cs_test_123");
    expect(result.checkoutUrl).toContain("checkout.stripe.com");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "https://api.stripe.com/v1/checkout/sessions",
    );
  });
});
