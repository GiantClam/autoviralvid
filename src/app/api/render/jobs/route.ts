import { NextRequest, NextResponse } from "next/server";
import { buildRenderJobRequest, summarizeRenderJob, type RenderJobRequest } from "@/lib/render";
import type { VideoProject } from "@/lib/types";

type IncomingPayload = Partial<RenderJobRequest> & {
  project?: Partial<VideoProject> & { name?: string };
};

function hasComposition(payload: IncomingPayload): payload is RenderJobRequest {
  return Boolean(
    payload &&
      payload.composition &&
      Array.isArray(payload.composition.layers) &&
      Array.isArray(payload.composition.audioTracks) &&
      payload.project &&
      payload.project.name,
  );
}

function hasRawProject(payload: IncomingPayload): payload is { project: VideoProject; engine?: RenderJobRequest["engine"] } {
  return Boolean(
    payload?.project &&
      Array.isArray(payload.project.tracks) &&
      typeof payload.project.width === "number" &&
      typeof payload.project.height === "number" &&
      typeof payload.project.duration === "number" &&
      Boolean(payload.project.name),
  );
}

function createDryRunResponse(jobRequest: RenderJobRequest) {
  return {
    status: "accepted",
    mode: "dry_run",
    job_id: `dryrun_${crypto.randomUUID()}`,
    summary: summarizeRenderJob(jobRequest),
    message:
      "REMOTION_RENDERER_URL is not configured. Request accepted in dry-run mode. Configure renderer URL to submit actual render jobs.",
    created_at: new Date().toISOString(),
  };
}

async function forwardToRemoteRenderer(
  jobRequest: RenderJobRequest,
  rendererBaseUrl: string,
) {
  const base = rendererBaseUrl.trim().replace(/\/+$/, "");
  const target = `${base}/render/jobs`;
  const response = await fetch(target, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(jobRequest),
  });

  if (!response.ok) {
    const text = await response.text();
    return NextResponse.json(
      {
        error: `Remote renderer failed with status ${response.status}`,
        detail: text,
      },
      { status: response.status },
    );
  }

  const data = await response.json().catch(() => ({}));
  return NextResponse.json({
    status: "accepted",
    mode: "remote",
    job_id: data?.job_id || data?.id || crypto.randomUUID(),
    summary: summarizeRenderJob(jobRequest),
    remote_response: data,
    created_at: new Date().toISOString(),
  });
}

export async function POST(req: NextRequest) {
  try {
    const payload = (await req.json()) as IncomingPayload;

    let jobRequest: RenderJobRequest;
    if (hasComposition(payload)) {
      jobRequest = payload;
    } else if (hasRawProject(payload)) {
      jobRequest = buildRenderJobRequest(payload.project, {
        engine: payload.engine || "remotion",
        runId: payload.project.runId,
        threadId: payload.project.threadId,
      });
    } else {
      return NextResponse.json(
        {
          error:
            "Invalid render payload. Provide either a full RenderJobRequest (with composition) or a raw VideoProject (with tracks).",
        },
        { status: 400 },
      );
    }

    const remoteRenderer = process.env.REMOTION_RENDERER_URL?.trim();
    if (!remoteRenderer) {
      return NextResponse.json(createDryRunResponse(jobRequest));
    }

    return await forwardToRemoteRenderer(jobRequest, remoteRenderer);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Unknown render job error",
      },
      { status: 500 },
    );
  }
}
