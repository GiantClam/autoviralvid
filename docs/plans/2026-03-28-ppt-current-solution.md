# 当前 PPT 生成功能方案（已落地）

> 文档目的：沉淀当前线上/当前代码的真实实现方案，作为后续迭代基线。  
> 更新时间：2026-03-28

## 1. 目标与原则

- 目标：生成“可读、可讲、可交付”的专业 PPT，优先保障内容完整性、视觉锚点、版式稳定性和可重试性。
- 原则：
  - 不做一次性硬编码补丁，优先机制化（contract/schema/quality gate/retry）。
  - Python 与 Node 共享模板元数据来源，避免配置漂移。
  - 渲染前 fail-fast，渲染后可诊断、可重试。

---

## 2. 当前主流程（两阶段）

### 阶段 A：内容定稿（Python）

1. 需求调研（可接 Serper）
2. 便利贴大纲（OutlinePlan）
3. 策划稿中间态（PresentationPlan）
4. 规划稿转渲染 payload（含 blocks / layout / template profile）

核心入口：
- `agent/src/ppt_service.py`

### 阶段 B：视觉编排与导出（Python -> Node）

1. 应用视觉编排：补齐 content 页 contract（title + body/list + visual anchor）
2. 图片资产注入：图库优先（Serper 搜索 + 数据 URI 注入）
3. 调用 Node 渲染器（SVG-to-PPTX）
4. 质量门禁失败则按 deck/slide/block 维度重试

核心入口：
- `agent/src/minimax_exporter.py`
- `scripts/generate-pptx-minimax.mjs`

---

## 3. 统一契约与 Schema

## 3.1 渲染输入契约

Node 侧统一入口：
- `scripts/minimax/render-contract.mjs`

关键约束（content 页）：
- 必须包含：`title` + `body/list` + `image/chart/kpi` 视觉锚点
- 拒绝重复非标题文本
- 必须存在强调信号（`emphasis[]` 或数字焦点）

## 3.2 中间态 Schema

- 调研：`agent/src/schemas/ppt_research.py`
- 大纲：`agent/src/schemas/ppt_outline.py`
- 策划稿：`agent/src/schemas/ppt_plan.py`

---

## 4. 模板系统（去硬编码）

## 4.1 模板目录（单一来源）

新增共享 catalog：
- `scripts/minimax/templates/template-catalog.json`

包含：
- `layout_defaults`
- `subtype_overrides`
- `keyword_rules`
- 每个模板的 `skill_profile / hardness_profile / schema_profile / contract_profile`

## 4.2 Node/Python 同源读取

- Node：`scripts/minimax/templates/template-catalog.mjs`
- Python：`agent/src/ppt_template_catalog.py`

调用方：
- Node：`template-registry.mjs`、`template-profiles.mjs`
- Python：`ppt_service.py`、`minimax_exporter.py`

---

## 5. 渲染机制

## 5.1 模板渲染（数据驱动）

文件：
- `scripts/minimax/templates/template-renderers.mjs`
- `scripts/minimax/templates/template-specs.mjs`

实现要点：
- 模板不再写死业务文案，优先从 `sourceSlide.blocks/title/narration` 取数据。
- 文本做去重、裁剪、字号收敛（防溢出、防重复）。
- 渲染几何使用边界约束（防图形越界）。

## 5.2 SVG 通道

文件：
- `scripts/minimax/svg-slide.mjs`

修复点：
- `addImage({data})` 使用 `image/svg+xml;base64,...`（兼容 SVG-to-PPTX）
- `svg_mode=on` 时先注入 SVG 底层，再叠加可编辑元素

## 5.3 卡片渲染与图表

文件：
- `scripts/minimax/card-renderers.mjs`
- `scripts/minimax/chart-factory.mjs`

实现要点：
- image block 缺图时统一品牌占位图（SVG）兜底，不允许空框
- chart 数据契约不合法直接抛错（可重试）

---

## 6. 图片注入策略（图库优先）

文件：
- `agent/src/ppt_service.py` (`_hydrate_image_assets`)

策略：
1. 优先 stock 站点检索（可配置 domain 列表）
2. 拉取后转 data URI 写回 block
3. 失败时落统一品牌占位 SVG

环境变量：
- `SERPER_API_KEY`（必需）
- 可选：`PPT_STOCK_SEARCH_DOMAINS`、`PPT_IMAGE_ASSET_ENABLED`

---

## 7. 质量门禁与重试

文件：
- `agent/src/ppt_quality_gate.py`
- `agent/src/ppt_retry_orchestrator.py`

当前门禁覆盖：
- 空白页、占位符污染、乱码文本
- 图表/指标数据占位检查
- 布局多样性（比例、相邻重复、长文档 variety）
- 内容密度、字体层级
- 图片缺失、图表可读性
- 重复文本、弱强调（新增）

---

## 8. Agent/Skill/Hardness/Schema/Contract 对齐

每页会带：
- `template_id`
- `skill_profile`
- `hardness_profile`
- `schema_profile`
- `contract_profile`

这些字段来自共享 catalog，不再在多个文件中重复硬编码。

---

## 9. 回归与验收（当前可执行）

## 9.1 Python

```bash
python -m py_compile agent/src/ppt_service.py agent/src/minimax_exporter.py agent/src/ppt_quality_gate.py agent/src/ppt_template_catalog.py
agent\\.venv\\Scripts\\python.exe -m pytest agent/tests/test_ppt_quality_gate.py agent/tests/test_ppt_contract.py -q
```

## 9.2 Node Harness

```bash
node scripts/tests/card-renderers.harness.test.mjs
node scripts/tests/template-renderers.harness.test.mjs
node scripts/tests/render-contract.harness.test.mjs
```

## 9.3 按现有流程重跑

```bash
node scripts/generate-pptx-minimax.mjs \
  --input test_outputs/lingchuang_rerun/run-d1ef781b8ac5-20260328-001855/render_payload.json \
  --output test_outputs/lingchuang_rerun/run-d1ef781b8ac5-20260328-001855/lingchuang_refixed.pptx \
  --render-output test_outputs/lingchuang_rerun/run-d1ef781b8ac5-20260328-001855/lingchuang_refixed.render.json
```

---

## 10. 后续建议（下一阶段）

1. 增加“渲染后视觉 QA”（截图 + 多模态模型）并接入自动重试。
2. 对第 2/3/5 页做像素级模板细化（字重、留白、线框细节）。
3. 增加模板 A/B 评分机制，自动选择最优模板族。

