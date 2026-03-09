import { NextRequest, NextResponse } from "next/server";
import { getAgentServiceUrl } from "@/lib/runtime-env";

export const POST = async (req: NextRequest) => {
    const body = await req.json();

    try {
        const agentUrl = getAgentServiceUrl();
        const res = await fetch(`${agentUrl}/upload/presign`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });

        if (!res.ok) {
            return NextResponse.json({ error: `Backend error: ${res.status}` }, { status: res.status });
        }

        const data = await res.json();
        return NextResponse.json(data);
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
};
