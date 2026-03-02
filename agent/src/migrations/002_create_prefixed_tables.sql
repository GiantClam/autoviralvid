-- Consolidated Database Schema with autoviralvid_ prefix
-- This script creates new tables mirroring the existing structure.
-- Run this in Supabase SQL Editor.

-- ============================================
-- 1. Core Project Tables
-- ============================================

-- JOBS Table (Core video project metadata)
CREATE TABLE IF NOT EXISTS public.autoviralvid_jobs (
    run_id TEXT PRIMARY KEY,
    slogan TEXT,
    cover_url TEXT,
    video_url TEXT,
    status TEXT DEFAULT 'pending',
    share_slug TEXT UNIQUE,
    user_id TEXT,
    storyboards JSONB DEFAULT '[]',
    total_duration INTEGER,
    styles TEXT,
    image_control TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- VIDEO_TASKS Table (Individual clip generation tasks)
CREATE TABLE IF NOT EXISTS public.autoviralvid_video_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id TEXT NOT NULL, -- Note: Handled by application logic, optional FK to autoviralvid_jobs(run_id)
    clip_idx INTEGER NOT NULL,
    prompt TEXT NOT NULL,
    ref_img TEXT,
    duration INTEGER DEFAULT 10,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'submitted', 'succeeded', 'failed')),
    provider_task_id TEXT,
    video_url TEXT,
    error TEXT,
    retry_count INTEGER DEFAULT 0,
    skill_id UUID, -- Links to autoviralvid_skills.id
    skill_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- PROMPTS_LIBRARY Table (Slogan templates and seeds)
CREATE TABLE IF NOT EXISTS public.autoviralvid_prompts_library (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL UNIQUE,
    prompt TEXT,
    embedding JSONB, -- fallback to JSONB if pgvector extension is not enabled
    cover_url TEXT,
    category TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- CREW_SESSIONS Table (Agent orchestration state)
CREATE TABLE IF NOT EXISTS public.autoviralvid_crew_sessions (
    run_id TEXT PRIMARY KEY,
    status TEXT DEFAULT 'pending',
    result JSONB DEFAULT '{}',
    context JSONB DEFAULT '{}',
    expected_clips INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- 2. Auth & User Tables (Matches Prisma Schema)
-- ============================================

CREATE TABLE IF NOT EXISTS public.autoviralvid_users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE,
    password TEXT,
    "emailVerified" TIMESTAMPTZ,
    image TEXT
);

CREATE TABLE IF NOT EXISTS public.autoviralvid_profiles (
    id TEXT PRIMARY KEY,
    "userId" TEXT UNIQUE REFERENCES public.autoviralvid_users(id) ON DELETE CASCADE,
    is_allowed BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS public.autoviralvid_Account (
    id TEXT PRIMARY KEY,
    "userId" TEXT NOT NULL REFERENCES public.autoviralvid_users(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    provider TEXT NOT NULL,
    "providerAccountId" TEXT NOT NULL,
    refresh_token TEXT,
    access_token TEXT,
    expires_at INTEGER,
    token_type TEXT,
    scope TEXT,
    id_token TEXT,
    session_state TEXT,
    UNIQUE(provider, "providerAccountId")
);

CREATE TABLE IF NOT EXISTS public.autoviralvid_Session (
    id TEXT PRIMARY KEY,
    "sessionToken" TEXT UNIQUE NOT NULL,
    "userId" TEXT NOT NULL REFERENCES public.autoviralvid_users(id) ON DELETE CASCADE,
    expires TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS public.autoviralvid_VerificationToken (
    identifier TEXT NOT NULL,
    token TEXT UNIQUE NOT NULL,
    expires TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (identifier, token)
);

-- ============================================
-- 3. Indexes & Constraints
-- ============================================

CREATE INDEX IF NOT EXISTS idx_autoviralvid_jobs_user_id ON public.autoviralvid_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_autoviralvid_jobs_share_slug ON public.autoviralvid_jobs(share_slug);
CREATE INDEX IF NOT EXISTS idx_autoviralvid_video_tasks_run_id ON public.autoviralvid_video_tasks(run_id);
CREATE INDEX IF NOT EXISTS idx_autoviralvid_video_tasks_status ON public.autoviralvid_video_tasks(status);
CREATE INDEX IF NOT EXISTS idx_autoviralvid_video_tasks_provider_id ON public.autoviralvid_video_tasks(provider_task_id);

-- ============================================
-- 4. Triggers for updated_at
-- ============================================

CREATE OR REPLACE FUNCTION update_autoviralvid_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tr_autoviralvid_jobs_updated_at ON public.autoviralvid_jobs;
CREATE TRIGGER tr_autoviralvid_jobs_updated_at
    BEFORE UPDATE ON public.autoviralvid_jobs
    FOR EACH ROW EXECUTE FUNCTION update_autoviralvid_updated_at_column();

DROP TRIGGER IF EXISTS tr_autoviralvid_video_tasks_updated_at ON public.autoviralvid_video_tasks;
CREATE TRIGGER tr_autoviralvid_video_tasks_updated_at
    BEFORE UPDATE ON public.autoviralvid_video_tasks
    FOR EACH ROW EXECUTE FUNCTION update_autoviralvid_updated_at_column();

DROP TRIGGER IF EXISTS tr_autoviralvid_crew_sessions_updated_at ON public.autoviralvid_crew_sessions;
CREATE TRIGGER tr_autoviralvid_crew_sessions_updated_at
    BEFORE UPDATE ON public.autoviralvid_crew_sessions
    FOR EACH ROW EXECUTE FUNCTION update_autoviralvid_updated_at_column();
