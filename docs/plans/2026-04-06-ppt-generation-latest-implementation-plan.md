# PPT 生成最新实现方案（2026-04-07）

## 1. 当前主流程（DrawingML-first）

主入口：`POST /api/v1/ppt/pipeline` 与 `POST /api/v1/ppt/export`

执行阶段：
1. research
2. outline_plan
3. presentation_plan
4. quality_gate
5. export

导出约束：
- `render_channel` 仅允许 `local`
- `retry_scope` 统一为 `deck`
- 不再使用 `slide/block/png_fallback` 分支
- 不再依赖 Node 导出脚本（`scripts/minimax/*.mjs`）

## 2. 与 ppt-master 的复用与对齐

已复用：
- `vendor/minimax-skills/skills/ppt-master/scripts/svg_finalize/*`（通过 `ppt_svg_finalizer.py` 统一调用）
- 模板目录同步机制（`scripts/sync_ppt_master_templates.py`）
- DrawingML 导出主链（`minimax_exporter.py`）

已对齐策略：
- 统一重试策略（`RetryPolicy`）
- 导出失败显式分类（`MiniMaxExportError` + `FailureClassification`）
- 质量门后仍保持 deck 级重试与诊断落库

## 3. 本轮完成项（稳定性/可维护性）

- 增加 `ppt_export_service.py`（导出薄门面）
- 增加 `ppt_quality_service.py`（质量评估薄门面）
- 增加 `ppt_retry_service.py`（重试薄门面）
- 增加 `ppt_svg_finalizer.py`（SVG 后处理单入口）
- `v7_routes.py` 强制 `retry_scope=deck`、`render_channel=local`
- `ppt_retry_orchestrator.py` 补充 `compute_render_path_downgrade` 兼容接口（no-op）
- `ppt_service.py` 统一禁用 partial scope 重试，保持 deck 级一致性

## 4. 已补回归测试

- `test_ppt_retry_scope_consistency.py`
- `test_ppt_export_retry_flow.py`
- `test_v7_export_submit_status.py`
- `test_ppt_svg_finalizer.py`
- `test_ppt_retry_orchestrator.py`

## 5. 当前已知待清理项（不影响主流程）

1. 历史文档仍有 Node/SVG-to-PPTX 叙述（主要在旧 `docs/plans/*`）。
2. 历史文案中仍有少量旧导出描述，建议持续按 svg-only 口径清理。
3. `ppt_service.py` 仍偏大，建议下一步继续拆分（策略/导出/质量/观测）。

## 6. 验证基线

建议最小回归命令：

```bash
pytest -q \
  agent/tests/test_ppt_retry_scope_consistency.py \
  agent/tests/test_ppt_export_retry_flow.py \
  agent/tests/test_v7_export_submit_status.py \
  agent/tests/test_ppt_svg_finalizer.py \
  agent/tests/test_ppt_retry_orchestrator.py
```

该基线覆盖了：重试范围一致性、导出主链、v7 路由约束、SVG 后处理、重试编排兼容。
