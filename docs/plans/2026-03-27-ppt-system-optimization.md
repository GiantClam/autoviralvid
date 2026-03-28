# PPT System Gap-Driven Optimization Implementation Plan

> Use this plan to execute the work task-by-task with tight verification after each step.

**Goal:** 在不重复造轮子的前提下，基于现有 MiniMax 官方化链路补齐关键能力缺口：专家内容工作流、Bento Grid 版式、数据可视化增强、质量门禁升级。

**Architecture:** 采用 Gap-Driven Strangler 策略。保留已上线的官方生成主链路（official mode、局部重试、诊断落库、PPT-first 视频），仅新增当前缺失能力并通过特性开关渐进启用。执行方式遵循 TDD：先写失败测试，再最小实现，再回归验证。

**Tech Stack:** FastAPI (Python), Node.js (PptxGenJS), Pydantic v2, pytest, Vitest

---

## Baseline (Already Implemented, Do Not Rebuild)

1. 官方化主链路已存在：`generator_mode=official`、`official_orchestrator`、`official_skill_adapter`。  
2. 局部重试与诊断已存在：`retry_scope(deck|slide|block)`、`target_slide_ids`、`target_block_ids`、重试分类与落库。  
3. 视觉系统已具备基础能力：18 色板、4 风格、视觉 preset、布局多样性启发式（Node 侧 45% + 禁止相邻重复）。  
4. 视频链路已支持 PPT 栅格图优先。  

本计划仅覆盖“未完成缺口”，避免重复改造上述能力。

### Task 1: 收紧 Python 侧布局多样性门禁（与 Node 侧对齐）

**Files:**
- Modify: `agent/src/ppt_quality_gate.py`
- Test: `agent/tests/test_ppt_quality_gate.py`

**Step 1: Write the failing tests**
```python
def test_layout_diversity_default_ratio_and_adjacent_rules():
    from src.ppt_quality_gate import validate_layout_diversity
    spec = {"slides": [{"slide_type": "content"} for _ in range(6)]}
    result = validate_layout_diversity(spec)
    assert result.ok is False
    assert any(i.code in {"layout_homogeneous", "layout_adjacent_repeat"} for i in result.issues)
```

```python
def test_layout_diversity_requires_variety_for_long_deck():
    from src.ppt_quality_gate import validate_layout_diversity
    spec = {"slides": [{"slide_type": "content"} for _ in range(10)]}
    result = validate_layout_diversity(spec, min_layout_variety=4)
    assert result.ok is False
    assert any(i.code == "layout_variety_low" for i in result.issues)
```

**Step 2: Run test to verify it fails**
Run: `cd agent; pytest tests/test_ppt_quality_gate.py -q`  
Expected: FAIL (新规则尚未实现)。

**Step 3: Write minimal implementation**
- 将 `validate_layout_diversity()` 默认参数改为：
  - `max_type_ratio=0.45`
  - `max_adjacent_repeat=1`
  - 新增 `min_layout_variety=4`
- 新增规则：
  - `total >= 10` 时，布局类型数不足触发 `layout_variety_low`
  - 首末页结构约束（首 `cover|hero_1`，末 `summary|hero_1`）作为可配置检查，默认关闭。

**Step 4: Run test to verify it passes**
Run: `cd agent; pytest tests/test_ppt_quality_gate.py -q`  
Expected: PASS。

**Step 5: Commit**
```bash
git add agent/src/ppt_quality_gate.py agent/tests/test_ppt_quality_gate.py
git commit -m "feat: tighten layout diversity quality gate defaults and add variety checks"
```

### Task 2: 新增“需求调研 + 便利贴大纲 + 策划稿”中间态契约

**Files:**
- Create: `agent/src/schemas/ppt_research.py`
- Create: `agent/src/schemas/ppt_outline.py`
- Create: `agent/src/schemas/ppt_plan.py`
- Modify: `agent/src/schemas/ppt.py`
- Modify: `agent/src/ppt_service.py`
- Modify: `agent/src/ppt_routes.py`
- Test: `agent/tests/test_ppt_research_flow.py`

**Step 1: Write the failing tests**
```python
def test_research_outline_plan_flow_contract():
    # 1) research -> 2) outline sticky notes -> 3) plan
    # assert required fields exist and can round-trip through API layer
    ...
```

