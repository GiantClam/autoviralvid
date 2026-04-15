import { describe, expect, it } from "vitest";

describe("billing plans route", () => {
  it("returns ordered plan catalog with provider availability", async () => {
    const { GET } = await import("./route");
    const response = await GET();
    const payload = (await response.json()) as {
      plans?: Array<{ key: string; providers?: Record<string, boolean> }>;
    };

    expect(response.status).toBe(200);
    expect(payload.plans?.length).toBeGreaterThan(0);
    expect(payload.plans?.[0]?.key).toBe("free");
    expect(typeof payload.plans?.[0]?.providers?.paypal).toBe("boolean");
    expect(typeof payload.plans?.[0]?.providers?.stripe).toBe("boolean");
  });
});
