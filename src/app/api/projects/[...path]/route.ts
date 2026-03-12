import { NextRequest, NextResponse } from "next/server";
import { SignJWT } from "jose";
import { auth } from "@/lib/auth";
import { getAgentServiceUrl, getAuthSecret } from "@/lib/runtime-env";

type Params = Promise<{ path: string[] }>;

async function buildBackendHeaders(request: NextRequest) {
  const headers: Record<string, string> = {};
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers["Content-Type"] = contentType;
  }

  const session = await auth();
  if (session?.user?.id) {
    const secretKey = new TextEncoder().encode(getAuthSecret());
    const token = await new SignJWT({
      sub: session.user.id,
      email: session.user.email || "",
    })
      .setProtectedHeader({ alg: "HS256" })
      .setIssuedAt()
      .setExpirationTime("5m")
      .sign(secretKey);
    headers["Authorization"] = `Bearer ${token}`;
  }

  return headers;
}

async function forward(
  request: NextRequest,
  context: { params: Params },
  method: string,
) {
  try {
    const { path } = await context.params;
    const backendUrl = getAgentServiceUrl();
    const incomingUrl = new URL(request.url);
    const targetPath = (path || []).map(encodeURIComponent).join("/");
    const targetUrl = new URL(`${backendUrl}/api/v1/${targetPath}`);
    targetUrl.search = incomingUrl.search;

    const headers = await buildBackendHeaders(request);
    const init: RequestInit = {
      method,
      headers,
      cache: "no-store",
    };

    if (method !== "GET" && method !== "HEAD") {
      init.body = await request.text();
    }

    const response = await fetch(targetUrl, init);
    const text = await response.text();

    return new NextResponse(text, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") || "application/json",
      },
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unknown proxy error" },
      { status: 500 },
    );
  }
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
