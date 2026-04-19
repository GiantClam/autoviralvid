import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("@/lib/runtime-env", () => ({
  getAgentServiceUrl: () => "http://agent.local",
}));

describe("internal ppt prompt dispatch route", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
    delete process.env.PPT_PROMPT_DISPATCH_TOKEN;
    delete process.env.PPT_EXPORT_WORKER_TOKEN;
    delete process.env.CRON_SECRET;
    delete process.env.BILLING_RECONCILE_TOKEN;
    delete process.env.PPT_EXPORT_WORKER_BASE_URL;
  });

  it("returns 503 when dispatch token is not configured", async () => {
    const { GET } = await import("./route");
    const request = new NextRequest("http://localhost/api/internal/ppt/prompt-jobs/dispatch");
    const response = await GET(request);
    const payload = await response.json();

    expect(response.status).toBe(503);
    expect(payload.error).toContain("token");
  });

  it("returns 401 when token does not match", async () => {
    process.env.PPT_PROMPT_DISPATCH_TOKEN = "secret";
    const { GET } = await import("./route");
    const request = new NextRequest("http://localhost/api/internal/ppt/prompt-jobs/dispatch");
    const response = await GET(request);
    const payload = await response.json();

    expect(response.status).toBe(401);
    expect(payload.error).toBe("Unauthorized");
  });

  it("forwards authorized dispatch request to worker endpoint", async () => {
    process.env.PPT_PROMPT_DISPATCH_TOKEN = "secret";
    process.env.PPT_EXPORT_WORKER_BASE_URL = "https://worker.example.com";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ success: true, data: { accepted: 1 } }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    const { GET } = await import("./route");
    const request = new NextRequest(
      "http://localhost/api/internal/ppt/prompt-jobs/dispatch?limit=2",
      {
        headers: { authorization: "Bearer secret" },
      },
    );
    const response = await GET(request);
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.success).toBe(true);
    expect(fetch).toHaveBeenCalledWith(
      "https://worker.example.com/api/v1/ppt/internal/prompt-jobs/dispatch",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "x-internal-token": "secret" }),
      }),
    );
  });
});
