/**
 * POST /api/auth/api-token
 *
 * Issues a short-lived JWT (1 hour) for the authenticated user.
 * The frontend caches this token and sends it as a Bearer token
 * to the Python backend, which verifies it with the same AUTH_SECRET.
 */
import { NextResponse } from "next/server";
import { SignJWT } from "jose";
import { auth } from "@/lib/auth";
import { getAuthSecret } from "@/lib/runtime-env";

export async function POST() {
    try {
        const secretKey = new TextEncoder().encode(getAuthSecret());
        const session = await auth();

        if (!session?.user?.id) {
            return NextResponse.json(
                { error: "Unauthorized" },
                { status: 401 },
            );
        }

        const token = await new SignJWT({
            sub: session.user.id,
            email: session.user.email || "",
        })
            .setProtectedHeader({ alg: "HS256" })
            .setIssuedAt()
            .setExpirationTime("1h")
            .sign(secretKey);

        return NextResponse.json({ token, expires_in: 3600 });
    } catch (error: unknown) {
        console.error("[api-token] Error:", error);
        return NextResponse.json(
            { error: "Internal server error" },
            { status: 500 },
        );
    }
}
