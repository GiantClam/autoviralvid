import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest, NextResponse } from "next/server";

const forwardApiV1RequestMock = vi.fn();

vi.mock("@/lib/server/generation-proxy", () => ({
  forwardApiV1Request: forwardApiV1RequestMock,
}));

describe("ppt proxy route", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    forwardApiV1RequestMock.mockResolvedValue(
      NextResponse.json({ ok: true }, { status: 200 }),
    );
  });

  it("forwards POST with ppt upstream/billing prefixes", async () => {
    const { POST } = await import("./route");
    const request = new NextRequest("http://localhost/api/ppt/generate-from-prompt", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ prompt: "hello" }),
    });

    const response = await POST(request, {
      params: Promise.resolve({ path: ["generate-from-prompt"] }),
    });

    expect(response.status).toBe(200);
    expect(forwardApiV1RequestMock).toHaveBeenCalledWith(request, {
      method: "POST",
      path: ["generate-from-prompt"],
      upstreamPrefixSegments: ["ppt"],
      billingPrefixSegments: ["ppt"],
    });
  });

  it("forwards GET under ppt prefix", async () => {
    const { GET } = await import("./route");
    const request = new NextRequest("http://localhost/api/ppt/jobs/abc", {
      method: "GET",
    });

    await GET(request, {
      params: Promise.resolve({ path: ["jobs", "abc"] }),
    });

    expect(forwardApiV1RequestMock).toHaveBeenCalledWith(request, {
      method: "GET",
      path: ["jobs", "abc"],
      upstreamPrefixSegments: ["ppt"],
      billingPrefixSegments: ["ppt"],
    });
  });
});
