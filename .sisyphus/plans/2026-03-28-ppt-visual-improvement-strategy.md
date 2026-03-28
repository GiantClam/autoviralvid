# PPT 视觉质量提升方案：当前实现 × 深度调研报告 对比与融合

> **文档目的**：对比当前 PPT 生成系统实现（`2026-03-28-ppt-current-solution.md`）与深度调研报告（`deep-research-report.md`），针对**卡片排版问题、视觉质量问题、内容页样式单一**三大痛点，形成可落地的改进策略。  
> **约束**：本方案仅为策略文档，不涉及代码修改。  
> **更新时间**：2026-03-28（v2 — 经代码走读和实际产出物验证后更新）

---

## 零、实际产出物问题验证（`lingchuang_new_templates` 实物分析）

> 以下分析基于 `test_outputs/lingchuang_new_templates/` 的 `.input.json`、`.render.json`、`unpacked/ppt/slides/*.xml` 的逐文件走读。

### 0.1 关键配置参数（从 render.json 提取）

| 参数 | 实际值 | 影响 |
|------|--------|------|
| `visual_priority` | **false** | ❌ 所有 backdrop 装饰元素未渲染 |
| `disable_local_style_rewrite` | **true** | ❌ 本地样式重写被禁用 |
| `original_style` | **true** | 保留原始样式 |
| `visual_density` | `"dense"` | 内容密度偏高 |
| `palette_key` | `"platinum_white_gold"` | 铂金白金色板 |
| `style_variant` | `"soft"` | 柔和均衡风格 |

### 0.2 slide_type 分布（8 个内容页）

| slide_type | 出现次数 | 占比 | 页面 |
|-----------|---------|------|------|
| `grid_3` | **3** | 37.5% | lc-02, lc-03, lc-06 |
| `quote_stat` | **3** | 37.5% | lc-04, lc-05, lc-07 |
| `grid_2` | 1 | 12.5% | lc-08 |
| `timeline` | 1 | 12.5% | lc-09 |

**问题**：`grid_3` 和 `quote_stat` 各占 37.5%，两种类型合计 75%。虽然单项未超过 45% 的门禁阈值，但观感极其单调。

### 0.3 template_family 分布

| 模板族 | 使用次数 | 页面 |
|--------|---------|------|
| `architecture_dark_panel` | **2** | lc-02, lc-09 |
| 其余 6 种模板 | 各 1 次 | lc-03~lc-08 |

**问题**：`architecture_dark_panel` 重复使用。

### 0.4 视觉一致性问题（从 slide XML 验证）

**所有 10 页 slide 的背景色完全相同**：
```xml
<a:solidFill><a:srgbClr val="060B17"/></a:solidFill>  <!-- 极深海军蓝/近黑色 -->
```

**所有 content 页的 header 区完全相同**：
- 颜色：`0A0A0A`（纯黑）
- 高度：`621792 EMU` ≈ `0.68"`（soft 风格的 headerHeight）
- 标题字号：`sz="2600"` = 26pt
- 标题字色：`E8F0FF`（浅蓝白）

**后果**：尽管分配了 7 种不同的 template_family，但因为 `buildDarkTheme()` 将所有模板的背景统一覆盖为暗色，实际渲染出的每一页看起来几乎一样——深黑背景 + 黑色标题栏 + 浅色文字。

### 0.5 图片占位问题

input.json 中 3 个 image block（lc-03, lc-04, lc-08）的 URL 都是**最小化空白 PNG**：
```
data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAlgAAAFvCAYAAABgJfQb...
```
解码后是 600×375 的**纯透明空白图**。说明图片注入流程（Serper 图库搜索 → data URI 转换）产出了占位图而非实际图片。

### 0.6 official_output.elements 全为空

```json
"official_output": {
  "slides": [
    { "slide_id": "lc-02", "elements": [] },
    ...
  ]
}
```
所有 slide 的 `elements: []`，说明 official output mapper 没有填充任何 elements，内容全靠 blocks → 模板渲染器路径。

### 0.7 问题清单总结

| # | 问题 | 严重性 | 根因 |
|---|------|--------|------|
| 1 | 所有页面背景色相同（060B17） | 🔴 致命 | `buildDarkTheme()` 覆盖所有模板为暗色；light 模板未生效 |
| 2 | 所有 header 区外观相同 | 🔴 致命 | `addHeader()` 对非 light 模板使用相同结构 |
| 3 | visual_priority=false | 🟡 严重 | 无 backdrop 装饰元素 |
| 4 | 图片全为空白占位图 | 🟡 严重 | Serper 图库搜索未返回有效结果或返回后转 data URI 失败 |
| 5 | grid_3 + quote_stat 占 75% | 🟡 严重 | 门禁阈值 0.45 只限制单一类型，组合仍单调 |
| 6 | architecture_dark_panel 重复 | 🟢 中等 | 关键词规则覆盖面广 |
| 7 | official_output.elements 全空 | 🟢 中等 | 不影响最终渲染但影响可追溯性 |

---

## 一、对比总览：当前实现 vs 深度调研报告

### 1.1 架构对比

