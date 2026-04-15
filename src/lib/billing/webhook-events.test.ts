import { beforeEach, describe, expect, it, vi } from "vitest";
import { Prisma } from "@prisma/client";

const { createMock, updateMock } = vi.hoisted(() => ({
  createMock: vi.fn(),
  updateMock: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    paymentWebhookEvent: {
      create: createMock,
      update: updateMock,
    },
  },
}));

import { beginWebhookEvent, finishWebhookEvent, sha256Hex } from "./webhook-events";

function prismaKnownError(code: string) {
  return new Prisma.PrismaClientKnownRequestError("test", {
    code,
    clientVersion: "test",
  });
}

describe("billing webhook idempotency helpers", () => {
  beforeEach(() => {
    createMock.mockReset();
    updateMock.mockReset();
  });

  it("creates a processing event when event id is new", async () => {
    createMock.mockResolvedValue({
      id: "evt_row_1",
      provider: "paypal",
      eventId: "EVT-1",
    });

    const result = await beginWebhookEvent(
      "paypal",
      "EVT-1",
      "BILLING.SUBSCRIPTION.ACTIVATED",
      "{\"ok\":true}",
    );

    expect(result.duplicate).toBe(false);
    expect(result.event?.id).toBe("evt_row_1");
    expect(createMock).toHaveBeenCalledTimes(1);
  });

  it("returns duplicate=true when unique key conflict happens", async () => {
    createMock.mockRejectedValue(prismaKnownError("P2002"));

    const result = await beginWebhookEvent("stripe", "evt_123", "invoice.payment_succeeded", "{}");

    expect(result.duplicate).toBe(true);
    expect(result.event).toBeNull();
  });

  it("keeps flow alive when webhook table is missing", async () => {
    createMock.mockRejectedValue(prismaKnownError("P2021"));

    const result = await beginWebhookEvent("paypal", "evt_missing_table", "event.test", "{}");

    expect(result.duplicate).toBe(false);
    expect(result.event).toBeNull();
  });

  it("marks event as processed", async () => {
    updateMock.mockResolvedValue({ id: "evt_row_1" });

    await finishWebhookEvent("paypal", "evt_1", "processed");

    expect(updateMock).toHaveBeenCalledTimes(1);
    expect(updateMock.mock.calls[0]?.[0]?.where?.provider_eventId).toEqual({
      provider: "paypal",
      eventId: "evt_1",
    });
  });

  it("ignores not-found and missing-table errors on finish", async () => {
    updateMock.mockRejectedValueOnce(prismaKnownError("P2025"));
    await expect(finishWebhookEvent("stripe", "evt_nf", "processed")).resolves.toBeUndefined();

    updateMock.mockRejectedValueOnce(prismaKnownError("P2022"));
    await expect(finishWebhookEvent("stripe", "evt_missing", "failed")).resolves.toBeUndefined();
  });

  it("hash helper is deterministic", () => {
    const a = sha256Hex("payload");
    const b = sha256Hex("payload");
    expect(a).toBe(b);
    expect(a).toMatch(/^[a-f0-9]{64}$/);
  });
});
