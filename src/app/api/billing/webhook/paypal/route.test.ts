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
    paymentSubscription: { findUnique: vi.fn() },
    subscription: { findUnique: vi.fn(), upsert: vi.fn() },
    user: { findUnique: vi.fn() },
    profile: { update: vi.fn() },
  },
}));

vi.mock("@/lib/quota", () => ({
  resetMonthlyQuota: vi.fn(),
}));

describe("paypal billing webhook route", () => {
  it("returns duplicate ack when webhook event already exists", async () => {
    beginWebhookEventMock.mockResolvedValue({
      duplicate: true,
      event: null,
    });

    const { POST } = await import("./route");

    const request = new NextRequest("http://localhost/api/billing/webhook/paypal", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        id: "WH-1",
        event_type: "BILLING.SUBSCRIPTION.ACTIVATED",
        resource: { id: "I-SUB-1" },
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