| 维度 | 当前实现 | 调研报告方案 | 差距分析 |
|------|----------|-------------|----------|
| **整体架构** | 两阶段管线（Python 内容定稿 → Node PptxGenJS 渲染） | 三模式路由（强模板 / 模板+微调 / Skill主导） | 当前缺少智能路由层，所有请求走同一管线 |
| **模板系统** | 共享 catalog（`template-catalog.json`），关键词+评分路由 | 元数据过滤 + 向量检索 + 加权评分精排 | 当前无语义向量检索，仅靠关键词匹配 |
| **编辑策略** | 从零生成每页（blocks → 渲染） | 差异驱动编辑计划（keep/delete/split/merge/replace） | 当前无增量编辑概念，每次全量重建 |
| **质量门禁** | 结构化验证（空白页/占位符/多样性/密度） | 多维评分（结构覆盖/风格一致/文本密度/图表完整/语义一致） | 当前无视觉截图QA、无风格一致性评分 |
| **重试机制** | deck/slide/block 三级重试 | 基于质量评分的回退（总分<60 或关键指标不足） | 当前重试是结构驱动，非质量评分驱动 |
| **视觉系统** | 18色板 + 4风格食谱 + 4视觉预设 | 概念化的配色/字体映射 | 当前已有完整设计token体系，但调研报告缺实现细节 |

### 1.2 能力矩阵

| 能力项 | 当前实现 | 调研报告 | 综合评价 |
|--------|---------|---------|---------|
| PptxGenJS 渲染引擎 | ✅ 已实现 | ❌ 仅概念 | **保留当前** |
| 模板评分路由 | ✅ 8维评分 | ✅ 4维加权评分 | **融合升级** |
| 语义向量检索 | ❌ 缺失 | ✅ 有设计 | **可引入** |
| 差异编辑计划 | ❌ 缺失 | ✅ JSON Schema | **可引入（长期）** |
| 多模态视觉QA | ❌ 缺失 | ✅ 有概念 | **应引入** |
| 卡片布局引擎 | ⚠️ 7种模板渲染器+4种通用分支（comparison/timeline/table/default） | ❌ 未涉及 | **需加强通用分支** |
| 内容子类型系统 | ⚠️ 6种定义，仅 comparison/timeline/table/data/section 有独立分支；mixed_media/image_showcase 无实现 | ✅ 6种明确定义 | **需补全** |
| 设计token体系 | ✅ 完整（4风格食谱+18色板+4视觉预设） | ⚠️ 概念化 | **保留当前** |
| 图片注入 | ⚠️ Serper API 图库搜索（`site:unsplash.com` 等）→ DataURI 转换；**非直接 Stock API** | ❌ 未涉及 | **需改进搜索质量与成功率** |
| 重试编排 | ✅ 三级重试（deck/slide/block） | ⚠️ 概念化 | **保留当前** |

### 1.3 结论

> **当前实现的工程基础扎实**（渲染引擎、模板系统、质量门禁、重试机制），但在**视觉丰富度和布局多样性**上存在明显短板。调研报告在**架构设计和流程编排**上有参考价值，但缺乏具体实现细节。**最优策略是在当前工程基础上，融合调研报告的架构理念，针对三大痛点做精准改进。**
>
> ⚠️ **代码走读发现的关键问题**（v2 新增）：
> - `buildDarkTheme()`（`design-tokens.mjs`）对所有暗色模板族覆盖背景为统一深色（`060B17`），导致 7 种不同模板族渲染出视觉相同的页面
> - `visual_priority=false` 导致所有 backdrop 装饰不渲染
> - 图片注入通过 Serper 图库搜索，但实际产出中大量返回空白占位图（搜索或转换失败）
> - `grid_3 + quote_stat` 两种 slide_type 合计占 75%，门禁仅检查单一类型占比，无法捕获组合单调性

---

## 二、痛点根因分析

### 2.1 痛点一：卡片排版问题

#### 现象
- 卡片位置错乱、重叠或留白不均
- 多卡片布局时对齐失败
- 卡片内容溢出或截断

#### 根因链

```
根因 1: 模板渲染器与通用渲染器的割裂（代码走读验证 ✅）
├── 7 个模板族有专用 renderTemplateContent() 实现（template-renderers.mjs L1085-1187）
├── 但 layout_grid="template_canvas" 时模板渲染器接管全部布局
├── 若模板渲染器内部未正确处理某些 block 类型（如 workflow/diagram），内容丢失
└── 非模板路径仅有 comparison/timeline/table/data 4 种通用分支，其余 fallback 到单列/双列

根因 2: 通用分支的卡片布局单一（代码走读验证 ✅）
├── default 分支（L1504-1611）：要点 < 5 条时为 左侧bullet + 右侧KPI面板
├── 要点 ≥ 5 条时退化为全宽单列 (useSingleColumn=true, L1507)
├── 右侧面板永远是 data bars 或 keyMetric 文字，无其他视觉元素
└── 缺少 mixed_media（图文混排）和 image_showcase（主图展示）布局

根因 3: 卡片高度计算固定（代码走读验证 ✅）
├── bodyBottom 硬编码为 5.05"（L1364）
├── 不同内容量的卡片使用相同高度
└── 内容少时大量留白，内容多时 bullet 被 yy + rowH > y + h 条件截断（L1168）

根因 4: card_id 映射问题已部分解决（代码走读修正 ⚠️）
├── Python 侧 _LAYOUT_CARD_SLOTS 已定义语义化 ID（L465-474: left/right/c1/c2/c3 等）
├── _assign_layout_card_ids() 已按布局查表分配（L500-546）
├── 但 input.json 中多数 content 页使用 layout_grid="template_canvas"
├── template_canvas 不在 _LAYOUT_CARD_SLOTS 中，card_id 分配回退到 title/body/list/image 等类型名
└── Node 侧 getCardById() fallback 到索引时无警告（bento-grid.mjs L111-125）
```

