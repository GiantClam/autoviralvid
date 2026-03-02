-- Migration 003: Add project-related columns to autoviralvid_jobs
-- These columns support the form-driven workflow and digital human pipeline.

-- Project metadata columns
ALTER TABLE public.autoviralvid_jobs ADD COLUMN IF NOT EXISTS template_id TEXT;
ALTER TABLE public.autoviralvid_jobs ADD COLUMN IF NOT EXISTS theme TEXT;
ALTER TABLE public.autoviralvid_jobs ADD COLUMN IF NOT EXISTS style TEXT;
ALTER TABLE public.autoviralvid_jobs ADD COLUMN IF NOT EXISTS duration INTEGER DEFAULT 30;
ALTER TABLE public.autoviralvid_jobs ADD COLUMN IF NOT EXISTS orientation TEXT DEFAULT '竖屏';
ALTER TABLE public.autoviralvid_jobs ADD COLUMN IF NOT EXISTS product_image_url TEXT;
ALTER TABLE public.autoviralvid_jobs ADD COLUMN IF NOT EXISTS video_type TEXT;
ALTER TABLE public.autoviralvid_jobs ADD COLUMN IF NOT EXISTS aspect_ratio TEXT DEFAULT '9:16';

-- Pipeline resolution columns
ALTER TABLE public.autoviralvid_jobs ADD COLUMN IF NOT EXISTS pipeline_hint TEXT;
ALTER TABLE public.autoviralvid_jobs ADD COLUMN IF NOT EXISTS pipeline_name TEXT;
ALTER TABLE public.autoviralvid_jobs ADD COLUMN IF NOT EXISTS t2i_skill TEXT;
ALTER TABLE public.autoviralvid_jobs ADD COLUMN IF NOT EXISTS i2v_skill TEXT;
ALTER TABLE public.autoviralvid_jobs ADD COLUMN IF NOT EXISTS narrative_key TEXT;
ALTER TABLE public.autoviralvid_jobs ADD COLUMN IF NOT EXISTS narrative_structure JSONB;

-- Digital human / extra params (JSONB for flexibility)
-- Stores: audio_url, voice_mode, voice_text, motion_prompt, etc.
ALTER TABLE public.autoviralvid_jobs ADD COLUMN IF NOT EXISTS extra_params JSONB;

-- Final render output
ALTER TABLE public.autoviralvid_jobs ADD COLUMN IF NOT EXISTS final_video_url TEXT;
