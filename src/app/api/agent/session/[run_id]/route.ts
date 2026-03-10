import { NextRequest, NextResponse } from "next/server";
import { getErrorMessage } from "@/lib/errors";
import { getAgentServiceUrl } from "@/lib/runtime-env";

export const GET = async (
    req: NextRequest,
    { params }: { params: Promise<{ run_id: string }> }
) => {
    const { run_id } = await params;

    try {
        const agentUrl = getAgentServiceUrl();
        const res = await fetch(`${agentUrl}/agent/session/${run_id}`, {
            cache: "no-store",
        });

        if (!res.ok) {
            return NextResponse.json({ error: `Backend error: ${res.status}` }, { status: res.status });
        }

        const data = await res.json();
        return NextResponse.json(data);
    } catch (error) {
        return NextResponse.json({ error: getErrorMessage(error) }, { status: 500 });
    }
};
