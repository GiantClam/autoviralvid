# PPT Generation Design Quality Simplification Implementation Plan

> Use this plan to execute the work task-by-task with tight verification after each step.

**Goal:** 用“单主干、少分叉、可验收”的方式重构现有 PPT 生成链路，把设计质量提升从“叠加补丁”改为“稳定收敛”。

**Architecture:** 保留现有能力模块（layout solver / quality gate / visual critic / retry policy），但重构编排方式：一次决策、一次渲染、一次评估、有限重试。核心是建立唯一决策源（Design Decision），并让 Python 与 Node 渲染端只消费决策，不再重复启发式选型。

**Tech Stack:** FastAPI (Python), SVG-to-PPTX (Node), pytest, template catalog

---

## Baseline（已基于代码核对）

1. 设计技能已接入主流程，不是“未接入”状态。
- 代码证据：`agent/src/ppt_service.py` 中 `_run_layer1_design_skill_chain`、`_apply_skill_planning_to_render_payload`。

2. 主渲染路径是 MiniMax 导出，不是 `pptx_engine.py`。
- 代码证据：`agent/src/minimax_exporter.py` + `scripts/generate-pptx-minimax.mjs`。
- `agent/src/pptx_engine.py` 主要用于 `template_file_url` 模板填充分支。

3. 主要问题不是“能力不足”，而是“决策重复 + 编排过载”。
- Python 有决策：`agent/src/installed_skill_executor.py` (`_choose_style/_choose_palette/_choose_template_family`)。
- Node 也有决策：`scripts/generate-pptx-minimax.mjs` (`selectStyle/selectPalette/resolveSlideTemplateFamily`)。
- `export_pptx` 在 `agent/src/ppt_service.py` 过长，承担过多职责。

4. 质量与重试模块本身结构可用，但缺少统一收敛策略。
- `agent/src/ppt_layout_solver.py`
- `agent/src/ppt_quality_gate.py`
- `agent/src/ppt_visual_critic.py`
- `agent/src/ppt_retry_orchestrator.py`
- `agent/src/ppt_failure_classifier.py`

### 设计约束现状（Skill 规则盘点）

**现有 Skill 设计规则与 PPTAgent 约束对比：**

| 约束类型 | PPTAgent | slide-making-skill | ppt-orchestra-skill | color-font-skill | 状态 |
|---------|----------|-------------------|-------------------|-----------------|------|
| 三色原则（主/副/强调） | ✅ | ❌ | ❌ | ❌ | **需新增** |
| 字体限制（最多2种） | ✅ | ⚠️ 推荐 | ❌ | ❌ | 需强化 |
| 正文字号≥18pt | ✅ | ❌ | ⚠️ 14-16pt | ❌ | 需强化 |
| 标题字号≥24pt | ✅ | ❌ | ✅ 36-44pt | ❌ | 需强化 |
| 空白比例≥15% | ✅ | ❌ | ⚠️ "留呼吸空间" | ❌ | **需新增** |
| 对齐检查（0.1网格） | ✅ | ❌ | ❌ | ❌ | **需新增** |
| 视觉层级（大小对比） | ✅ | ❌ | ⚠️ 大小对比 | ❌ | 需强化 |
| 配色方案数 | - | ❌ | ❌ | ✅ 18套 | 已具备 |
| 风格配方数 | - | ❌ | ❌ | ✅ 4套 | 已具备 |

**结论：**
1. **不需要从零构建**——配色（18套）和风格配方（4套）已存在于 `color-font-skill` 和 `design-style-skill`
2. **问题在于**：现有 Skill 规则是 **推荐性指南（guideline）**，而非 **强制性约束（constraint）**
3. **策略**：强化现有规则 → 补充缺失规则 → 与 `design_decision_v1` 联动 → 增加自动检查工具

### 补充方案：设计约束强化路径

#### Step 1: 规则分类
- **已实现（ Skill 已具备）**：`color-font-skill`（配色）、`design-style-skill`（风格）
- **需强化为约束**：`slide-making-skill`（字号、层级）→ 需在渲染前检查
- **需新增**：`design-constraint-checker`（三色原则、空白比例、对齐网格）

#### Step 2: 约束执行位置
- **渲染前检查**：在 `Design Decision` 生成后、渲染前执行约束检查
- **渲染后验证**：在 `Quality Gate` 中增加约束违规扣分项
- **重试限制**：约束违规导致的失败不计入重试预算

#### Step 3: Skill 联动方式
```
design_decision_v1 
  → 输出 style_variant/palette_key/layout_grid 
  → color-font-skill.resolve_palette(palette_key) 
  → design-style-skill.apply_style(style_variant)
  → slide-making-skill.apply_constraints()  ← 新增约束执行
  → render
```

---

## Target Architecture（简洁有效版）

