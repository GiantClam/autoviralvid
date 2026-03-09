import { NextRequest, NextResponse } from "next/server";
import { SignJWT } from "jose";
import { auth } from "@/lib/auth";
import { getAgentServiceUrl, getAuthSecret } from "@/lib/runtime-env";

export const GET = async (req: NextRequest) => {
    const { searchParams } = new URL(req.url);
    const limit = searchParams.get("limit") || "40";

    try {
        const agentUrl = getAgentServiceUrl();
        const secretKey = new TextEncoder().encode(getAuthSecret());
        // Build auth header for backend
        const headers: Record<string, string> = {};
        const session = await auth();
        if (session?.user?.id) {
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

        const res = await fetch(`${agentUrl}/agent/sessions?limit=${limit}`, {
            cache: "no-store",
            headers,
        });

        if (!res.ok) {
            return NextResponse.json({ error: `Backend error: ${res.status}` }, { status: res.status });
        }

        const data = await res.json();
        return NextResponse.json(data);
    } catch (error: unknown) {
        const message = error instanceof Error ? error.message : String(error);
        return NextResponse.json({ error: message }, { status: 500 });
    }
};