#### 对应代码位置

| 问题 | 文件 | 关键行 |
|------|------|--------|
| 模板渲染器入口 | `template-renderers.mjs` | L1111-1187 `renderTemplateContent()` switch |
| 通用布局分支 | `generate-pptx-minimax.mjs` | L1387-1611 `addContentSlide()` |
| 单列退化 | `generate-pptx-minimax.mjs` | L1507 `useSingleColumn = safeBullets.length >= 5` |
| 高度固定 | `generate-pptx-minimax.mjs` | L1364 `bodyBottom = 5.05` |
| card_id 分配 | `ppt_service.py` | L465-474 `_LAYOUT_CARD_SLOTS`, L500-546 `_assign_layout_card_ids()` |
| getCardById fallback | `bento-grid.mjs` | L111-125 `grid.cards[index % grid.cards.length]` |

---

### 2.2 痛点二：视觉质量问题

#### 现象
- 整体观感"AI味"重，缺乏设计感
- 颜色使用单一或不协调
- 缺少视觉层次（阴影、间距、对比度不足）
- 装饰元素少，页面空洞

#### 根因链

```
根因 1: buildDarkTheme() 覆盖所有暗色模板为统一深色背景（代码走读验证 ✅ —— 致命根因）
├── buildTheme() (L764-788) 先构建 baseTheme，bg = palette[2]
├── 然后调用 buildDarkTheme(baseTheme, templateFamily)（design-tokens.mjs）
├── buildDarkTheme() 对所有非 "_light" 后缀的模板族，将 bg 覆盖为极深色（060B17）
├── 结果：7 种不同模板族在实际渲染中使用完全相同的背景色
└── 这是视觉单调的第一大根因

根因 2: addHeader() 对所有暗色模板使用同一结构（代码走读验证 ✅）
├── isLightTemplate = templateFamily.endsWith("_light") (L1104)
├── 非 light 模板：bg = theme.bg (被 buildDarkTheme 统一为深色)
├── 非 light 模板：header = theme.primary (同一色板下固定值)
├── 标题位置、字号、颜色完全相同
└── 结果：所有暗色模板的页面 header 区域看起来一模一样

根因 3: visual_priority 被 disable_local_style_rewrite 间接关闭（代码走读验证 ✅）
├── original_style 默认 true → disableLocalStyleRewrite 默认 true（L106-111）
├── visualConfig.enabled 受 visual_priority 控制
├── 当 visual_priority=false 时 addVisualBackdrop() 直接 return（L819）
├── 实际产出中 visual_priority=false，所有 backdrop 装饰未渲染
└── 页面没有任何装饰性视觉元素

根因 4: backdrop 种类有限（代码走读验证 ✅）
├── 仅 4 种类型: high-contrast / color-block / soft-gradient / minimal (L840-916)
├── 加上无装饰时的 "minimal line" 模式 (L820-838)
├── 全 deck 由 visual_preset 决定 backdrop 类型，所有内容页用同一种
└── 即使 visual_priority=true，所有页面的装饰也相同

根因 5: 图片搜索质量不稳定（代码走读验证 ✅ —— 修正: 非直接 Stock API）
├── 图片来源：Serper Image Search API，带 site:unsplash.com/pexels.com/pixabay.com 过滤
├── 环境变量：SERPER_API_KEY（必需），PPT_STOCK_SEARCH_DOMAINS（可配）
├── 搜索关键词由 block content 提取，如"workflow-screen"、"case-board"（太抽象）
├── 搜索失败或无结果时，使用 fallback_stock_terms（通用背景词）
├── 最终 fallback: 品牌占位 SVG → 空白 PNG（在 lingchuang 产出中已发生）
└── 根本原因：搜索词不够具体，且 Serper 图库搜索对中文效果不佳

根因 6: 无渲染后视觉 QA（保持不变）
├── 质量门禁仅检查结构属性（空白/占位符/密度/多样性）
├── 无截图 + 多模态模型评估
└── 视觉问题（背景全黑、图片空白、元素重叠）无法在质量门禁中捕获
```

#### 对应代码位置

| 问题 | 文件 | 关键位置 |
|------|------|----------|
| 🔴 背景色覆盖 | `design-tokens.mjs` | `buildDarkTheme()` 全文 |
| 🔴 header 统一 | `generate-pptx-minimax.mjs` | L1102-1158 `addHeader()`, L1104 `isLightTemplate` |
| 🟡 视觉优先级 | `generate-pptx-minimax.mjs` | L106-111 `originalStyle→disableLocalStyleRewrite`, L819 `visualConfig?.enabled` |
| backdrop | `generate-pptx-minimax.mjs` | L818-917 `addVisualBackdrop()` |
| 🟡 图片搜索 | `ppt_service.py` | L1495-1645 `_hydrate_image_assets()`, L1566-1611 搜索逻辑 |
| 质量门禁 | `ppt_quality_gate.py` | L353-584 `validate_slide()` — 仅结构检查 |

---

### 2.3 痛点三：内容页样式单一

#### 现象
- 连续多页使用相同布局（标题+要点列表）
- 缺少图表、时间轴、对比图等丰富版式
- 视觉锚点不足（纯文字页面偏多）

#### 根因链