### Single Spine
1. `Input Normalize`：统一输入合同，补齐必要字段。
2. `Design Decision`：仅一次选定 deck/slide 级别视觉决策。
3. `Render`：渲染端严格消费决策，不再二次猜测。
4. `Quality Evaluate`：统一评分 + 问题码输出。
5. `Bounded Retry`：仅按问题码执行有限动作梯。

### One Source of Truth
统一新增 `design_decision_v1`（deck-level + slide-level）作为全链路真值来源，至少包含：
- `style_variant`
- `palette_key`
- `template_family`
- `layout_grid`
- `render_path`
- `quality_profile`
- `route_mode`
- `decision_trace`（来源与置信度）

### 减法原则
1. 不新增新的“智能层”，优先删除重复决策。
2. 不在重试阶段改变全局风格，只允许局部动作（文本压缩、布局降密、补视觉锚点）。
3. 不再让 Node 端重做风格/配色/模板选择。

---

## Task 1: 建立统一决策对象（Design Decision）

**Files:**
- Create: `agent/src/ppt_design_decision.py`
- Modify: `agent/src/ppt_service.py`
- Modify: `agent/src/installed_skill_executor.py`
- Test: `agent/tests/test_ppt_service_skill_path.py`
- Test: `agent/tests/test_ppt_pipeline_contract_inputs.py`

**Step 1: 定义决策数据结构和合并规则**
- 在 `ppt_design_decision.py` 定义 `DesignDecisionV1` 与 `SlideDecision`。
- 明确优先级：`user explicit > template/profile policy > skill output > deterministic fallback`。

**Step 2: 在 `ppt_service.py` 统一生成 decision**
- 把 `_run_layer1_design_skill_chain`、`_apply_skill_planning_to_render_payload` 的结果收敛到 `design_decision_v1`。
- 仅在这里允许“选风格/配色/模板”。

**Step 3: 收敛 installed skill executor 的职责**
- 保留其“补全与规范化”能力。
- 移除/封存与 Node 重叠的二次主决策逻辑（保留 fallback 但默认不生效）。

**Step 4: 运行测试**
Run: `pytest agent/tests/test_ppt_service_skill_path.py agent/tests/test_ppt_pipeline_contract_inputs.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add agent/src/ppt_design_decision.py agent/src/ppt_service.py agent/src/installed_skill_executor.py agent/tests/test_ppt_service_skill_path.py agent/tests/test_ppt_pipeline_contract_inputs.py
git commit -m "refactor(ppt): introduce unified design decision v1"
```

---

## Task 2: 渲染端只消费决策，不再重复选型

**Files:**
- Modify: `agent/src/minimax_exporter.py`
- Modify: `scripts/generate-pptx-minimax.mjs`
- Modify: `scripts/minimax-style-heuristics.mjs`
- Test: `agent/tests/test_exporter_official_mode.py`
- Test: `agent/tests/test_ppt_template_routing.py`

**Step 1: exporter 强制透传 design_decision_v1**
- 在 payload 中写入固定字段，确保 Node 端可直接渲染。

**Step 2: Node 端切换为“decision-first”**
- `generate-pptx-minimax.mjs` 优先读取 `design_decision_v1`。
- 只有字段缺失时才允许最小 fallback，并记录 warning。

**Step 3: 下调 style heuristic 权重**
- `minimax-style-heuristics.mjs` 保留工具函数，但不再作为默认主路径。

**Step 4: 运行测试**
Run: `pytest agent/tests/test_exporter_official_mode.py agent/tests/test_ppt_template_routing.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add agent/src/minimax_exporter.py scripts/generate-pptx-minimax.mjs scripts/minimax-style-heuristics.mjs agent/tests/test_exporter_official_mode.py agent/tests/test_ppt_template_routing.py
git commit -m "refactor(ppt): make minimax renderer decision-driven"
```

---

## Task 3: 重试机制减法（有限动作梯）

**Files:**
- Modify: `agent/src/ppt_service.py`
- Modify: `agent/src/ppt_retry_orchestrator.py`
- Modify: `agent/src/ppt_visual_critic.py`
- Test: `agent/tests/test_ppt_export_retry_flow.py`
- Test: `agent/tests/test_ppt_retry_orchestrator.py`
- Test: `agent/tests/test_ppt_critic_repair_loop.py`

**Step 1: 固化 retry policy**
- 仅允许 `deck -> slide -> block` 三层 scope。
- 默认最大重试次数收敛为 `2`（`refine` 模式可升到 `3`）。

**Step 2: 固化动作梯，不再自由拼 patch**
- 允许动作：`compress_text`、`downgrade_layout_density`、`add_visual_anchor`、`switch_render_path_once`。
- 禁止在 retry 中修改 `style_variant/palette_key/template_family`。