```python
def test_plan_blocks_reject_placeholder_content():
    # assert ContentBlock.content contains no placeholder tokens
    ...
```

**Step 2: Run test to verify it fails**
Run: `cd agent; pytest tests/test_ppt_research_flow.py -q`  
Expected: FAIL。

**Step 3: Write minimal implementation**
- 增加三个 schema：
  - `ResearchContext`
  - `OutlinePlan/StickyNote`
  - `PresentationPlan/SlidePlan/ContentBlock`
- 在 `ppt_service.py` 增加三段式方法：
  - `generate_research_context()`
  - `generate_outline_plan()`
  - `generate_presentation_plan()`
- 在 `ppt_routes.py` 新增对应 API 路由，并保持 `export_pptx` 兼容旧入口。

**Step 4: Run test to verify it passes**
Run: `cd agent; pytest tests/test_ppt_research_flow.py -q`  
Expected: PASS。

**Step 5: Commit**
```bash
git add agent/src/schemas/ppt_research.py agent/src/schemas/ppt_outline.py agent/src/schemas/ppt_plan.py agent/src/schemas/ppt.py agent/src/ppt_service.py agent/src/ppt_routes.py agent/tests/test_ppt_research_flow.py
git commit -m "feat: add research-outline-plan intermediate workflow contracts"
```

### Task 3: 引入 Bento Grid 渲染模块（新增，不重写现有官方链路）

**Files:**
- Create: `scripts/minimax/bento-grid.mjs`
- Create: `scripts/minimax/card-renderers.mjs`
- Create: `scripts/minimax/chart-factory.mjs`
- Modify: `scripts/generate-pptx-minimax.mjs`
- Test: `scripts/tests/bento-grid.harness.test.mjs`
- Test: `scripts/tests/card-renderers.harness.test.mjs`

**Step 1: Write the failing tests**
```javascript
import { validateGrid } from "../minimax/bento-grid.mjs";
const ok = validateGrid("hero_1");
if (!ok) throw new Error("hero_1 invalid");
```

```javascript
import { renderCard } from "../minimax/card-renderers.mjs";
// assert renderer dispatch works for text/kpi/chart/list/image...
```

**Step 2: Run test to verify it fails**
Run: `node scripts/tests/bento-grid.harness.test.mjs && node scripts/tests/card-renderers.harness.test.mjs`  
Expected: FAIL。

**Step 3: Write minimal implementation**
- 在新模块定义 8 个网格模板与边界/重叠校验。
- 为 8 类卡片提供统一渲染入口（text/kpi/chart/image/icon_text/list/quote/comparison）。
- 在 `generate-pptx-minimax.mjs` 仅增加可选路径：
  - 当 `layout_grid` 存在时走 Bento 渲染。
  - 否则保持原有 official/legacy 逻辑不变。

**Step 4: Run test to verify it passes**
Run:
```bash
node scripts/tests/bento-grid.harness.test.mjs
node scripts/tests/card-renderers.harness.test.mjs
```
Expected: PASS。

**Step 5: Commit**
```bash
git add scripts/minimax/bento-grid.mjs scripts/minimax/card-renderers.mjs scripts/minimax/chart-factory.mjs scripts/generate-pptx-minimax.mjs scripts/tests/bento-grid.harness.test.mjs scripts/tests/card-renderers.harness.test.mjs
git commit -m "feat: add optional bento grid rendering path with card renderers"
```

### Task 4: 完整图表与 KPI/时间线组件接入（基于 Task 3）

**Files:**
- Modify: `scripts/minimax/chart-factory.mjs`
- Modify: `scripts/minimax/card-renderers.mjs`
- Test: `scripts/tests/chart-factory.harness.test.mjs`
- Test: `scripts/tests/kpi-timeline.harness.test.mjs`

**Step 1: Write the failing tests**
```javascript
// assert bar/line/pie/doughnut/area/radar/scatter are mapped
```

```javascript
// assert KPI requires number/unit/trend and timeline handles max item count
```

**Step 2: Run test to verify it fails**
Run:
```bash
node scripts/tests/chart-factory.harness.test.mjs
node scripts/tests/kpi-timeline.harness.test.mjs
```
Expected: FAIL。

