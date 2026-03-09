import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";
import { PrismaAdapter } from "@auth/prisma-adapter";
import bcrypt from "bcryptjs";
import { getAuthSecret } from "@/lib/runtime-env";

/**
 * NextAuth v5 with lazy initialization.
 *
 * Uses the request-time callback pattern so that Prisma is only
 * imported when an actual auth request arrives, not at build time.
 */
export const { handlers, auth, signIn, signOut } = NextAuth(() => {
    // Lazy-require prisma inside the callback so it's never
    // evaluated during `next build` page-data collection.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { prisma } = require("./prisma");

    return {
        adapter: PrismaAdapter(prisma),
        providers: [
            // ── Email/Password credentials ──
            Credentials({
                name: "Email",
                credentials: {
                    email: { label: "Email", type: "email" },
                    password: { label: "Password", type: "password" },
                },
                async authorize(credentials) {
                    const email = credentials?.email as string | undefined;
                    const password = credentials?.password as string | undefined;
                    if (!email || !password) return null;

                    const user = await prisma.user.findUnique({
                        where: { email },
                        include: { profile: true },
                    });

                    if (!user || !user.password) return null;

                    const valid = await bcrypt.compare(password, user.password);
                    if (!valid) return null;

                    return {
                        id: user.id,
                        email: user.email,
                        image: user.image,
                    };
                },
            }),
            // ── Google OAuth (only enabled when env vars are set) ──
            ...(process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET
                ? [
                      Google({
                          clientId: process.env.GOOGLE_CLIENT_ID,
                          clientSecret: process.env.GOOGLE_CLIENT_SECRET,
                          allowDangerousEmailAccountLinking: true,
                      }),
                  ]
                : []),
        ],
        session: {
            strategy: "jwt" as const,
            maxAge: 30 * 24 * 60 * 60,
        },
        callbacks: {
            async jwt({ token, user }: { token: any; user: any }) {
                if (user) {
                    token.id = user.id;
                }
                return token;
            },
            async session({ session, token }: { session: any; token: any }) {
                if (session.user && token.id) {
                    session.user.id = token.id as string;
                }
                return session;
            },
        },
        pages: {
            signIn: "/",
        },
        secret: getAuthSecret(),
    };
});