```
根因 1: 子类型推断与 subtype_overrides 联合导致类型坍缩（代码走读验证 ✅）
├── inferSubtype()（minimax-style-heuristics.mjs L38-81）基于关键词 + block 类型匹配
├── 未命中关键词时 return "content"
├── resolveSubtypeByTemplate() 再查 template-catalog.json 的 subtype_overrides
├── 多个模板的 override 映射到相同类型（如 architecture_dark_panel, consulting_warm_light 都 → "comparison"）
├── 结果：在 lingchuang 产出中 grid_3 × 3 + quote_stat × 3 占 75%
└── 虽然单项不超 45%，但两种类型组合占绝对主导

根因 2: 通用渲染分支只有 4+1 种布局（代码走读验证 ✅）
├── addContentSlide() 通用分支（L1387-1611）:
│   ├── table → 全宽表格
│   ├── comparison → 两列 A/B 卡片
│   ├── timeline → 水平步骤条
│   ├── data → 左 bullet + 右 data bars
│   └── else → 左 bullet + 右 KPI 面板 (或 useSingleColumn 全宽)
├── 缺失: mixed_media（图文混排）, image_showcase（主图展示）
├── 模板渲染器路径（renderTemplateContent）有 7 种实现，但它们各自内部也类似（header + 卡片区域）
└── 结果：即使走模板路径，视觉差异也不大（见根因 2.2 的 buildDarkTheme 问题）

根因 3: 布局多样性门禁存在"组合盲区"（代码走读验证 ✅）
├── validate_layout_diversity()（ppt_quality_gate.py L599-733）
├── max_type_ratio = 0.45：仅限制单一类型占比
├── 不检查 TOP-2 类型组合占比（例如 grid_3 37.5% + quote_stat 37.5% = 75%）
├── max_adjacent_repeat = 1：允许 ABAB 模式（交替重复）
├── 长 deck 要求 4 种：lingchuang 有 4 种（grid_3/quote_stat/grid_2/timeline）恰好通过
└── 结果：门禁全部通过，但观感仍然极其单调

根因 4: template_family 评分系统中 keyword_rules 导致特定模板过度命中（代码走读验证 ✅）
├── template-catalog.json keyword_rules 中 architecture_dark_panel 匹配词: ["architecture", "orchestration", "sandbox", "dsl", "workflow engine", "编排", "架构"]
├── "编排"/"架构" 在 AI/技术类 PPT 中高频出现
├── inferTemplateFamilyFromContent() (template-registry.mjs L172-220) 中 keyword 评分权重较高
└── 结果：architecture_dark_panel 在 lingchuang deck 中使用了 2 次

根因 5: 图片注入成功率低，视觉锚点不足（代码走读验证 ✅）
├── 3 个 image block 全部为空白占位 PNG（见第零节分析）
├── _hydrate_image_assets()（ppt_service.py L1495-1645）用 Serper Images 搜索
├── 搜索词直接取 block.content（如 "workflow-screen"/"case-board"/"comparison-screen"）
├── 这些是语义标签而非真实图片描述，搜索命中率极低
├── fallback_stock_terms 为通用词（"科技 抽象 背景"），与主题关联度差
└── 结果：content 页缺少图片，视觉锚点 fallback 为文本，页面空洞
```

#### 对应代码位置

| 问题 | 文件 | 关键位置 |
|------|------|----------|
| 子类型推断 | `generate-pptx-minimax.mjs` | L597-633 `buildSubtypeCandidates()` |
| 子类型渲染 | `generate-pptx-minimax.mjs` | L1277-1552 仅 comparison/timeline 分支 |
| 多样性阈值 | `ppt_planning.py` | `enforce_layout_diversity()` |
| 模板偏向 | `template-catalog.json` | `keyword_rules` 权重分配 |
| 视觉锚点 | `ppt_service.py` | L843-972 `_ensure_content_contract()` |

---

## 三、改进策略

### 策略总原则

1. **保留工程基础**：不推翻当前的 Python→Node 管线，在此基础上增强
2. **融合调研理念**：引入调研报告的智能路由、质量评分、多维评估概念
3. **优先解决痛点**：按影响面排序，先解决内容页样式单一（覆盖面最广），再解决卡片排版，最后提升视觉质量
4. **可度量可回退**：每项改进都有明确的度量指标和回退策略

---

### 3.1 策略 A：内容页版式多样化（解决痛点三）

#### A1. 补全 6 种内容子类型渲染器

**目标**：在 `addContentSlide()` 中实现全部 6 种子类型的独立渲染逻辑

| 子类型 | 当前状态 | 改进方向 | 布局描述 |
|--------|---------|---------|---------|
| **text** | ✅ 已实现 | 增加 icon+text rows 变体 | 左对齐要点 + 彩色图标圆 |
| **mixed_media** | ❌ 未实现 | **新增** | 左文右图（或反转），图片占 40-50% |
| **data_visualization** | ❌ 未实现 | **新增** | 左侧 SVG 图表 + 右侧 1-3 条洞察 + 数据来源 |
| **comparison** | ✅ 已实现 | 增加卡片式变体 | 当前双列 → 增加带圆角卡片的 A/B 对比 |
| **timeline** | ✅ 已实现 | 增加垂直变体 | 当前水平步骤条 → 增加垂直时间轴 |
| **image_showcase** | ❌ 未实现 | **新增** | 主图铺满 + 底部/侧面文字说明 |

**每个子类型须包含至少 2 种布局变体**，由渲染器根据内容量自动选择。

#### A2. 增强子类型推断逻辑

**当前**：`inferSubtypeHeuristic()` 仅用关键词匹配  
**改进**：采用**多信号融合评分**

