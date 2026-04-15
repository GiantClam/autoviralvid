import { describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const beginWebhookEventMock = vi.fn();
const finishWebhookEventMock = vi.fn();

vi.mock("@/lib/billing/webhook-events", () => ({
  beginWebhookEvent: beginWebhookEventMock,
  finishWebhookEvent: finishWebhookEventMock,
  sha256Hex: (input: string) => `hash-${input.length}`,
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    paymentCustomer: { findUnique: vi.fn(), upsert: vi.fn() },
    paymentSubscription: { findUnique: vi.fn(), upsert: vi.fn() },
    user: { findUnique: vi.fn() },
    subscription: { upsert: vi.fn() },
  },
}));

vi.mock("@/lib/quota", () => ({
  resetMonthlyQuota: vi.fn(),
}));

describe("stripe billing webhook route", () => {
  it("returns duplicate ack when webhook event already exists", async () => {
    delete process.env.STRIPE_WEBHOOK_SECRET;
    beginWebhookEventMock.mockResolvedValue({
      duplicate: true,
      event: null,
    });

    const { POST } = await import("./route");

    const request = new NextRequest("http://localhost/api/billing/webhook/stripe", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        id: "evt_1",
        type: "invoice.payment_succeeded",
        data: {
          object: {},
        },
      }),
    });

    const response = await POST(request);
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload).toEqual({ received: true, duplicate: true });
    expect(beginWebhookEventMock).toHaveBeenCalledTimes(1);
    expect(finishWebhookEventMock).not.toHaveBeenCalled();
  });
});

