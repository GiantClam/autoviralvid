import { NextRequest, NextResponse } from 'next/server';
import { getAgentServiceUrl } from '@/lib/runtime-env';

type Params = Promise<{ run_id: string }>;

export async function GET(
    request: NextRequest,
    context: { params: Params }
) {
    try {
        const { run_id } = await context.params;
        if (!run_id) {
            return NextResponse.json({ error: 'Missing run_id parameter' }, { status: 400 });
        }

        const backendUrl = getAgentServiceUrl();
        const url = `${backendUrl}/jobs/${encodeURIComponent(run_id)}/tasks`;

        const response = await fetch(url);
        if (!response.ok) {
            const errorText = await response.text();
            return NextResponse.json(
                { error: `Backend request failed: ${response.statusText}`, detail: errorText },
                { status: response.status }
            );
        }

        const data = await response.json();
        return NextResponse.json(data);
    } catch (error) {
        return NextResponse.json(
            { error: error instanceof Error ? error.message : 'Unknown error' },
            { status: 500 }
        );
    }
}
