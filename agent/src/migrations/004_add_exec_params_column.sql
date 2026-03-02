-- Migration 004: Add exec_params column to autoviralvid_video_tasks
-- Required for queue-based RunningHub submission (tasks store their
-- full execution parameters so the Worker can submit them).

ALTER TABLE autoviralvid_video_tasks
  ADD COLUMN IF NOT EXISTS exec_params JSONB DEFAULT '{}'::jsonb;

-- Also ensure skill columns exist (they may already from earlier migrations)
ALTER TABLE autoviralvid_video_tasks
  ADD COLUMN IF NOT EXISTS skill_name TEXT;

ALTER TABLE autoviralvid_video_tasks
  ADD COLUMN IF NOT EXISTS skill_id UUID;
