import { PrismaClient } from "@prisma/client"

if (!process.env.SUPABASE_URL && process.env.DATABASE_URL) {
    process.env.SUPABASE_URL = process.env.DATABASE_URL
}

const globalForPrisma = global as unknown as { prisma: PrismaClient }

export const prisma =
    globalForPrisma.prisma ||
    new PrismaClient({
        log: ["query"],
    })

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma
