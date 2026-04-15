import { Prisma } from "@prisma/client";
import { prisma } from "@/lib/prisma";
import { createHash } from "crypto";

function isMissingTableError(error: unknown): boolean {
  if (
    error instanceof Prisma.PrismaClientKnownRequestError &&
    (error.code === "P2021" || error.code === "P2022")
  ) {
    return true;
  }
  return false;
}

export function sha256Hex(input: string): string {
  return createHash("sha256").update(input).digest("hex");
}

export async function beginWebhookEvent(
  provider: "paypal" | "stripe",
  eventId: string,
  eventType: string,
  payloadRaw: string,
) {
  if (!eventId) {
    return { duplicate: false as const, event: null };
  }

  const payloadHash = sha256Hex(payloadRaw);
  try {
    const event = await prisma.paymentWebhookEvent.create({
      data: {
        provider,
        eventId,
        eventType,
        payloadHash,
        status: "processing",
      },
    });
    return { duplicate: false as const, event };
  } catch (error) {
    if (
      error instanceof Prisma.PrismaClientKnownRequestError &&
      error.code === "P2002"
    ) {
      return { duplicate: true as const, event: null };
    }
    if (isMissingTableError(error)) {
      // If table isn't migrated yet, keep webhook flow working without idempotency persistence.
      return { duplicate: false as const, event: null };
    }
    throw error;
  }
}

export async function finishWebhookEvent(
  provider: "paypal" | "stripe",
  eventId: string,
  status: "processed" | "failed",
) {
  if (!eventId) return;
  try {
    await prisma.paymentWebhookEvent.update({
      where: {
        provider_eventId: {
          provider,
          eventId,
        },
      },
      data: {
        status,
        processedAt: new Date(),
      },
    });
  } catch (error) {
    if (isMissingTableError(error)) return;
    if (
      error instanceof Prisma.PrismaClientKnownRequestError &&
      error.code === "P2025"
    ) {
      return;
    }
    throw error;
  }
}