```
评分信号:
  1. 标题关键词匹配 (权重 0.3)
     - "对比/vs/比较" → comparison +3
     - "流程/步骤/阶段" → timeline +3
     - "数据/增长/趋势" → data_visualization +3

  2. blocks 内容分析 (权重 0.4)
     - 含 chart block → data_visualization +5
     - 含 image block → mixed_media/image_showcase +4
     - 含 kpi block → data_visualization +3
     - 仅 text blocks → text +2

  3. 相邻页回避 (权重 0.3)
     - 与前一页相同子类型 → 当前子类型 -3
     - 与前两页都相同 → 当前子类型 -5
```

**选择得分最高的子类型，但保底不低于 "text"。**

#### A3. 收紧布局多样性门禁

| 参数 | 当前值 | 建议值 | 理由 |
|------|--------|--------|------|
| `max_type_ratio` | 0.45 | **0.35** | 单一布局不超过 35%，确保至少 3 种布局轮换 |
| `min_layout_variety_for_long` | 4 | **5** | 长 deck (≥10页) 要求 5 种不同布局 |
| 相邻重复间隔 | 1 | **2** | 同类布局至少间隔 2 页才可重复 |
| **【新增】TOP-2 组合占比** | 无 | **≤ 0.65** | TOP-2 类型合计不超过 65%（解决 lingchuang 中 75% 的问题） |
| **【新增】ABAB 模式检测** | 无 | **禁止连续交替 ≥ 4 次** | 防止 grid_3→quote_stat→grid_3→quote_stat 交替 |

#### A4. 每页强制视觉锚点

**从调研报告引入"结构覆盖率"概念**：

```
content 页视觉锚点要求:
  - 必须包含至少 1 个非文本元素（image / chart / kpi / icon-grid / timeline-connector）
  - visual_anchor_ratio 目标 ≥ 0.9（当前门禁要求 0.8）
  - text_only_content_slides 必须 = 0
```

**落地方式**：在 `_ensure_content_contract()` 中，若 blocks 全为 text 类型，自动注入一个 KPI 或 icon-grid block。

---

### 3.2 策略 B：卡片排版稳定化（解决痛点一）

#### B1. 修复 `template_canvas` 布局的 card_id 映射（代码走读修正）

**实际现状**：Python 侧 `_LAYOUT_CARD_SLOTS`（L465-474）已定义语义化 ID（left/right/c1/c2/c3 等），`_assign_layout_card_ids()`（L500-546）已实现按布局查表分配。**这不是从零开始的工作。**

**真正的问题**：大多数 content 页使用 `layout_grid="template_canvas"`，这个值不在 `_LAYOUT_CARD_SLOTS` 中，导致 card_id 分配回退为按 block_type 命名（title/body/list/image/kpi）。

**改进方向**：
1. 为 `template_canvas` 定义通用槽位映射（例如 `[title, body, list, visual, kpi]`）
2. 或者让每个模板族声明自己支持的槽位，在 `template-catalog.json` 中添加 `card_slots` 字段
3. Node 侧 `getCardById()` (bento-grid.mjs L111-125) 在 fallback 到索引时应输出 warning log

#### B2. 动态卡片高度计算

**当前问题**：`bodyBottom = 5.05"` 硬编码  
**改进**：根据内容量动态分配

```
计算逻辑:
  available_height = slide_height(5.625) - header_height - top_margin - bottom_margin
  per_card_height = (available_height - (card_count - 1) * gap) / card_count
  min_card_height = 0.8"  // 最小卡片高度
  
  如果 per_card_height < min_card_height:
    // 内容过多，切换到滚动式或分页策略
    split_to_two_slides()
```

#### B3. 溢出检测与自动回流

**当前问题**：`clampRectToSlide()` 仅防止越界，不处理内容溢出  
**改进**：加入内容回流逻辑

```
回流策略优先级:
  1. fit: "shrink" → 缩小字号（最低不低于 10pt）
  2. 截断 + "..." → 超长文本省略
  3. 减少 bullets → 保留前 N 条核心要点
  4. 降级布局 → 从 grid_4 降为 grid_3 或 split_2
  5. 分页 → 内容超量时拆为两页
```

#### B4. 文本拆分优化

**当前问题**：分隔符正则不完整，中文断句不佳  
**改进**：

```
新分隔符正则:
  /[;；。！？!?，,、\n\r]+/

智能断句规则:
  - 优先在句号/分号处断
  - 次选在逗号/顿号处断
  - 每个 bullet 最长 72 字符（中文）/ 120 字符（英文）
  - 超长段落按意群拆分，保留语义完整性
```

---

### 3.3 策略 C：视觉质量提升（解决痛点二）

#### C0. 【新增 P0】修复 buildDarkTheme() 背景色覆盖问题

**这是产出物验证中发现的第一大致命根因。**

**当前**：`buildDarkTheme()`（`design-tokens.mjs`）对所有非 `_light` 后缀的模板族，将 `theme.bg` 覆盖为极深色（`060B17`），无视色板中 `palette[2]` 的原始值。

**后果**：
- `platinum_white_gold` 色板的 `palette[2]` = `D4AF37`（金色），但被覆盖为 `060B17`
- 7 种暗色模板渲染出完全相同的深黑背景
- 模板多样性在视觉上完全失效

**改进**：
1. `buildDarkTheme()` 应保留色板中 `palette[2]` 的色相信息，仅在亮度上做适度暗化
2. 或者为每个模板族定义独立的 `bgOverride` 色值（在 `template-catalog.json` 中）
3. 至少保证不同模板族之间的背景色有可辨别的差异（色相或明度差 ≥ 15%）

