-- Skills-Based Architecture Database Schema
-- Run this migration in Supabase SQL Editor

-- ============================================
-- Skills Registry Table
-- ============================================
CREATE TABLE IF NOT EXISTS public.autoviralvid_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('t2i', 'i2v', 't2v', 'video_edit', 'audio', 'avatar')),
    provider TEXT NOT NULL CHECK (provider IN ('runninghub', 'tokenengine', 'zhenzhen', 'liblib', 'mock')),

    -- Workflow Configuration
    workflow_id TEXT,                           -- Provider-specific workflow ID
    version TEXT DEFAULT '1.0.0',

    -- Node Mappings (for ComfyUI-based providers)
    node_mappings JSONB DEFAULT '{}',           -- {"prompt": {"nodeId": "41", "fieldName": "prompt"}, "image": {...}}

    -- Capabilities
    capabilities JSONB DEFAULT '{
        "max_duration": 10,
        "min_duration": 5,
        "orientations": ["landscape", "portrait"],
        "supports_image_ref": true,
        "supports_audio": false,
        "output_formats": ["mp4"],
        "resolution_options": ["1080p", "720p"]
    }',

    -- Input/Output Schemas (JSON Schema format)
    input_schema JSONB DEFAULT '{}',
    output_schema JSONB DEFAULT '{}',

    -- Quality & Performance Metrics (updated from execution history)
    quality_score DECIMAL(3,2) DEFAULT 0.70 CHECK (quality_score >= 0 AND quality_score <= 1),
    reliability_score DECIMAL(3,2) DEFAULT 0.80 CHECK (reliability_score >= 0 AND reliability_score <= 1),
    avg_latency_ms INTEGER DEFAULT 60000,
    cost_per_execution DECIMAL(10,4) DEFAULT 0.00,

    -- Selection Configuration
    priority INTEGER DEFAULT 100,               -- Lower = higher priority in selection
    is_enabled BOOLEAN DEFAULT true,
    requires_upload BOOLEAN DEFAULT false,      -- Does this skill require image upload before use?

    -- API Configuration
    api_base_url TEXT,

    -- Metadata
    description TEXT,
    tags TEXT[] DEFAULT '{}',

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for skills table
CREATE INDEX IF NOT EXISTS idx_autoviralvid_skills_category ON public.autoviralvid_skills(category);
CREATE INDEX IF NOT EXISTS idx_autoviralvid_skills_provider ON public.autoviralvid_skills(provider);
CREATE INDEX IF NOT EXISTS idx_autoviralvid_skills_enabled_priority ON public.autoviralvid_skills(is_enabled, priority);
CREATE INDEX IF NOT EXISTS idx_autoviralvid_skills_name ON public.autoviralvid_skills(name);

-- ============================================
-- Skill Executions Table (Execution History)
-- ============================================
CREATE TABLE IF NOT EXISTS public.autoviralvid_skill_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id UUID REFERENCES public.autoviralvid_skills(id) ON DELETE SET NULL,
    skill_name TEXT,                            -- Denormalized for queries when skill deleted
    run_id TEXT NOT NULL,
    clip_idx INTEGER,                           -- Which clip in the video
    task_id TEXT,                               -- Provider-specific task ID

    -- Execution Context
    input_params JSONB DEFAULT '{}',            -- Sanitized input (no full prompts for privacy)
    output_result JSONB DEFAULT '{}',

    -- Status & Timing
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'submitted', 'processing', 'succeeded', 'failed', 'timeout', 'cancelled')),
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,

    -- Quality Feedback
    user_rating INTEGER CHECK (user_rating IS NULL OR (user_rating >= 1 AND user_rating <= 5)),
    auto_quality_score DECIMAL(3,2),            -- Computed from output analysis

    -- Error Handling
    error_message TEXT,
    error_code TEXT,
    retry_count INTEGER DEFAULT 0,

    -- Output
    output_url TEXT,

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for skill_executions table
CREATE INDEX IF NOT EXISTS idx_autoviralvid_skill_executions_skill_id ON public.autoviralvid_skill_executions(skill_id);
CREATE INDEX IF NOT EXISTS idx_autoviralvid_skill_executions_run_id ON public.autoviralvid_skill_executions(run_id);
CREATE INDEX IF NOT EXISTS idx_autoviralvid_skill_executions_status ON public.autoviralvid_skill_executions(status);
CREATE INDEX IF NOT EXISTS idx_autoviralvid_skill_executions_created ON public.autoviralvid_skill_executions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_autoviralvid_skill_executions_skill_name ON public.autoviralvid_skill_executions(skill_name);

-- ============================================
-- User Skill Preferences Table
-- ============================================
CREATE TABLE IF NOT EXISTS public.autoviralvid_user_skill_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL UNIQUE,

    -- Preference Weights (must sum to ~1.0)
    quality_weight DECIMAL(3,2) DEFAULT 0.40 CHECK (quality_weight >= 0 AND quality_weight <= 1),
    speed_weight DECIMAL(3,2) DEFAULT 0.30 CHECK (speed_weight >= 0 AND speed_weight <= 1),
    cost_weight DECIMAL(3,2) DEFAULT 0.30 CHECK (cost_weight >= 0 AND cost_weight <= 1),

    -- Category-specific overrides
    preferred_skills JSONB DEFAULT '{}',        -- {"i2v": ["runninghub_sora2"], "t2i": ["runninghub_qwen"]}
    blocked_skills TEXT[] DEFAULT '{}',

    -- Budget constraints
    max_cost_per_video DECIMAL(10,2),
    max_latency_seconds INTEGER,

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for user preferences
CREATE INDEX IF NOT EXISTS idx_autoviralvid_user_skill_preferences_user_id ON public.autoviralvid_user_skill_preferences(user_id);

