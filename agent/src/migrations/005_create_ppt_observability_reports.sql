-- PPT observability report sink for production monitoring dashboards.
CREATE TABLE IF NOT EXISTS autoviralvid_ppt_observability_reports (
    id BIGSERIAL PRIMARY KEY,
    deck_id TEXT,
    status TEXT NOT NULL,
    failure_code TEXT,
    failure_detail TEXT,
    route_mode TEXT,
    quality_profile TEXT,
    attempts INTEGER,
    quality_score DOUBLE PRECISION,
    quality_score_threshold DOUBLE PRECISION,
    alert_count INTEGER,
    alerts JSONB,
    issue_codes JSONB,
    export_channel TEXT,
    generator_mode TEXT,
    diagnostics JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_autoviralvid_ppt_observability_created_at
    ON autoviralvid_ppt_observability_reports (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_autoviralvid_ppt_observability_status
    ON autoviralvid_ppt_observability_reports (status);

CREATE INDEX IF NOT EXISTS idx_autoviralvid_ppt_observability_route_mode
    ON autoviralvid_ppt_observability_reports (route_mode);