#### C0.5 【新增 P0】header 区域视觉差异化

**当前**：`addHeader()`（L1102-1158）对所有非 light 模板使用 `theme.primary` 填充 header，位置/高度/颜色完全相同。

**改进**：
1. 不同模板族的 header 应有差异化的视觉处理（如 dashboard_dark 用色带，architecture_dark_panel 用渐变）
2. 在 `template-catalog.json` 中为每个模板族定义 `header_style` 属性
3. 或让模板渲染器自行控制 header（不走通用 `addHeader()`）

#### C1. 视觉优先级默认开启

**当前**：`original_style=true`（默认）→ `disableLocalStyleRewrite=true` → `visual_priority` 被间接抑制。`addVisualBackdrop()`（L818-917）在 `!visualConfig.enabled` 时直接 return。

**改进**：**默认开启 visual_priority**，将 `original_style` 默认值改为 `false`，或将 `visual_priority` 与 `original_style` 解耦

```
影响范围:
  - addVisualBackdrop() 将默认执行
  - 每页自动添加装饰性元素
  - 页面不再"裸奔"
  - 同时不影响 original_style 对色板/字体的保留
```

#### C2. 扩充 backdrop 库

**当前**：4 种 backdrop 类型  
**改进**：扩充到 **8+ 种**

| 新增类型 | 描述 | 适用子类型 |
|---------|------|-----------|
| `corner-accent` | 右上角色块 + 左下角细线 | text, mixed_media |
| `side-panel` | 左侧 15% 宽色带 | data_visualization |
| `bottom-wave` | 底部曲线装饰 | image_showcase |
| `dot-grid` | 浅色圆点网格背景 | comparison |
| `diagonal-split` | 对角线分割两色背景 | comparison, timeline |

**每种 backdrop 从设计 token 中读取颜色**，不硬编码。  
**deck 内 backdrop 自动轮换**，不允许连续 3 页以上使用同一类型。

#### C3. 色板自动匹配

**当前**：`normalizeVisualPreset()`（L316-325）已有基础的话题关键词→preset 映射，但 preset 仅 4 种。色板选择由 `selectPaletteHeuristic()` 处理，但 `original_style=true` 时色板保持不变。  
**改进**：在 `template-catalog.json` 中添加 `palette_keywords` 规则，与 preset 系统解耦

```json
{
  "palette_keywords": {
    "科技|AI|人工智能|cloud|tech": "pure_tech_blue",
    "金融|投资|财务|fintech": "business_authority",
    "教育|培训|学术|education": "education_charts",
    "医疗|健康|医药|health": "modern_wellness",
    "环保|ESG|绿色|sustainability": "forest_eco",
    "品牌|发布会|launch|premium": "platinum_white_gold",
    "旅游|度假|夏日|travel": "coastal_coral",
    "美食|餐厅|food": "art_food"
  }
}
```

**匹配逻辑**：用户 topic + audience 做关键词匹配，命中则推荐对应色板；未命中则用默认色板（当前行为不变）。

#### C3.5 【新增】改进图片搜索策略

**当前问题**（代码走读验证 ✅）：
- `_hydrate_image_assets()`（ppt_service.py L1495-1645）从 block.content 提取搜索词
- 但 block.content 是语义标签（如 `"workflow-screen"`、`"case-board"`），不是有效的图片搜索词
- Serper 搜索用 `site:unsplash.com` 等过滤，但这些语义标签在图库中无结果
- fallback_stock_terms 是通用词（`"科技 抽象 背景"`），与 slide 主题无关

**改进方向**：
1. 搜索词应从 **slide.title + slide.narration** 提取关键词，而非 block.content
2. 添加"搜索词增强"步骤：将语义标签翻译为图库友好的描述（如 "workflow-screen" → "software workflow dashboard interface screenshot"）
3. 提高 fallback 质量：从 deck 级别提取 topic 关键词作为 fallback，而非固定的通用词
4. 增加图片缓存：相同 deck 内相似搜索词复用已获取的图片

#### C4. 风格食谱自动选择

**当前**：`minimax_style_variant` 在导出时硬编码  
**改进**：基于 `PPTPipelineRequest.purpose` 或内容特征自动选择

| 场景 | 推荐风格 | 触发条件 |
|------|---------|---------|
| 数据报告/财务 | Sharp & Compact | 含大量表格/图表 |
| 企业汇报/商务 | Soft & Balanced | 默认 / 企业相关话题 |
| 产品介绍/营销 | Rounded & Spacious | 产品/营销/创意类话题 |
| 发布会/品牌展示 | Pill & Airy | 品牌/发布会/高端类 |

#### C5. 引入渲染后视觉 QA

**从调研报告引入多模态质量评估概念**：

```
渲染后 QA 流程:
  1. 生成 PPTX 后，调用 pptx_rasterizer.py 将每页转为 PNG
  2. 将 PNG 发送给多模态模型（可用 Claude Vision）
  3. 评估维度:
     - 文字是否溢出/截断？(二值判断)
     - 元素是否重叠？(二值判断)
     - 色彩对比度是否足够？(评分 0-100)
     - 整体排版美观度？(评分 0-100)
  4. 若有严重问题（溢出/重叠），触发该页重试
  5. 若美观度评分 < 60，标记为待优化
```