**Step 3: 统一失败码到动作映射**
- 失败码来源只认 `quality_gate + visual_critic + failure_classifier`。
- 去掉重复或冲突映射。

**Step 4: 运行测试**
Run: `pytest agent/tests/test_ppt_export_retry_flow.py agent/tests/test_ppt_retry_orchestrator.py agent/tests/test_ppt_critic_repair_loop.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add agent/src/ppt_service.py agent/src/ppt_retry_orchestrator.py agent/src/ppt_visual_critic.py agent/tests/test_ppt_export_retry_flow.py agent/tests/test_ppt_retry_orchestrator.py agent/tests/test_ppt_critic_repair_loop.py
git commit -m "refactor(ppt): simplify retry ladder and patch policy"
```

---

## Task 4: 拆分 `export_pptx` 超长流程

**Files:**
- Create: `agent/src/ppt_export_pipeline.py`
- Modify: `agent/src/ppt_service.py`
- Test: `agent/tests/test_ppt_pipeline.py`
- Test: `agent/tests/test_ppt_e2e.py`

**Step 1: 提取 pipeline stages**
- 从 `export_pptx` 中抽出：`prepare_input`、`build_decision`、`render`、`evaluate`、`retry`、`persist`。

**Step 2: `ppt_service.py` 仅保留入口编排**
- 参数校验、鉴权、日志入口保留在 service。
- 具体执行转交 `ppt_export_pipeline.py`。

**Step 3: 增加阶段级可观测字段**
- 每个 stage 输出：`duration_ms`、`decision_source`、`retry_count`、`quality_score`。

**Step 4: 运行测试**
Run: `pytest agent/tests/test_ppt_pipeline.py agent/tests/test_ppt_e2e.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add agent/src/ppt_export_pipeline.py agent/src/ppt_service.py agent/tests/test_ppt_pipeline.py agent/tests/test_ppt_e2e.py
git commit -m "refactor(ppt): extract export pipeline stages from service"
```

---

## Task 5: 质量验收基线与回归门禁

**Files:**
- Modify: `agent/src/ppt_quality_gate.py`
- Modify: `agent/src/ppt_route_strategy.py`
- Modify: `scripts/minimax/templates/template-catalog.json`
- Test: `agent/tests/test_ppt_quality_gate.py`
- Test: `agent/tests/test_ppt_route_strategy.py`
- Test: `agent/tests/test_ppt_policy_catalog.py`

**Step 1: 定义统一验收指标**
- `weighted_quality_score`
- `retry_count`
- `layout_homogeneous incidence`
- `render_success_rate`

**Step 2: 将阈值集中到 catalog/profile**
- 用 `template-catalog.json` 承载阈值，减少散落常量。

**Step 3: route mode 与质量阈值联动**
- `fast/standard/refine` 仅控制成本与重试预算，不改核心决策逻辑。

**Step 4: 运行测试**
Run: `pytest agent/tests/test_ppt_quality_gate.py agent/tests/test_ppt_route_strategy.py agent/tests/test_ppt_policy_catalog.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add agent/src/ppt_quality_gate.py agent/src/ppt_route_strategy.py scripts/minimax/templates/template-catalog.json agent/tests/test_ppt_quality_gate.py agent/tests/test_ppt_route_strategy.py agent/tests/test_ppt_policy_catalog.py
git commit -m "chore(ppt): centralize quality thresholds and acceptance gate"
```

---

## 验收标准（完成定义）

1. 质量表现
- `weighted_quality_score`：P50 >= 78，P90 >= 72。
- 视觉门禁失败率（首轮）较当前下降 >= 30%。

2. 稳定性
- 平均重试轮次 <= 1.3。
- `layout_homogeneous` 失败码占比 <= 5%。

3. 性能
- 标准模式端到端耗时不增加超过 15%。

4. 可维护性
- `export_pptx` 主函数行数下降 >= 40%。
- 关键决策字段仅在 `design_decision_v1` 写入一次。

---

## 非目标（本轮不做）

1. 不引入新的外部模型供应商。
2. 不新增大规模“智能美化”子代理链。
3. 不改动模板资产体系（仅调整选择与阈值策略）。

---

## 执行顺序建议

1. Task 1（先统一决策源）
2. Task 2（再清理渲染端重复决策）
3. Task 3（收敛重试策略）
4. Task 4（拆分 service 过载函数）
5. Task 5（最后固化验收门禁）

这样可以最小风险地从“拼凑方案”过渡到“可解释、可回归、可迭代”的主干架构。

---

Plan complete and saved to `docs/plans/2026-04-01-ppt-design-quality-optimization.md`. Two execution options:

1. Current Session - Execute one task at a time in this session, review between tasks, and keep iteration tight
2. Separate Session - Open a fresh Codex session dedicated to implementing the plan with checkpoints

Which approach?
