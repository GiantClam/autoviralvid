-- Diagnostics table for PPT export retries and scoped failure analysis.

create table if not exists autoviralvid_ppt_retry_diagnostics (
  id bigserial primary key,
  deck_id text not null,
  failure_code text,
  failure_detail text,
  retry_scope text not null default 'deck',
  retry_target_ids jsonb not null default '[]'::jsonb,
  attempt integer not null default 1,
  idempotency_key text,
  render_spec_version text default 'v1',
  status text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_ppt_retry_diag_deck_id
  on autoviralvid_ppt_retry_diagnostics (deck_id, created_at desc);

create index if not exists idx_ppt_retry_diag_status
  on autoviralvid_ppt_retry_diagnostics (status, created_at desc);

