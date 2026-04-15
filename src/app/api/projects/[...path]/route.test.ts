import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest, NextResponse } from "next/server";

const forwardApiV1RequestMock = vi.fn();

vi.mock("@/lib/server/generation-proxy", () => ({
  forwardApiV1Request: forwardApiV1RequestMock,
}));

describe("projects proxy route", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    forwardApiV1RequestMock.mockResolvedValue(
      NextResponse.json({ ok: true }, { status: 200 }),
    );
  });

  it("forwards POST with unchanged catch-all path and empty prefixes", async () => {
    const { POST } = await import("./route");
    const request = new NextRequest("http://localhost/api/projects/projects/p1/storyboard", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
    });

    const response = await POST(request, {
      params: Promise.resolve({ path: ["projects", "p1", "storyboard"] }),
    });

    expect(response.status).toBe(200);
    expect(forwardApiV1RequestMock).toHaveBeenCalledTimes(1);
    expect(forwardApiV1RequestMock).toHaveBeenCalledWith(request, {
      method: "POST",
      path: ["projects", "p1", "storyboard"],
      upstreamPrefixSegments: [],
      billingPrefixSegments: [],
    });
  });

  it("forwards GET requests through the same proxy function", async () => {
    const { GET } = await import("./route");
    const request = new NextRequest("http://localhost/api/projects/projects/p1/status", {
      method: "GET",
    });

    await GET(request, {
      params: Promise.resolve({ path: ["projects", "p1", "status"] }),
    });

    expect(forwardApiV1RequestMock).toHaveBeenCalledWith(request, {
      method: "GET",
      path: ["projects", "p1", "status"],
      upstreamPrefixSegments: [],
      billingPrefixSegments: [],
    });
  });
});
