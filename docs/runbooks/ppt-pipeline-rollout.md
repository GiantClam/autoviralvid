# PPT Pipeline Rollout Runbook

## Feature Flags
- `PPT_RETRY_ENABLED`
- `PPT_PARTIAL_RETRY_ENABLED`
- `PPT_RETRY_MAX_ATTEMPTS`
- `PPT_VIDEO_BASE_MODE` (recommended: `ppt_image_slideshow`)

## Rollout Steps
1. Enable on staging with `PPT_RETRY_ENABLED=true` and `PPT_PARTIAL_RETRY_ENABLED=true`.
2. Verify diagnostics writes into `autoviralvid_ppt_retry_diagnostics`.
3. Validate success and latency metrics for at least 100 exports.
4. Roll production traffic by cohorts: 10% -> 50% -> 100%.

## Guardrails
- `ppt_export_success_rate >= 95%`
- `ppt_retry_attempts_avg <= 3`
- No regression in `video_mode=ppt_image_slideshow` selection when slide images exist.
- No increase in placeholder/garbled incidents after quality gate.

## Rollback
1. Set `PPT_RETRY_ENABLED=false`.
2. Set `PPT_PARTIAL_RETRY_ENABLED=false`.
3. Keep export endpoint online (fallback to single-attempt export path).
4. Confirm new failures stop within 5 minutes via diagnostics table.