**分阶段落地**：
- **Phase 1**：仅检测溢出和重叠（结构性问题，可自动修复）
- **Phase 2**：加入色彩对比度评估
- **Phase 3**：加入整体美观度评分（需要评分基线校准）

---

### 3.4 策略 D：融合调研报告的架构优化（中长期）

#### D1. 智能路由层（调研报告"模式 A/B/C"简化版）

**不需要建设完整的模板检索+向量库**，但可以引入**路由分级**概念：

```
路由判断逻辑（在 ppt_service.py 中）:

1. 分析 PPTPipelineRequest 的复杂度:
   - 页数 ≤ 5 且无特殊要求 → 快速模式（简化管线）
   - 页数 6-15 且有明确话题 → 标准模式（完整管线）
   - 页数 > 15 或高度定制 → 精细模式（增加 QA 循环）

2. 根据模式调整:
   - 快速模式: 跳过研究阶段，使用默认模板族
   - 标准模式: 完整 5 阶段管线
   - 精细模式: 5 阶段 + 渲染后视觉 QA + 自动重试
```

#### D2. 质量评分体系（融合调研报告"6维评分"）

**将当前的二值门禁升级为加权评分**：

```
质量评分 = 
  0.25 × 结构覆盖度（必选章节完整性）
  + 0.20 × 布局多样性（子类型分布均匀度）
  + 0.20 × 视觉锚点覆盖率（非文本元素比例）
  + 0.15 × 文本密度合理性（每页文字量偏差）
  + 0.10 × 图片完整性（图片加载成功率）
  + 0.10 × 一致性（字体/色彩/间距统一度）

回退阈值:
  - 总分 < 60: 触发全 deck 重试
  - 单项 < 40: 触发该维度对应的修复策略
```

#### D3. 合同 Profile 精细化

**当前仅 default/high_density_consulting/lenient_draft 三种**  
**改进**：根据常见业务场景扩展

| Profile | 目标受众 | 视觉锚点要求 | 最大文本密度 | 推荐风格 |
|---------|---------|-------------|-------------|---------|
| `investor_pitch` | 投资人 | ≥90% | 3 bullets/页 | Pill & Airy |
| `status_report` | 管理层 | ≥70% | 5 bullets/页 | Soft & Balanced |
| `training_deck` | 学员 | ≥80% | 4 bullets/页 | Rounded & Spacious |
| `tech_review` | 技术团队 | ≥60% | 6 bullets/页 | Sharp & Compact |
| `marketing_pitch` | 客户 | ≥95% | 2 bullets/页 | Pill & Airy |

---

## 四、优先级矩阵与实施路线

### 4.1 优先级评估

| 改进项 | 影响面 | 实现复杂度 | 优先级 | 预估工期 |
|--------|-------|-----------|--------|---------|
| **C0. 修复 buildDarkTheme() 背景色覆盖** | 🔴 致命 | 🟢 低 | **P0** | 0.5天 |
| **C0.5 header 区域视觉差异化** | 🔴 致命 | 🟡 中 | **P0** | 1天 |
| C1. visual_priority 默认开启 | 🔴 高 | 🟢 低 | **P0** | 0.5天 |
| A1. 补全子类型渲染器 | 🔴 高 | 🟡 中 | **P0** | 3-5天 |
| A2. 增强子类型推断（防止类型坍缩） | 🔴 高 | 🟢 低 | **P0** | 1-2天 |
| **C3.5 改进图片搜索策略** | 🟡 严重 | 🟡 中 | **P1** | 2天 |
| A3. 收紧多样性门禁（加入 TOP-2 组合检查） | 🟡 中 | 🟢 低 | **P1** | 0.5天 |
| C2. 扩充 backdrop 库 | 🟡 中 | 🟡 中 | **P1** | 2-3天 |
| C3. 色板自动匹配 | 🟡 中 | 🟢 低 | **P1** | 1天 |
| B1. 修复 template_canvas card_id 映射 | 🟡 中 | 🟢 低 | **P1** | 1天 |
| B2. 动态卡片高度 | 🟡 中 | 🟡 中 | **P1** | 2天 |
| A4. 强制视觉锚点 | 🟡 中 | 🟢 低 | **P1** | 1天 |
| C4. 风格食谱自动选择 | 🟢 低 | 🟢 低 | **P2** | 1天 |
| B3. 溢出检测回流 | 🟡 中 | 🟡 中 | **P2** | 2天 |
| B4. 文本拆分优化 | 🟢 低 | 🟢 低 | **P2** | 1天 |
| D2. 质量评分体系 | 🟡 中 | 🟡 中 | **P2** | 3天 |
| C5. 渲染后视觉QA | 🔴 高 | 🔴 高 | **P3** | 5-7天 |
| D1. 智能路由层 | 🟡 中 | 🟡 中 | **P3** | 3-5天 |
| D3. 合同 Profile 精细化 | 🟢 低 | 🟢 低 | **P3** | 2天 |

### 4.2 实施路线图

