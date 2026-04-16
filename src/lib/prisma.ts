import { PrismaClient } from "@prisma/client"

function isPostgresDsn(value: string | undefined): value is string {
    if (!value) return false
    return value.startsWith("postgres://") || value.startsWith("postgresql://")
}

if (!isPostgresDsn(process.env.POSTGRES_PRISMA_URL)) {
    if (isPostgresDsn(process.env.DATABASE_URL)) {
        process.env.POSTGRES_PRISMA_URL = process.env.DATABASE_URL
    } else if (isPostgresDsn(process.env.SUPABASE_URL)) {
        // Backward compatibility: older deployments reused SUPABASE_URL for Prisma DSN.
        process.env.POSTGRES_PRISMA_URL = process.env.SUPABASE_URL
    }
}

const globalForPrisma = global as unknown as { prisma: PrismaClient }

export const prisma =
    globalForPrisma.prisma ||
    new PrismaClient({
        log: ["query"],
    })

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma
