/**
 * POST /api/auth/reset-password
 *
 * Accepts { token, email, password } and resets the user's password.
 *
 * NOTE: Full token verification requires a dedicated password_resets
 * table.  The current implementation is a placeholder that validates
 * the email exists and updates the password directly.
 * TODO: integrate with the token stored in forgot-password route.
 */
import { NextRequest, NextResponse } from "next/server";
import bcrypt from "bcryptjs";

// eslint-disable-next-line @typescript-eslint/no-require-imports
const { prisma } = require("@/lib/prisma");

export async function POST(req: NextRequest) {
    try {
        const { token, email, password } = await req.json();

        if (!token || !email || !password) {
            return NextResponse.json(
                { error: "Missing required fields" },
                { status: 400 },
            );
        }

        if (typeof password !== "string" || password.length < 6) {
            return NextResponse.json(
                { error: "Password must be at least 6 characters" },
                { status: 400 },
            );
        }

        // TODO: Verify the reset token from a password_resets table
        // For now, we accept any valid-looking token format
        if (typeof token !== "string" || token.length < 10) {
            return NextResponse.json({ error: "Invalid token" }, { status: 400 });
        }

        const user = await prisma.user.findUnique({
            where: { email: email.trim().toLowerCase() },
        });

        if (!user) {
            return NextResponse.json({ error: "Invalid token" }, { status: 400 });
        }

        const hashedPassword = await bcrypt.hash(password, 10);

        await prisma.user.update({
            where: { id: user.id },
            data: { password: hashedPassword },
        });

        return NextResponse.json({ message: "Password reset successfully" });
    } catch (error: unknown) {
        console.error("[reset-password]", error);
        return NextResponse.json({ error: "Internal error" }, { status: 500 });
    }
}
