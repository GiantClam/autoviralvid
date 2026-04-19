import { NextRequest, NextResponse } from "next/server";
import { forwardApiV1Request } from "@/lib/server/generation-proxy";

type Params = Promise<{ path: string[] }>;

async function forward(
  request: NextRequest,
  context: { params: Params },
  method: string,
) {
  const { path } = await context.params;
  if ((path?.[0] || "").toLowerCase() === "v7") {
    return NextResponse.json(
      { error: "deprecated_endpoint", detail: "Use /api/ppt/generate-from-prompt instead." },
      { status: 410 },
    );
  }
  return forwardApiV1Request(request, {
    method,
    path: path || [],
    upstreamPrefixSegments: [],
    billingPrefixSegments: [],
  });
}

export async function GET(request: NextRequest, context: { params: Params }) {
  return forward(request, context, "GET");
}

export async function POST(request: NextRequest, context: { params: Params }) {
  return forward(request, context, "POST");
}

export async function PUT(request: NextRequest, context: { params: Params }) {
  return forward(request, context, "PUT");
}

export async function DELETE(request: NextRequest, context: { params: Params }) {
  return forward(request, context, "DELETE");
}
