/**
 * GET /api/quota — return the current user's quota usage.
 */
import { NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { getBillingSnapshot } from "@/lib/billing/account";

export async function GET() {
    try {
        const session = await auth();
        if (!session?.user?.id) {
            return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
        }

        const snapshot = await getBillingSnapshot(session.user.id);
        const quota = snapshot.quota;
        return NextResponse.json(quota);
    } catch (error: unknown) {
        console.error("[api/quota] Error:", error);
        return NextResponse.json(
            { error: "Failed to fetch quota" },
            { status: 500 },
        );
    }
}
