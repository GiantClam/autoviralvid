-- Add `name` column for Auth.js PrismaAdapter compatibility.
-- Safe to run multiple times.
ALTER TABLE "autoviralvid_users"
ADD COLUMN IF NOT EXISTS "name" TEXT;
