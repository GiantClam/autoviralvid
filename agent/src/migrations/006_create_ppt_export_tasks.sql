-- Persistent status store for V7 PPT export submit/status flow.
CREATE TABLE IF NOT EXISTS public.autoviralvid_ppt_export_tasks (
    task_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    mode TEXT NOT NULL DEFAULT 'local_background',
    runtime_role TEXT,
    user_id TEXT,
    request_meta JSONB DEFAULT '{}'::jsonb,
    result JSONB,
    error TEXT,
    failure JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_autoviralvid_ppt_export_tasks_status
    ON public.autoviralvid_ppt_export_tasks (status);

CREATE INDEX IF NOT EXISTS idx_autoviralvid_ppt_export_tasks_created_at
    ON public.autoviralvid_ppt_export_tasks (created_at DESC);

CREATE OR REPLACE FUNCTION update_autoviralvid_ppt_export_tasks_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tr_autoviralvid_ppt_export_tasks_updated_at ON public.autoviralvid_ppt_export_tasks;
CREATE TRIGGER tr_autoviralvid_ppt_export_tasks_updated_at
    BEFORE UPDATE ON public.autoviralvid_ppt_export_tasks
    FOR EACH ROW EXECUTE FUNCTION update_autoviralvid_ppt_export_tasks_updated_at();