```
Phase 1: 紧急止血 (P0, 预计 1 周) —— 解决"所有页面看起来一样"的致命问题
├── C0.  修复 buildDarkTheme() 背景色覆盖（design-tokens.mjs）
├── C0.5 header 区域差异化（让不同模板族有可辨别的 header 视觉）
├── C1.  visual_priority 默认开启（解耦 original_style）
├── A1.  补全 mixed_media / image_showcase 渲染器（addContentSlide 新增分支）
└── A2.  增强子类型推断（引入 TOP-2 回避 + blocks 分析权重提升）

Phase 2: 系统加强 (P1, 预计 1.5 周) —— 解决"图片空白、布局重复"
├── C3.5 改进图片搜索策略（搜索词从 title+narration 提取，非 block.content 标签）
├── A3.  收紧布局多样性门禁（加入 TOP-2 组合占比检查）
├── A4.  强制视觉锚点（text-only → 自动注入 KPI/icon）
├── B1.  修复 template_canvas 的 card_id 映射
├── B2.  动态卡片高度计算
├── C2.  扩充 backdrop 库（4 → 8+ 种）
└── C3.  色板自动匹配（关键词→色板规则）

Phase 3: 精细打磨 (P2, 预计 1.5 周) —— 精细化视觉品质
├── B3. 溢出检测与自动回流
├── B4. 文本拆分优化
├── C4. 风格食谱自动选择
└── D2. 质量评分体系（二值门禁 → 加权评分 + TOP-2 组合检查）

Phase 4: 架构升级 (P3, 预计 2 周, 可独立排期)
├── C5. 渲染后视觉 QA（多模态模型）
├── D1. 智能路由层（快速/标准/精细三级）
└── D3. 合同 Profile 精细化
```

---

## 五、与现有计划的关系

### 5.1 与已有补救计划的互补关系

| 已有计划 | 覆盖范围 | 本方案补充 |
|---------|---------|-----------|
| `2026-03-28-minimax-ppt-rich-visual-remediation.md` | blocks 语义模型、模板路由、文本密度、E2E 门禁 | **本方案补充**: 子类型渲染器、backdrop 扩充、色板匹配、视觉 QA |
| `2026-03-27-ppt-system-optimization.md` | bento grid、图表组件、多样性门禁、文本限制 | **本方案补充**: 子类型推断增强、动态高度、溢出回流、质量评分体系 |
| `2026-03-27-minimax-official-skill-refactor.md` | 官方 Skill 集成、适配器层、渐进式上线 | **本方案补充**: 不冲突，可在官方模式和本地模式上并行生效 |

### 5.2 不重复原则

本方案**不重复**以下已在其他计划中覆盖的工作：
- ❌ blocks 作为 source of truth（remediation Task 3）
- ❌ 语义 slide_type 保留（remediation Task 2）
- ❌ bento grid 模块引入（optimization Task 3）
- ❌ 图表/KPI 组件集成（optimization Task 4）
- ❌ 官方 Skill 适配器层（refactor Task 2）

---

## 六、度量指标与验收标准

### 6.1 关键度量

| 指标 | 当前基线 | Phase 1 目标 | Phase 2 目标 | 最终目标 |
|------|---------|-------------|-------------|---------|
| 内容子类型覆盖率 | 3/6 (50%) | 6/6 (100%) | — | 100% |
| 同一子类型最大占比 | ~60% | ≤45% | ≤35% | ≤35% |
| 视觉锚点覆盖率 | ~65% | ≥80% | ≥90% | ≥95% |
| text-only 内容页比例 | ~30% | ≤10% | 0% | 0% |
| card_id 映射成功率 | ~85% | ≥98% | 100% | 100% |
| 卡片溢出/截断率 | ~15% | ≤5% | ≤2% | 0% |
| backdrop 种类数 | 4 | 4 | ≥8 | ≥8 |
| 色板场景匹配率 | 0% | — | ≥60% | ≥80% |

### 6.2 验收方式

1. **自动化测试**：扩展现有 harness test，添加子类型覆盖率断言、视觉锚点覆盖率断言
2. **真实 fixture 验证**：用 `lingchuang` 和 `a6cf` fixture 重跑，对比前后质量指标
3. **markitdown 文本提取**：验证无乱码、无占位符、无超长重复段落
4. **人工抽检**：每个 Phase 完成后，人工评审 3-5 个生成样本

---

## 七、风险与缓解

| 风险 | 影响 | 缓解策略 |
|------|------|---------|
| 子类型渲染器引入新 bug | 已有 content 页出问题 | 每个子类型独立特性开关，可逐个上线 |
| backdrop 过多导致"花哨" | 视觉质量反而下降 | 每个 backdrop 需通过设计评审，限制透明度 |
| 色板自动匹配误判 | 话题被错误匹配到不合适色板 | 匹配结果可被 PPTPipelineRequest 显式覆盖 |
| 视觉 QA 模型调用延迟 | 生成时间变长 | Phase 1-3 不引入，仅 Phase 4 可选启用 |
| 动态高度计算导致布局异常 | 极端 case 下卡片过小 | 设置 min_card_height 下限，异常时降级为固定高度 |

---

## 八、附录：调研报告可直接复用的概念

| 调研报告概念 | 本方案采纳方式 |
|-------------|--------------|
| 三模式路由（A/B/C） | 简化为三级管线（快速/标准/精细），不需要模板向量库 |
| 元数据过滤+向量检索 | 暂不引入向量库，用关键词+评分覆盖 80% 场景 |
| 差异编辑计划（JSON） | 暂不引入，保留全量生成模式；未来可在"模板+微调"场景中引入 |
| 多维质量评分 | 采纳评分维度和权重设计，替换当前二值门禁 |
| 渲染后视觉QA | 采纳概念，在 Phase 4 引入截图+多模态评估 |
| 回退阈值 | 采纳总分 < 60 和单项 < 40 的回退策略 |
| 合同 Profile 精细化 | 采纳分场景 Profile 设计，扩展到 5+ 种 |
