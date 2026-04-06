# PPT Official Rollout Runbook

## Scope
- This runbook is for PPT generation only.
- Video rendering is deferred to a separate Phase 2 project.

## Feature Flags
- `PPT_GENERATOR_MODE=official|legacy`
- `PPT_OFFICIAL_ROLLOUT_PERCENT=0..100`
- `PPT_ENABLE_LEGACY_FALLBACK=true|false`
- `PPT_VISUAL_PRIORITY=true|false`
- `PPT_VISUAL_PRESET=tech_cinematic|executive_brief|premium_light|energetic`
- `PPT_VISUAL_DENSITY=sparse|balanced|dense`
- `PPT_RETRY_ENABLED=true|false`
- `PPT_PARTIAL_RETRY_ENABLED=true|false`

## Rollout Steps
1. Staging dry-run: set `PPT_GENERATOR_MODE=official`, `PPT_OFFICIAL_ROLLOUT_PERCENT=100`, `PPT_ENABLE_LEGACY_FALLBACK=true`.
2. Run at least 30 exports with the same prompt set under both modes (`official` vs `legacy`).
3. Compare success rate and quality-gate pass rate. Official must be no worse than legacy.
4. Production rollout by percentage: `10 -> 30 -> 50 -> 100`.
5. Keep `PPT_ENABLE_LEGACY_FALLBACK=true` during rollout window, then disable after stability.

## Quality Gates
- `ppt_export_success_rate`
- `ppt_quality_gate_pass_rate`
- `ppt_retry_attempts_avg`
- `ppt_placeholder_pollution_rate`

## LingChuang Baseline
- Run:
  - `python scripts/e2e_lingchuang_ppt.py`
  - `python scripts/e2e_lingchuang_ppt_quality.py --require-keywords "灵创智能,AI营销,数字人" --min-slides 8`
- Persist baseline report at `test_reports/ppt/lingchuang_quality_baseline.json`.

## Local Render Quality Checklist
- Verify stage-4 payload keeps visual anchors (`chart/image/kpi/workflow`) on content slides.
- Verify stage-5 `official_input` content slides always keep non-empty `blocks`.
- Verify template diversity for mixed content decks is >= 2.
- Run:
  - `(deprecated) Node export entry has been removed.`
  - `Use Python export path via agent/src/minimax_exporter.py (DrawingML native).`
  - `node scripts/tests/validate-render-metrics.mjs test_outputs/d1ef-fixed.render.json test_outputs/a6cf-fixed.render.json`

## Rollback
1. Set `PPT_GENERATOR_MODE=legacy`.
2. Set `PPT_OFFICIAL_ROLLOUT_PERCENT=0`.
3. Keep service online and verify one complete PPT export.
4. Confirm failure metrics recover within 5 minutes.