**Step 3: Write minimal implementation**
- `chart-factory.mjs` 封装图表类型映射与统一参数。
- KPI 卡片与时间线卡片在 `card-renderers.mjs` 实现并走主题 token。
- 缺失数据直接抛出可重试错误码，不回退占位值。

**Step 4: Run test to verify it passes**
Run:
```bash
node scripts/tests/chart-factory.harness.test.mjs
node scripts/tests/kpi-timeline.harness.test.mjs
```
Expected: PASS。

**Step 5: Commit**
```bash
git add scripts/minimax/chart-factory.mjs scripts/minimax/card-renderers.mjs scripts/tests/chart-factory.harness.test.mjs scripts/tests/kpi-timeline.harness.test.mjs
git commit -m "feat: add chart factory and kpi timeline renderers with strict data checks"
```

### Task 5: 扩展质量门禁到“数据完整性 + 排版层级”

**Files:**
- Modify: `agent/src/ppt_quality_gate.py`
- Modify: `agent/tests/test_ppt_quality_gate.py`
- Test: `agent/tests/test_ppt_export_retry_flow.py`

**Step 1: Write the failing tests**
```python
def test_chart_placeholder_data_is_rejected():
    ...
```

```python
def test_content_slide_requires_min_blocks_and_typography_hierarchy():
    ...
```

**Step 2: Run test to verify it fails**
Run:
```bash
cd agent
pytest tests/test_ppt_quality_gate.py tests/test_ppt_export_retry_flow.py -q
```
Expected: FAIL。

**Step 3: Write minimal implementation**
- 新增视觉质量检查函数：
  - 图表/KPI 占位数据拦截
  - 内容页最小信息密度
  - 字号层级扁平检测
- 将新增问题统一落在 `QualityIssue`，并复用现有重试编排。

**Step 4: Run test to verify it passes**
Run:
```bash
cd agent
pytest tests/test_ppt_quality_gate.py tests/test_ppt_export_retry_flow.py -q
```
Expected: PASS。

**Step 5: Commit**
```bash
git add agent/src/ppt_quality_gate.py agent/tests/test_ppt_quality_gate.py agent/tests/test_ppt_export_retry_flow.py
git commit -m "feat: extend quality gate with data completeness and typography checks"
```

### Task 6: 放宽 v7 文案长度限制（40 -> 可配置）

**Files:**
- Modify: `agent/src/schemas/ppt_v7.py`
- Modify: `agent/tests/test_ppt_v7_schema.py`

**Step 1: Write the failing test**
```python
def test_v7_visible_text_limit_is_configurable():
    # 80 chars should pass when env overrides default
    ...
```

**Step 2: Run test to verify it fails**
Run: `cd agent; pytest tests/test_ppt_v7_schema.py -q`  
Expected: FAIL。

**Step 3: Write minimal implementation**
- 将硬编码 `<=40` 改为配置项（默认 80）。
- 保持旧行为兼容：未配置时使用默认值并保留校验报错语义。

**Step 4: Run test to verify it passes**
Run: `cd agent; pytest tests/test_ppt_v7_schema.py -q`  
Expected: PASS。

**Step 5: Commit**
```bash
git add agent/src/schemas/ppt_v7.py agent/tests/test_ppt_v7_schema.py
git commit -m "feat: make v7 visible text length limit configurable"
```

---

## End-to-End Verification

1. Run backend regression:
```bash
cd agent
pytest tests/test_exporter_official_mode.py tests/test_ppt_export_retry_flow.py tests/test_ppt_quality_gate.py tests/test_ppt_v7_schema.py -q
```

2. Run Node harnesses:
```bash
node scripts/tests/bento-grid.harness.test.mjs
node scripts/tests/card-renderers.harness.test.mjs
node scripts/tests/chart-factory.harness.test.mjs
node scripts/tests/kpi-timeline.harness.test.mjs
```

3. Run one real export flow:
```bash
python scripts/run_ui_ppt_v7_real_e2e.py
```

Expected:
- 无占位符污染与明显编码问题；
- 布局多样性门禁触发准确；
- 新中间态工作流可串联到导出接口；
- Bento 路径可开关启用，不影响现有 official 默认路径。

