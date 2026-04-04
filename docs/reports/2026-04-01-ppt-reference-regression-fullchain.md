# PPT Full-Chain Regression Report (2026-04-01)

## Scope

对 `docs/plans/2026-04-01-ppt-design-quality-optimization-v1.md` 的主张执行一次完整回归验证，覆盖两条主路径：

- `fidelity`（标准参考重建）
- `zero_create`（严格去参考信息生成）

## Commands

```bash
python scripts/run_reference_regression_once.py \
  --reference-ppt C:\Users\liula\Downloads\ppt2\ppt2\1.pptx \
  --pages 1-22 \
  --phase phase5r20260401 \
  --creation-mode fidelity \
  --quality-bar normal \
  --focus-cluster geometry \
  --single-cluster on \
  --visual-critic-repair on
```

```bash
python scripts/run_reference_regression_once.py \
  --reference-ppt C:\Users\liula\Downloads\ppt2\ppt2\1.pptx \
  --pages 1-22 \
  --phase phase5z12 \
  --creation-mode zero_create \
  --quality-bar normal \
  --focus-cluster geometry \
  --single-cluster on \
  --visual-critic-repair on
```

## Results

| Path | Baseline | Latest | Delta | Verdict |
|---|---:|---:|---:|---|
| fidelity | 98.0 (`phase5`) | 98.0 (`phase5r20260401`) | 0.0 | 保持稳定（VERIFIED） |
| zero_create | 55.1275 (`phase5z11`) | 56.1218 (`phase5z13`) | +0.9943 | 小幅提升（NEEDS_IMPROVEMENT） |

## Key Observations

1. fidelity 路径稳定在高分：
- 首次 API 尝试约 `64.3`，经 critic repair + local 重试后恢复到 `98.0`，问题数归零。

2. zero_create 路径仍是主要短板，但已出现提分信号：
- 本轮出现一次 `pipeline timeout`（约 570s）后进入 local 重建。
- critic repair 新增“目标页模板白名单”后，分数由 `55.1275 -> 56.1218`。
- `issue_buckets` 仍集中在 `visual` 与 `other`，说明还需继续压结构错配。
- 说明当前修复链路从“稳定复现”开始进入“可控提分”阶段。

3. 白名单策略落地验证：
- 在 `round_summary.phase5z13.json` 的 `visual_critic.patch.slide_mutations` 中，目标页已携带：
  - `template_family_whitelist`
  - `template_family`
  - `template_lock=true`
- Node 模板解析已接入白名单约束，避免回退到非白名单模板（含 `dashboard_dark`）。

4. 反向实验（未采纳）：
- `phase5z15`：尝试在 geometry 回合抑制 media 联动，得分 `55.87`（低于 `phase5z13`）。
- `phase5z16`：尝试将 critic 目标页扩大到 10 页，得分 `55.17`，且 schema-invalid 触发增加。
- 结论：保持 `phase5z13` 的策略组合作为当前最佳实践。

5. local-first 可行性验证（已采纳）：
- `phase5z18` 在 `PPT_ZERO_CREATE_DEFAULT_MODE=local` + `--mode auto` 下执行。
- 结果：`score=56.1218`（与 `phase5z13` 同级），`issue_count=30`，无 API timeout。
- 耗时明显降低（从分钟级超时重试降到约 30 秒级），适合作为本地开发默认策略。

## Artifacts

- `output/regression/round_summary.phase5r20260401.json`
- `output/regression/issues.phase5r20260401.json`
- `output/regression/generated.phase5r20260401.pptx`
- `output/regression/round_summary.phase5z12.json`
- `output/regression/issues.phase5z12.json`
- `output/regression/generated.phase5z12.pptx`
- `output/regression/round_summary.phase5z13.json`
- `output/regression/issues.phase5z13.json`
- `output/regression/generated.phase5z13.pptx`
- `output/regression/round_summary.phase5z15.json`
- `output/regression/round_summary.phase5z16.json`
- `output/regression/round_summary.phase5z18.json`

## Conclusion

本次全链路回归结论是：

- 方案主干在 fidelity 场景已达到并维持高质量门禁。
- zero_create 仍需专项提分（核心是视觉相似度与结构映射能力），但白名单约束已带来可观测正向增益，链路稳定性满足持续迭代条件。
