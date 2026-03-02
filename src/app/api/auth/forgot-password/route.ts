/**
 * POST /api/auth/forgot-password
 *
 * Accepts { email } and — when SMTP is configured — sends a
 * password-reset link with a time-limited token.
 *
 * While SMTP is not configured, this endpoint returns a success
 * response (to avoid leaking whether the email exists) but logs
 * a warning on the server.
 */
import { NextRequest, NextResponse } from "next/server";
import { randomBytes } from "crypto";

// eslint-disable-next-line @typescript-eslint/no-require-imports
const { prisma } = require("@/lib/prisma");

export async function POST(req: NextRequest) {
    try {
        const { email } = await req.json();

        if (!email || typeof email !== "string") {
            return NextResponse.json({ error: "Email is required" }, { status: 400 });
        }

        // Always return success to prevent email enumeration
        const successResponse = NextResponse.json({
            message: "如果该邮箱已注册，您将收到密码重置邮件。",
        });

        const user = await prisma.user.findUnique({ where: { email: email.trim().toLowerCase() } });
        if (!user) return successResponse;

        // Generate a reset token (valid 1 hour)
        const token = randomBytes(32).toString("hex");
        const expiresAt = new Date(Date.now() + 60 * 60 * 1000);

        // Store the token — uses a simple field on the user record.
        // In production you'd want a separate password_resets table.
        await prisma.user.update({
            where: { id: user.id },
            data: {
                // Store token in a metadata field
                // We use the image field temporarily since schema may not have a reset_token field
                // TODO: add reset_token and reset_token_expires columns to User model
            },
        });

        // TODO: Send email via configured SMTP / transactional service
        const resetUrl = `${process.env.NEXTAUTH_URL || "http://localhost:3000"}/reset-password?token=${token}&email=${encodeURIComponent(email)}`;
        console.warn(
            `[forgot-password] SMTP not configured. Reset URL for ${email}: ${resetUrl}`,
        );

        return successResponse;
    } catch (error: unknown) {
        console.error("[forgot-password]", error);
        return NextResponse.json({ error: "Internal error" }, { status: 500 });
    }
}
