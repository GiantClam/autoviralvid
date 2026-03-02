import { NextRequest, NextResponse } from 'next/server';

type Params = Promise<{ run_id: string }>;

export async function POST(
    request: NextRequest,
    context: { params: Params }
) {
    try {
        const { run_id } = await context.params;

        if (!run_id) {
            return NextResponse.json(
                { error: 'Missing run_id parameter' },
                { status: 400 }
            );
        }

        // Forward the request to the backend agent service
        const backendUrl = process.env.NEXT_PUBLIC_AGENT_URL || process.env.AGENT_URL || 'http://localhost:8123';
        const url = `${backendUrl}/jobs/${encodeURIComponent(run_id)}/retry`;

        console.log(`[Frontend API] Forwarding retry request to: ${url}`);

        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error(`[Frontend API] Backend retry failed: ${response.status} - ${errorText}`);
            return NextResponse.json(
                { error: `Backend retry failed: ${response.statusText}` },
                { status: response.status }
            );
        }

        const data = await response.json();
        console.log(`[Frontend API] Retry successful:`, data);

        return NextResponse.json(data);
    } catch (error) {
        console.error('[Frontend API] Retry error:', error);
        return NextResponse.json(
            { error: error instanceof Error ? error.message : 'Unknown error occurred' },
            { status: 500 }
        );
    }
}

