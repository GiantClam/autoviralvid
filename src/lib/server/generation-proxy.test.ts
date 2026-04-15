import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const authMock = vi.fn();
const checkQuotaMock = vi.fn();
const consumeQuotaMock = vi.fn();
const refundQuotaMock = vi.fn();

vi.mock("@/lib/auth", () => ({
  auth: authMock,
}));

vi.mock("@/lib/quota", () => ({
  checkQuota: checkQuotaMock,
  consumeQuota: consumeQuotaMock,
  refundQuota: refundQuotaMock,
}));

vi.mock("@/lib/runtime-env", () => ({
  getAgentServiceUrl: () => "http://agent.local",
  getAuthSecret: () => "test-secret",
}));

describe("generation proxy billing flow", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
    process.env.GENERATION_BILLING_ENABLED = "true";
    authMock.mockResolvedValue({
      user: { id: "user-1", email: "u1@example.com" },
    });
    checkQuotaMock.mockResolvedValue({
      allowed: false,
      remaining: 0,
      total: 3,
      used: 3,
      plan: "free",
    });
    consumeQuotaMock.mockResolvedValue(true);
    refundQuotaMock.mockResolvedValue(undefined);
  });

  it("charges once for matched generation endpoint and does not refund on success", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ success: true }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const { forwardApiV1Request } = await import("./generation-proxy");
    const request = new NextRequest("http://localhost/api/projects/projects/p1/storyboard", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
    });
    const response = await forwardApiV1Request(request, {
      method: "POST",
      path: ["projects", "p1", "storyboard"],
      upstreamPrefixSegments: [],
      billingPrefixSegments: [],
    });

    expect(response.status).toBe(200);
    expect(consumeQuotaMock).toHaveBeenCalledWith("user-1", 1);
    expect(refundQuotaMock).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("refunds charged units when backend returns failure", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ success: false }), {
          status: 500,
          headers: { "content-type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const { forwardApiV1Request } = await import("./generation-proxy");
    const request = new NextRequest("http://localhost/api/projects/projects/p1/images", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
    });
    const response = await forwardApiV1Request(request, {
      method: "POST",
      path: ["projects", "p1", "images"],
      upstreamPrefixSegments: [],
      billingPrefixSegments: [],
    });

    expect(response.status).toBe(500);
    expect(consumeQuotaMock).toHaveBeenCalledWith("user-1", 1);
    expect(refundQuotaMock).toHaveBeenCalledWith("user-1", 1);
  });

  it("does not charge for non-chargeable endpoint", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ status: "ok" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const { forwardApiV1Request } = await import("./generation-proxy");
    const request = new NextRequest("http://localhost/api/projects/projects/p1/status", {
      method: "GET",
    });
    const response = await forwardApiV1Request(request, {
      method: "GET",
      path: ["projects", "p1", "status"],
      upstreamPrefixSegments: [],
      billingPrefixSegments: [],
    });

    expect(response.status).toBe(200);
    expect(consumeQuotaMock).not.toHaveBeenCalled();
    expect(refundQuotaMock).not.toHaveBeenCalled();
  });

  it("returns 401 when charging endpoint is requested without authenticated user", async () => {
    authMock.mockResolvedValueOnce(null);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const { forwardApiV1Request } = await import("./generation-proxy");
    const request = new NextRequest("http://localhost/api/ppt/generate-from-prompt", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ prompt: "demo" }),
    });
    const response = await forwardApiV1Request(request, {
      method: "POST",
      path: ["generate-from-prompt"],
      upstreamPrefixSegments: ["ppt"],
      billingPrefixSegments: ["ppt"],
    });
    const payload = await response.json();

    expect(response.status).toBe(401);
    expect(payload.error).toContain("Authentication required");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns 402 on quota exceeded and skips backend call", async () => {
    consumeQuotaMock.mockResolvedValueOnce(false);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const { forwardApiV1Request } = await import("./generation-proxy");
    const request = new NextRequest("http://localhost/api/projects/v7/export", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
    });
    const response = await forwardApiV1Request(request, {
      method: "POST",
      path: ["v7", "export"],
      upstreamPrefixSegments: [],
      billingPrefixSegments: [],
    });
    const payload = await response.json();

    expect(response.status).toBe(402);
    expect(payload.error).toBe("quota_exceeded");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