-- ============================================
-- Skill Discovery Cache (for marketplace workflows)
-- ============================================
CREATE TABLE IF NOT EXISTS public.autoviralvid_skill_discovery_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider TEXT NOT NULL,
    external_workflow_id TEXT NOT NULL,
    workflow_name TEXT,
    workflow_metadata JSONB DEFAULT '{}',
    discovered_at TIMESTAMPTZ DEFAULT NOW(),
    last_validated_at TIMESTAMPTZ,
    is_importable BOOLEAN DEFAULT true,

    UNIQUE(provider, external_workflow_id)
);

-- ============================================
-- Triggers for updated_at
-- ============================================
CREATE OR REPLACE FUNCTION update_autoviralvid_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to skills table
DROP TRIGGER IF EXISTS update_autoviralvid_skills_updated_at ON public.autoviralvid_skills;
CREATE TRIGGER update_autoviralvid_skills_updated_at
    BEFORE UPDATE ON public.autoviralvid_skills
    FOR EACH ROW
    EXECUTE FUNCTION update_autoviralvid_updated_at_column();

-- Apply trigger to user_skill_preferences table
DROP TRIGGER IF EXISTS update_autoviralvid_user_skill_preferences_updated_at ON public.autoviralvid_user_skill_preferences;
CREATE TRIGGER update_autoviralvid_user_skill_preferences_updated_at
    BEFORE UPDATE ON public.autoviralvid_user_skill_preferences
    FOR EACH ROW
    EXECUTE FUNCTION update_autoviralvid_updated_at_column();

-- ============================================
-- Add skill_id column to video_tasks if not exists
-- ============================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = 'autoviralvid_video_tasks'
        AND column_name = 'skill_id'
    ) THEN
        ALTER TABLE public.autoviralvid_video_tasks ADD COLUMN skill_id UUID REFERENCES public.autoviralvid_skills(id) ON DELETE SET NULL;
        ALTER TABLE public.autoviralvid_video_tasks ADD COLUMN skill_name TEXT;
    END IF;
END $$;

-- ============================================
-- Seed Initial Skills Data
-- ============================================
INSERT INTO public.autoviralvid_skills (name, display_name, category, provider, workflow_id, node_mappings, capabilities, priority, requires_upload, description, tags)
VALUES
(
    'runninghub_sora2_i2v',
    'RunningHub Sora2 Video',
    'i2v',
    'runninghub',
    '1985261217524629506',
    '{"prompt": {"nodeId": "41", "fieldName": "prompt"}, "image": {"nodeId": "40", "fieldName": "image"}}',
    '{"max_duration": 10, "min_duration": 5, "orientations": ["landscape", "portrait"], "supports_image_ref": true, "supports_audio": true, "output_formats": ["mp4"]}',
    10,
    true,
    'High-quality video generation using Sora2 model via RunningHub ComfyUI workflow',
    ARRAY['video', 'sora2', 'high-quality', 'i2v']
),
(
    'tokenengine_sora2',
    'TokenEngine Sora2',
    'i2v',
    'tokenengine',
    NULL,
    '{}',
    '{"max_duration": 10, "min_duration": 5, "orientations": ["landscape", "portrait"], "supports_image_ref": true, "supports_audio": false, "output_formats": ["mp4"]}',
    20,
    false,
    'Sora2 video generation via TokenEngine API (aotiai.com)',
    ARRAY['video', 'sora2', 'fast', 'i2v']
),
(
    'zhenzhen_sora2',
    'ZhenZhen Sora2',
    'i2v',
    'zhenzhen',
    NULL,
    '{}',
    '{"max_duration": 10, "min_duration": 5, "orientations": ["landscape", "portrait"], "supports_image_ref": true, "supports_audio": false, "output_formats": ["mp4"]}',
    30,
    false,
    'Sora2 video generation via ZhenZhen API (t8star.cn)',
    ARRAY['video', 'sora2', 'budget', 'i2v']
),
(
    'runninghub_qwen_t2i',
    'RunningHub Qwen Scene Image',
    't2i',
    'runninghub',
    NULL,  -- Will be set from RUNNINGHUB_IMAGE_WORKFLOW_ID env var
    '{"prompt": {"nodeId": "3", "fieldName": "text"}, "image": {"nodeId": "21", "fieldName": "image"}}',
    '{"supports_image_ref": true, "output_formats": ["png", "jpg"]}',
    10,
    true,
    'Scene image generation using Qwen model with product reference via RunningHub',
    ARRAY['image', 'qwen', 'scene-generation', 't2i']
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    workflow_id = EXCLUDED.workflow_id,
    node_mappings = EXCLUDED.node_mappings,
    capabilities = EXCLUDED.capabilities,
    priority = EXCLUDED.priority,
    requires_upload = EXCLUDED.requires_upload,
    description = EXCLUDED.description,
    tags = EXCLUDED.tags,
    updated_at = NOW();

-- ============================================
-- Grant permissions (adjust as needed)
-- ============================================
-- For service role access
GRANT ALL ON public.autoviralvid_skills TO service_role;
GRANT ALL ON public.autoviralvid_skill_executions TO service_role;
GRANT ALL ON public.autoviralvid_user_skill_preferences TO service_role;
GRANT ALL ON public.autoviralvid_skill_discovery_cache TO service_role;

-- For anon access (read-only on skills)
GRANT SELECT ON public.autoviralvid_skills TO anon;
