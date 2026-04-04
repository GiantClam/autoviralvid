# PPT 生成质量优化重构方案

> **文档元信息**
> - **目的**：融合 ppt-master、MiniMax 与 Anthropic 的先进架构模式，彻底解决当前系统在视觉多样性、渲染灵活性及生成效率上的瓶颈。
> - **范围**：涵盖从内容规划、设计决策到双轨渲染及视觉 QA 的全链路重构。
> - **日期**：2026-03-29
> - **关联文档**：`ppt_service.py`, `ppt_planning.py`, `ppt_quality_gate.py`, `generate-pptx-minimax.mjs`, `card-renderers.mjs`, `template-renderers.mjs`, `design-tokens.mjs`, `template-catalog.json`, `template-registry.mjs`, `ppt_retry_orchestrator.py`, `pptx_engine.py`, `pptx_rasterizer.py`, `ppt_visual_qa.py`

---

## 一、目标架构

### 1.1 设计原则

1.  **双轨渲染架构**：以 PptxGenJS API 为主路径确保可编辑性，以 SVG 到 custGeom 为辅路径实现复杂可视化，在规划阶段动态决定每页的渲染路径。
2.  **直接复用成熟 Skill**：优先调用已安装的 MiniMax 与 Anthropic 子 Skill，避免在基础设计决策和 XML 编辑上重复造轮子。
3.  **三级降级策略**：建立从规划路由到跨路径兜底，再到 PNG 栅格化嵌入的完整保底机制，确保任何情况下都有高质量产出。
4.  **架构平滑增强**：保留现有的 Python 到 Node.js 通讯管线，通过模块化重构实现 per-slide 的并行生成与独立重试。
5.  **视觉节奏优先**：将视觉密度交替和多样性检查提升为一等公民，从规划层强制执行呼吸感和节奏感。

### 1.2 六层架构总览

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 0: 路由层                                              │
│  ├── 有模板 .pptx → 模板编辑路径                             │
│  └── 无模板     → 从零生成路径（双轨渲染）                     │
└──────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────┐
│  Layer 1: 设计决策（直接调用 Skill）                          │
│  ├── color-font-skill  → 选色板 + 字体                        │
│  ├── design-style-skill → 选风格（Sharp, Soft, Rounded, Pill）│
│  └── 输出: design_spec 对象                                   │
└──────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────┐
│  Layer 2: 内容策略 + 编排 + 路由决策                           │
│  ├── 页面类型分类（5 类 + 6 子类型）                          │
│  ├── 视觉密度标注 + 节奏控制                                  │
│  ├── 内容策略（断言式标题, SCQA）                             │
│  ├── 多样性预检（TOP-2 + ABAB 检测）                          │
│  ├── 渲染路径路由（每页标注 render_path）                     │
│  └── 输出: slide_plan[]                                       │
└──────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────────┐
│  PptxGenJS API 路径      │     │  SVG → custGeom 路径         │
│  (~85% 页面)             │     │  (~15% 页面)                 │
│  ├── 文本框/标题/正文     │     │  ├── AI 生成整页 SVG         │
│  ├── 预设形状（180+种）   │     │  ├── 解析 SVG 元素           │
│  ├── 原生图表（7种）      │     │  ├── 形状 → custGeom points  │
│  ├── 表格               │     │  ├── 文本 → addText()（原生） │
│  └── 标准布局            │     │  └── 图片 → addImage()       │
└─────────────────────────┘     └─────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────┐
│  Layer 3: 并行 Slide 生成                                     │
│  ├── 每页派生一个 typed subagent                              │
│  ├── 每个 subagent 使用 slide-making-skill 生成 slide-XX.js   │
│  ├── 最多 5 个并行任务                                        │
│  └── 输出: slides/slide-01.js 到 slide-N.js                  │
└──────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────┐
│  Layer 4: 编译 + 后处理                                        │
│  └── compile.js 合并所有 slide 到 presentation.pptx            │
└──────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────┐
│  Layer 5: 三层 QA                                             │
│  ├── 文本 QA: markitdown                                      │
│  ├── 结构 QA: ppt_quality_gate.py                             │
│  ├── 视觉 QA: pptx_rasterizer → 多模态审查                    │
│  └── 失败 → 单页重试（三级降级策略）                            │
└──────────────────────────────────────────────────────────────┘
```

### 1.3 双轨渲染路径

| 特性 | PptxGenJS API 路径 | SVG → custGeom 路径 |
| :--- | :--- | :--- |
| **适用场景** | 标准内容页, 列表, 简单图表, 表格 | 流程图, 架构图, 复杂信息图, 非标图表 |
| **核心优势** | 100% 原生可编辑, 自动换行, 兼容性极佳 | 布局自由度极高, 视觉表现力强 |
| **实现方式** | 调用 PptxGenJS 结构化 API | AI 生成 SVG, 解析后映射到 custGeom 路径 |
| **文本处理** | 原生文本框, 支持段落样式 | 映射为原生 addText(), 确保可编辑 |
| **典型占比** | 约 85% | 约 15% |

### 1.4 三级降级策略

| 级别 | 触发条件 | 行为描述 | 预期覆盖率 |
| :--- | :--- | :--- | :--- |
| **Level 1: 规划路由** | 初始规划阶段 | 根据内容子类型自动选择最优渲染路径 | ~90% |
| **Level 2: 跨路径兜底** | PptxGenJS 重试多次仍失败 | 切换到 SVG 路径重新生成整页布局 | ~8% |
| **Level 3: PNG 终极兜底** | SVG 混合渲染也失败 | 将 SVG 通过 sharp 栅格化为 PNG 嵌入 | ~2% |

---

## 二、技术背景与关键发现

### 2.1 四方 Skill 全景对比

| 维度 | ppt-master | MiniMax pptx-generator | MiniMax pptx-plugin | Anthropic pptx |
| :--- | :--- | :--- | :--- | :--- |
| **技术栈** | Python, SVG, OOXML | PptxGenJS (Node.js) | PptxGenJS, 5 agents | PptxGenJS, XML editing |
| **渲染路径** | AI → SVG → DrawingML | AI → JS per-slide → compile | AI → subagent → compile | PptxGenJS 或 XML editing |
| **设计系统** | design_spec.md 13 章 | 18 色板, 4 风格配方 | 5 独立 Skill 组合 | 10 色板, 字体配对 |
| **模板/图表** | 20 模板, 33 图表 | 5 页面类型, 7 图表 | 同左, 6 内容子类型 | 设计指南, 布局模式 |
| **图标** | 640+ SVG 图标 | 无 | 无 | react-icons → PNG |
| **并行生成** | 严格串行 | 最多 5 subagent | 5 typed subagent | subagent 并行编辑 |
| **模板编辑** | 仅从零生成 | 基础 XML 参考 | ppt-editing-skill | unpack, edit, pack 流程 |
| **QA** | 人工确认 | markitdown 文本 QA | markitdown + fix-verify | 视觉 QA (PDF → 图片 → 多模态) |

### 2.2 ppt-master SVG → DrawingML 转换器实现分析

ppt-master 的 SVG → OOXML 转换器是其核心资产，总计约 2,700 行 Python 代码：

| 模块 | 行数 | 职责描述 |
| :--- | :--- | :--- |
| `drawingml_converter.py` | 269 | 总调度器, 处理 group 元素, 将 SVG 转换为 slide XML |
| `drawingml_elements.py` | 848 | 基础元素转换（矩形, 圆形, 路径, 文本, 图像等） |
| `drawingml_styles.py` | 359 | 处理填充, 描边, 渐变, 阴影, 透明度等样式映射 |
| `drawingml_paths.py` | 429 | 核心模块, 解析 SVG path 并生成 DrawingML 路径命令 |
| `drawingml_utils.py` | 310 | 坐标系转换, 颜色解析, 字体宽度估算工具 |
| `drawingml_context.py` | 102 | 转换状态管理 |

**SVG → DrawingML 路径命令映射**：

| SVG 命令 | DrawingML 元素 | 支持状态 |
| :--- | :--- | :--- |
| `M` (moveTo) | `<a:moveTo>` | ✅ |
| `L` (lineTo) | `<a:lnTo>` | ✅ |
| `C` (cubic Bezier) | `<a:cubicBezTo>` | ✅ |
| `Q` (quadratic Bezier) | `<a:quadBezTo>` | ✅ |
| `A` (arc) | `<a:arcTo>` | ✅ (需端点到中心参数化转换) |
| `Z` (close) | `<a:close>` | ✅ |

**已知限制**：
- 文本使用 `wrap="none"` + `spAutoFit`（自动缩放，不自动换行）。
- `estimate_text_width()` 是粗糙的字符宽度估算，不精确。
- 不支持 clipPath, mask, textPath, animate, 外部 CSS。
- 外部依赖仅 python-pptx (>=0.6.21)。

### 2.3 关键发现：PptxGenJS 已支持 custGeom

当前项目使用的 PptxGenJS ^3.12.0，该版本自 v3.7.0 起已原生支持 `custGeom`（自定义几何图形/freeform）：
- 提供了完整的 DrawingML 路径命令支持：moveTo, lnTo, arcTo, cubicBezTo, quadBezTo, close。
- 与 SVG path 命令存在 1:1 的映射逻辑。
- 可利用 `svg-points` 等 npm 包解析 SVG 的 `d` 属性。
- 弧线端点到中心参数化转换的 JavaScript 实现已成熟。
- **结论**：这意味着 SVG 到 DrawingML 的转换可以完全在 Node.js 侧完成，无需引入 ppt-master 的 Python 转换器。

### 2.4 当前系统差距分析

| 能力维度 | 当前系统实现 | 行业最佳实践 | 差距等级 | 改进优先级 |
| :--- | :--- | :--- | :--- | :--- |
| **渲染架构** | 单体 JSON 到 PptxGenJS | 双轨路由（API + SVG 转换） | 🔴 大 | **P0** |
| **并行生成** | 串行单体脚本 | per-slide subagent 并行 | 🔴 大 | **P0** |
| **模板丰富度** | 7 模板渲染器 | 20+ 核心模板 + 33 种图表 | 🔴 大 | **P0** |
| **图标系统** | 无 | react-icons 4000+ 矢量图标 | 🔴 大 | **P1** |
| **设计规范** | 分散的常量定义 | 统一的 design_spec 对象 | 🟡 中 | **P1** |
| **模板编辑** | 不支持 | unpack, XML edit, pack 流程 | 🟡 中 | **P1** |
| **视觉 QA** | 结构化门禁 | 多模态视觉闭环审查 | 🟡 中 | **P1** |
| **视觉节奏** | 仅类型占比检查 | 密度交替与呼吸页控制 | 🟡 中 | **P1** |
| **内容策略** | 无（直接生成） | SCQA/金字塔原理 | 🟡 中 | **P2** |
| **风格体系** | 4 视觉预设 | 3 级风格体系 (General/Consulting/Top) | 🟡 中 | **P2** |

### 2.5 当前系统优势（应保留）

1.  **三级自动重试**：具备 deck, slide, block 级别的精细化重试机制，远超开源方案。
2.  **全自动管线**：无需人工干预，完全适配 API 调用场景。
3.  **模板评分路由**：基于 8 维评分矩阵自动选择最优模板。
4.  **流式生成支持**：前端体验更佳，支持实时进度反馈。
5.  **Serper 图片集成**：具备真实图片搜索与注入能力。

---

## 三、15 个重构策略

### 策略 S1：统一设计规范对象（借鉴 ppt-master design_spec.md）

#### 问题
当前设计 token 分散在 `PALETTES`, `STYLE_RECIPES`, `FONT_BY_STYLE` 等多处，导致视觉风格难以全局统一，且难以适配不同主题。

#### 方案
在 Python 侧生成统一的 `design_spec` 对象，作为管线的"视觉合同"全程传递。该对象兼容 MiniMax Theme Object Contract，包含色彩, 排版, 间距及视觉风格定义。

```jsonc
{
  "design_spec": {
    "colors": {
      "primary": "22223b",    // MiniMax theme.primary
      "secondary": "4a4e69",  // MiniMax theme.secondary
      "accent": "9a8c98",     // MiniMax theme.accent
      "light": "c9ada7",      // MiniMax theme.light
      "bg": "f2e9e4",         // MiniMax theme.bg
      "text_primary": "F8FAFC",
      "text_secondary": "CBD5E1",
      "success": "22C55E",
      "warning": "EF4444"
    },
    "typography": {
      "title_font": "Microsoft YaHei",
      "body_font": "Arial",
      "title_size": 26,
      "body_size": 15,
      "caption_size": 11
    },
    "spacing": {
      "page_margin": 0.45,
      "card_gap": 0.2,
      "card_radius": 0.1,
      "header_height": 0.68
    },
    "visual": {
      "style_recipe": "soft",   // Sharp / Soft / Rounded / Pill
      "backdrop_type": "high-contrast",
      "visual_priority": true,
      "icon_style": "outlined"
    }
  }
}
```

#### 集成点
- `ppt_service.py`: `_apply_visual_orchestration()` 生成该对象。
- `generate-pptx-minimax.mjs`: 入口处解析并替代硬编码常量。
- **可直接用 Skill**：`color-font-skill` 选色板 + `design-style-skill` 选风格。

---

### 策略 S2：引入图表模板库（借鉴 ppt-master 33 种图表）

#### 问题
当前仅支持基础的数据条，无法满足专业演示中对饼图, 折线图, 雷达图等多样化图表的需求。

#### 方案
分阶段引入图表支持：
1.  **Phase 1**: 封装 PptxGenJS 原生图表 API，支持 7 种标准图表（BAR, LINE, PIE, DOUGHNUT, AREA, SCATTER, RADAR）。
2.  **Phase 2**: 针对漏斗图, 瀑布图等非标图表，走 SVG 到 custGeom 路径。利用 `svg-points` 解析 SVG 路径并映射为 PptxGenJS points。

```javascript
const CHART_TYPE_MAP = {
  bar:        pptxgen.charts.BAR,
  line:       pptxgen.charts.LINE,
  pie:        pptxgen.charts.PIE,
  doughnut:   pptxgen.charts.DOUGHNUT,
  area:       pptxgen.charts.AREA,
  scatter:    pptxgen.charts.SCATTER,
  radar:      pptxgen.charts.RADAR,
};
```

#### 集成点
- `card-renderers.mjs`: 扩展 `renderChartCard`。
- `ppt_service.py`: 在内容合同中增加 `chart_type` 推断逻辑。
- 新建 `scripts/minimax/svg-chart-converter.mjs` 处理非标图表。

---

### 策略 S3：图标系统 react-icons（采用 Anthropic 方案）

#### 问题
Unicode emoji 在不同平台渲染不一，且数量极少，缺乏专业感。

#### 方案
采用 Anthropic 的方案，集成 `react-icons`。通过 sharp 将矢量图标栅格化为高保真 PNG 嵌入。这种方式确保了跨平台的一致性，并允许精确控制图标颜色。

```javascript
import { FiTrendingUp, FiTarget, FiUsers } from 'react-icons/fi';
import sharp from 'sharp';

async function renderIcon(IconComponent, size = 48, color = '#4A4E69') {
  const svgString = renderToStaticMarkup(<IconComponent size={size} color={color} />);
  const pngBuffer = await sharp(Buffer.from(svgString)).png().toBuffer();
  return `data:image/png;base64,${pngBuffer.toString('base64')}`;
}
```

**图标映射表**（基于 Feather Icons）：
```javascript
const ICON_MAP = {
  growth: 'FiTrendingUp', trend: 'FiBarChart2', target: 'FiTarget',
  idea: 'FiZap', check: 'FiCheckCircle', warning: 'FiAlertTriangle',
  clock: 'FiClock', money: 'FiDollarSign', team: 'FiUsers',
  code: 'FiCode', cloud: 'FiCloud', security: 'FiShield',
  api: 'FiLink', database: 'FiDatabase', rocket: 'FiSend',
  handshake: 'FiHeart', chart: 'FiPieChart', building: 'FiBriefcase',
  globe: 'FiGlobe', medal: 'FiAward', settings: 'FiSettings',
};
```

#### 集成点
- 新建 `scripts/minimax/icon-renderer.mjs`。
- `card-renderers.mjs`: 新增 `renderIconBadge()`。

---

### 策略 S4：视觉节奏控制（借鉴 ppt-master 密度交替）

#### 问题
连续的高密度页面（如全是 4 格矩阵）会导致观众视觉疲劳，缺乏演示节奏。

#### 方案
在 Python 侧 `ppt_planning.py` 的 `enforce_layout_diversity()` 中引入密度节奏引擎。通过 `DENSITY_MAP` 标注每个布局的密度等级，并强制执行交替规则。

```python
DENSITY_MAP = {
    "grid_4": "high",    "bento_5": "high",   "bento_6": "high",
    "grid_3": "medium",  "split_2": "medium",  "asymmetric_2": "medium",
    "timeline": "medium",
    "hero_1": "low",     "section": "breathing",
    "cover": "breathing", "summary": "breathing",
}

def enforce_density_rhythm(layouts: list) -> list:
    """确保视觉密度交替，避免连续高密度"""
    result = list(layouts)
    consecutive_high = 0
    pages_since_breathing = 0
    for i, layout in enumerate(result):
        density = DENSITY_MAP.get(layout, "medium")
        if density == "high":
            consecutive_high += 1
        else:
            consecutive_high = 0
        if density != "breathing":
            pages_since_breathing += 1
        else:
            pages_since_breathing = 0
        if consecutive_high >= 3:
            result[i] = _downgrade_density(layout)
            consecutive_high = 0
        if pages_since_breathing >= 5 and i < len(result) - 2:
            result.insert(i + 1, "section")
            pages_since_breathing = 0
    return result

def _downgrade_density(layout: str) -> str:
    """降级高密度布局"""
    downgrade_map = {
        "grid_4": "grid_3",
        "bento_6": "split_2",
        "bento_5": "asymmetric_2"
    }
    return downgrade_map.get(layout, "grid_3")
```

#### 集成点
- `ppt_planning.py`: `enforce_layout_diversity()`。
- `ppt_quality_gate.py`: `validate_layout_diversity()`。

---

### 策略 S5：扩展模板渲染器（从 7 → 12+）

#### 问题
现有的 7 个模板渲染器覆盖面不足，导致大量页面回退到通用的 grid 布局。

#### 方案
新增 5 个专业级模板渲染器，提升视觉表现力。每个模板需包含渲染函数, 核心能力, 主题约束及评分规则。

1.  **kpi_dashboard_dark**:
    - **视觉风格**: 深色背景，霓虹色强调。
    - **布局特征**: 4 到 6 个带趋势线的 KPI 卡片。
    - **要求**: 需实现 `renderKpiDashboard` 函数，支持数据趋势标注。
    - **能力**: 自动处理数值缩放与单位显示。
    - **主题**: 强制使用 Dark Theme。
    - **评分规则**: 当内容包含 4 个以上数值指标且包含时间维度时触发。
2.  **image_showcase_light**:
    - **视觉风格**: 极简白色，大留白。
    - **布局特征**: 1 大 2 小图片组合，带悬浮文字说明。
    - **要求**: 具备图片视觉优先级排序能力。
    - **能力**: 自动裁剪图片以适配比例。
    - **主题**: 强制使用 Light Theme。
    - **评分规则**: 当内容包含 3 张以上图片且文字量较少时触发。
3.  **process_flow_dark**:
    - **视觉风格**: 渐变连接线，发光节点。
    - **布局特征**: 横向或纵向 4 步流程。
    - **要求**: 自动计算连接线坐标。
    - **能力**: 支持步骤状态标注（已完成, 进行中, 待开始）。
    - **主题**: 强制使用 Dark Theme。
    - **评分规则**: 当内容包含明确的步骤或阶段描述时触发。
4.  **comparison_cards_light**:
    - **视觉风格**: 柔和阴影，清晰边界。
    - **布局特征**: 2 到 3 个并排对比卡片，带勾选图标。
    - **要求**: 自动对齐对比项。
    - **能力**: 自动提取对比维度。
    - **主题**: 强制使用 Light Theme。
    - **评分规则**: 当内容包含"对比", "优势", "差异"等关键词时触发。
5.  **quote_hero_dark**:
    - **视觉风格**: 巨型排版，半透明背景图。
    - **布局特征**: 居中金句 + 作者信息。
    - **要求**: 自动计算文字层级。
    - **能力**: 自动选择高对比度字体颜色。
    - **主题**: 强制使用 Dark Theme。
    - **评分规则**: 当内容为单句核心观点或引用时触发。

**注意**：在双轨架构下，上述模板仅适用于 PptxGenJS 路径。SVG 路径页面采用 AI 自由布局。

#### 集成点
- `template-renderers.mjs`: 注册新渲染器。
- `template-catalog.json`: 更新评分规则。

---

### 策略 S6：内容策略层 SCQA（借鉴 ppt-master 金字塔原理）

#### 问题
当前生成的内容往往是事实的堆砌，缺乏说服力和逻辑结构。

#### 方案
引入 SCQA（情境, 冲突, 问题, 答案）框架，并强制执行断言式标题。通过 LLM Prompt 增强，引导模型生成具有洞察力的标题。

**Prompt 增强示例**:
- ❌ 标题: "市场分析"
- ✅ 标题: "目标市场规模达 500 亿，年复合增长率超 20%"
- ❌ 标题: "产品特性"
- ✅ 标题: "三项核心技术突破，将渲染效率提升 300%"

**SlideContentStrategy 数据类**:
```python
class SlideContentStrategy:
    assertion: str        # 核心论点（应作为标题）
    evidence: list[str]   # 支撑论据列表
    data_anchor: str      # 数据锚点
    page_role: str        # 页面角色 (argument, evidence, transition, summary)
    density_hint: str     # 密度建议 (high, medium, low, breathing)
    render_path: str      # 渲染路径决策 ("pptxgenjs" | "svg")
```

#### 集成点
- `ppt_planning.py`: 在大纲生成阶段注入策略。
- `ppt_service.py`: 确保内容合同包含策略字段。

---

### 策略 S7：图片策略优化

#### 问题
图片搜索关键词过于宽泛，导致搜索结果不相关或加载失败。

#### 方案
建立五级图片来源优先级，并优化搜索词生成逻辑。

**五级图片来源优先级**:
1.  **用户提供的 URL**: 绝对优先。
2.  **AI 生成的矢量 SVG**: 针对图示类需求。
3.  **Serper 搜索**: 针对实景类需求，使用改进后的关键词。
4.  **图标 + 彩色背景组合**: 针对抽象概念。
5.  **品牌占位图**: 最终兜底。

**搜索词优化**:
不再直接使用 `block.content` 的语义标签，而是结合 `slide.title` 与 `topic entity` 提取关键词。
- 原始: "效率提升"
- 优化: "high speed rocket launch professional photography"

#### 集成点
- `ppt_service.py`: `_hydrate_image_assets()` 与新函数 `_build_image_search_query()`。

---

### 策略 S8：多样性门禁增强（TOP-2 组合 + ABAB 检测）

#### 问题
虽然有布局多样性检查，但仍会出现局部重复（如 ABAB 模式）或某种布局占比过高的情况。

#### 方案
新增两项核心检查指标：
1.  **TOP-2 组合占比**: 出现频率最高的两种布局组合占比必须 <= 65%。
2.  **ABAB 模式检测**: 禁止出现连续 4 页及以上的交替重复（如 grid_3 → quote_stat → grid_3 → quote_stat）。

#### 集成点
- `ppt_quality_gate.py`: `validate_layout_diversity()`。

---

### 策略 S9：密度节奏引擎

#### 问题
缺乏全局的视觉密度管理，导致演示文稿整体感官不平衡。

#### 方案
建立全局密度映射表并执行强制规则。

**DENSITY_MAP 表**:
| 密度等级 | 对应布局 |
| :--- | :--- |
| **High** | grid_4, bento_5, bento_6 |
| **Medium** | grid_3, split_2, asymmetric_2, timeline |
| **Low** | hero_1 |
| **Breathing** | section, cover, summary |

**强制规则**:
- 禁止连续 3 页高密度布局。
- 每 5 页内容必须包含至少 1 页 Breathing 或 Low 密度页面。
- **降级策略**: 当检测到密度冲突时，自动执行降级：grid_4 → grid_3, bento_6 → split_2。

#### 集成点
- `ppt_planning.py`: `enforce_layout_diversity()`。

---

### 策略 S10：子 Agent 并行生成模式（来自 MiniMax plugin + Anthropic）

#### 问题
当前管线是串行单体：Python 一次性生成全部 slide 的 JSON，传给一个 Node.js 脚本渲染全部。单页失败需要重跑整个任务。

#### 方案
采用 per-slide 模式，为每页派生独立的 subagent，生成独立的 `slide-XX.js` 模块，最后通过 `compile.js` 合并。

```
ppt-orchestra-skill 规划大纲
    ↓
并行派生最多 5 个 typed subagent：
  ├── cover-page-generator    → slide-01.js
  ├── content-page-generator  → slide-02.js ~ slide-N-1.js
  ├── section-divider-generator → 插入位
  └── summary-page-generator  → slide-N.js
    ↓
compile.js 合并所有 slide → presentation.pptx
```

每个 slide JS 文件是独立可运行的模块：
```javascript
// slide-XX.js
function createSlide(pres, theme) {
  const slide = pres.addSlide();
  // ... 渲染逻辑
  return slide;
}
module.exports = { createSlide, slideConfig };
```

#### 集成点
- 重构 `generate-pptx-minimax.mjs` 为模块化结构。
- `ppt_retry_orchestrator.py`: 实现 slide 级别的独立重生成。

---

### 策略 S11：模板编辑双轨路由（来自 Anthropic + MiniMax）

#### 问题
当前系统只支持从零生成，不支持在用户提供的 .pptx 模板上填充内容。

#### 方案
引入 unpack, XML edit, pack 流程。当检测到用户上传模板时，自动切换到模板编辑路径。

```
用户上传 .pptx 模板
  ↓
markitdown 提取文本（分析模板结构）
  ↓
unpack.py（解压为 slide XML 文件）
  ↓
逐页 XML 编辑（替换文本/图片占位符）
  ↓
clean.py（清理孤立资源）
  ↓
pack.py（重新打包为 .pptx）
```

#### 集成点
- `ppt_routes.py`: 新增路由分发逻辑。
- `pptx_engine.py`: 增强 XML 占位符替换能力。

---

### 策略 S12：视觉 QA 闭环（来自 Anthropic）

#### 问题
结构化检查无法发现视觉上的重叠, 对比度不足或文字溢出。

#### 方案
集成多模态模型进行视觉审查。

```
Layer A: 文本 QA（markitdown）
  ├── 内容完整性：所有计划的 assertion/evidence 都出现
  ├── 占位符检测：grep "xxxx|lorem|ipsum|placeholder"
  └── 页码正确性：page number badge 连续

Layer B: 结构 QA（现有 ppt_quality_gate.py）
  ├── 布局多样性（TOP-2、ABAB 检测）
  ├── 密度节奏检查
  └── 空白页/溢出检测

Layer C: 视觉 QA（增强 ppt_visual_qa.py）
  ├── pptx_rasterizer.py → 逐页截图
  ├── 多模态模型审查：对齐, 对比度, 文字可读性
  └── 发现问题 → 单页重试（通过 S10 的 per-slide 机制）
```

#### 集成点
- `ppt_visual_qa.py`: 增加 markitdown 文本检查与多模态视觉反馈。
- `ppt_retry_orchestrator.py`: QA 反馈驱动单页重试。

---

### 策略 S13：Skill 组合复用

#### 问题
已安装的多个专业 Skill 处于闲置状态，导致重复开发。

#### 方案
在 subagent 的 prompt 中通过 `load_skills` 显式注入对应能力。

| 策略 | 可直接用的 Skill | 替代的自建代码 |
| :--- | :--- | :--- |
| S1 (design_spec) | `color-font-skill` + `design-style-skill` | 替代手动从 PALETTES 选择 |
| S2 (图表) | `slide-making-skill` 的 API 参考 | 替代自研图表渲染器 |
| S3 (图标) | `pptx` (Anthropic) 的 react-icons 方案 | 替代 Unicode emoji |
| S10 (并行生成) | `ppt-orchestra-skill` 规划 | 替代单体 Node.js 脚本 |
| S11 (模板编辑) | `ppt-editing-skill` | 替代自研 XML 编辑流程 |

#### 集成点
- 优化 subagent 的系统提示词。

---

### 策略 S14：双轨渲染架构（SVG → DrawingML）

#### 问题
单一渲染路径无法兼顾"标准页面的可编辑性"与"复杂页面的表现力"。

#### 方案
实现 SVG 到 DrawingML 的混合渲染器。AI 用 SVG 描述布局，代码将简单形状映射为 AutoShape，复杂路径映射为 custGeom，文本映射为原生 addText。

**渲染路径路由规则**:
| 页面类型 | 推荐路径 | 理由 |
| :--- | :--- | :--- |
| Cover / TOC / Summary | PptxGenJS | 标准布局，文字处理能力强 |
| Content: 纯文本/表格 | PptxGenJS | 自动换行与原生表格支持 |
| **Content: 流程图/时间线** | **SVG** | 连接线与非标形状排列 |
| **Content: 架构图/关系图** | **SVG** | 自由布局与大量连线 |
| **Content: 信息图/仪表盘** | **SVG** | 高密度精确定位 |
| **Content: SWOT/矩阵类** | **SVG** | 2×2 网格 + 内部元素自由排布 |
| **Content: 漏斗/桑基/瀑布** | **SVG** | 非标图表形状 |

**混合渲染器代码示例**:
```javascript
function renderSlideFromSvg(slide, svgString, designSpec) {
  const elements = parseSvg(svgString);
  for (const el of elements) {
    switch (el.type) {
      case 'rect':
        // 简单矩形 → 预设形状
        slide.addShape(pres.ShapeType.rect, {
          x: toInches(el.x), y: toInches(el.y),
          w: toInches(el.width), h: toInches(el.height),
          fill: { color: el.fill }, rectRadius: el.rx ? toInches(el.rx) : undefined,
        });
        break;
      case 'text':
        // 文本 → 原生文本框（保持可编辑 + 自动换行）
        slide.addText(el.content, {
          x: toInches(el.x), y: toInches(el.y),
          w: toInches(el.estimatedWidth), h: toInches(el.estimatedHeight),
          fontFace: designSpec.typography.body_font,
          fontSize: el.fontSize, color: el.fill
        });
        break;
      case 'path':
        // 复杂路径 → custGeom（矢量可编辑）
        slide.addShape({ points: svgPathToPoints(el.d), fill: { color: el.fill } });
        break;
      case 'circle': case 'ellipse':
        slide.addShape(pres.ShapeType.ellipse, { /* ... */ });
        break;
      case 'line':
        slide.addShape(pres.ShapeType.line, { /* ... */ });
        break;
    }
  }
}
```

#### 集成点
- 新建 `scripts/minimax/svg-slide-renderer.mjs`。
- 依赖：`svg-points` npm 包。

---

### 策略 S15：三级降级策略

#### 问题
生成过程中的不确定性可能导致部分页面渲染失败。

#### 方案
建立三级保底机制。

```
Layer 2 规划时：为每页选择最优路径（pptxgenjs / svg）
     │
     ├── pptxgenjs 路径 → 生成 slide-XX.js → 标准重试
     │       └── 重试耗尽仍失败 → 切换到 SVG 路径（第二级降级）
     │
     └── svg 路径 → AI 生成 SVG → 混合渲染 → 标准重试
             └── 重试耗尽仍失败 → 降级为 SVG→PNG（终极兜底）
```

**三级降级表**:
| 级别 | 触发条件 | 行为 | 覆盖率 |
| :--- | :--- | :--- | :--- |
| **Level 1: 规划路由** | 规划阶段 | 每页选择最优渲染路径 | ~90% |
| **Level 2: 跨路径兜底** | PptxGenJS 重试 N 次仍失败 | 切换到 SVG 路径重新生成 | ~8% |
| **Level 3: PNG 终极兜底** | SVG 混合渲染也失败 | SVG 栅格化为 PNG 嵌入 | ~2% |

#### 集成点
- `ppt_retry_orchestrator.py`: 完善降级逻辑。

---

## 四、实施路线图

### 4.1 分阶段计划

**Phase 1: 架构基石与紧急修复 (Week 1-2)**
- **视觉修复**: 修复 `buildDarkTheme` 背景色覆盖问题，确保深色模式视觉正确。
- **Header 增强**: 实现 header 区域差异化渲染，提升页面层级感。
- **默认配置**: 开启 `visual_priority` 默认配置，优先保证视觉质量。
- **渲染器补全**: 补全 `mixed_media` 与 `image_showcase` 渲染器。
- **智能推断**: 增强子类型推断逻辑，自动识别内容特征。
- **核心重构**: 实现 `design_spec` 统一设计规范对象。
- **并行框架**: 完成 per-slide JS 模块化重构与并行生成框架。
- **路由部署**: 部署双轨渲染路由逻辑。
- **门禁实施**: 实施视觉节奏控制与 TOP-2 多样性门禁。

**Phase 2: 渲染增强与 QA 闭环 (Week 3-4)**
- **混合渲染**: 实现 SVG 到 custGeom 的混合渲染器。
- **图表扩展**: 扩展 PptxGenJS 原生图表支持。
- **图标系统**: 上线 `react-icons` 图标系统，替代 Unicode emoji。
- **文本 QA**: 建立基于 markitdown 的文本 QA 流程。
- **图片优化**: 优化图片搜索关键词生成算法。

**Phase 3: 能力扩展与降级闭环 (Week 5-6)**
- **非标图表**: 支持 SVG 路径下的非标图表渲染。
- **模板扩展**: 新增 5 个专业模板渲染器。
- **策略注入**: 注入 SCQA 内容策略层。
- **模板编辑**: 实现 .pptx 模板编辑路径。
- **降级闭环**: 完成三级降级策略的闭环。

**Phase 4: 持续优化与智能路由 (Week 7+)**
- **视觉 QA**: 引入多模态模型进行全量视觉 QA。
- **智能推断**: 实现图表类型的智能自动推断。
- **动态路由**: 基于生成历史成功率动态调整路由权重。

### 4.2 优先级矩阵

| 策略 | 来源 | 影响面 | 复杂度 | 优先级 | 工期 | 依赖 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| S1. 统一设计规范 | 综合 | 🔴 高 | 🟢 低 | **P0** | 2d | 无 |
| S10. 并行生成 | 综合 | 🔴 高 | 🟡 中 | **P0** | 3d | 无 |
| S14. 双轨路由框架 | 综合 | 🔴 高 | 🟡 中 | **P0** | 2d | S10 |
| S4. 视觉节奏控制 | ppt-master | 🟡 中 | 🟢 低 | **P1** | 1d | 无 |
| S8. TOP-2 门禁 | 综合 | 🟡 中 | 🟢 低 | **P1** | 0.5d | 无 |
| S14. SVG 渲染器 | 综合 | 🔴 高 | 🔴 高 | **P1** | 4d | S14 框架 |
| S3. react-icons | Anthropic | 🟡 中 | 🟢 低 | **P1** | 1d | 无 |
| S12. 视觉 QA | Anthropic | 🟡 中 | 🟡 中 | **P1** | 2d | 无 |
| S7. 图片搜索词优化 | 综合 | 🟡 中 | 🟢 低 | **P1** | 1d | 无 |
| S5. 扩展模板渲染器 | 综合 | 🔴 高 | 🔴 高 | **P1** | 5d | S1 |
| S6. 内容策略层 | ppt-master | 🟡 中 | 🟡 中 | **P2** | 3d | 无 |
| S11. 模板编辑路径 | 综合 | 🟡 中 | 🟡 中 | **P2** | 3d | 无 |
| S13. Skill 组合复用 | 综合 | 🟡 中 | 🟢 低 | **P2** | 1d | S10 |
| S15. 三级降级策略 | 综合 | 🟡 中 | 🟡 中 | **P2** | 2d | S14 |
| S9. 密度节奏引擎 | ppt-master | 🟡 中 | 🟡 中 | **P2** | 2d | S4 |

### 4.3 质量验收标准

| 指标 | 初始基线 | Phase 1 | Phase 2 | Phase 3 | 最终目标 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 模板视觉差异度 | ~2 种 | >= 5 种 | >= 8 种 | >= 12 种 | >= 12 种 |
| 图表类型覆盖 | 1 种 | >= 4 种 | >= 8 种 | >= 12 种 | >= 15 种 |
| 视觉锚点覆盖率 | ~65% | >= 75% | >= 90% | >= 95% | >= 95% |
| TOP-2 布局占比 | 75% | <= 65% | <= 60% | <= 55% | <= 55% |
| 连续高密度页上限 | 无限制 | <= 3 | <= 2 | <= 2 | <= 2 |
| 图片加载成功率 | ~40% | >= 60% | >= 80% | >= 90% | >= 90% |
| SVG 路径页面占比 | 0% | 0% | >= 10% | >= 15% | ~15% |
| 单页重试成功率 | N/A | >= 80% | >= 90% | >= 95% | >= 95% |
| 图标为真实矢量比例 | 0% | 0% | >= 80% | >= 95% | >= 95% |

---

## 五、风险与缓解

| 风险描述 | 潜在影响 | 缓解策略 |
| :--- | :--- | :--- |
| 双轨渲染增加系统复杂度 | 维护成本上升, 调试困难 | 采用模块化设计, 确保两条路径可独立开关与测试。 |
| SVG 转换精度不足 | 复杂图形渲染变形 | 实施 Level 3 PNG 兜底机制, 确保始终有视觉产出。 |
| 文本在 SVG 路径中溢出 | 文字截断, 影响阅读 | 文本始终强制走原生 addText() API, 不参与矢量路径转换。 |
| AI 生成 SVG 质量不稳定 | 布局混乱 | 在 Prompt 中严格限制支持的 SVG 元素子集, 禁用复杂特性。 |
| react-icons 依赖增加 | 构建时间增长 | 仅按需引入特定的图标子库。 |
| 内容策略层 prompt 不稳定 | LLM 不一定遵循指令 | 在 `_ensure_content_contract()` 中添加 fallback 逻辑。 |

---

## 六、附录

### 6.1 ppt-master 可复用资产
- **图表定义**: 33 种图表的数据结构与视觉映射逻辑。
- **设计规范**: 13 章结构化设计指南的精简版。
- **节奏规则**: 经过验证的视觉密度交替算法。
- **转换参考**: SVG path 到 DrawingML 命令的 1:1 映射表。
- **禁用特性**: 明确的 SVG 禁用特性列表，用于约束 AI 生成。

### 6.2 已安装 Skill 索引
- `pptx` (Anthropic): 提供 XML 编辑与图标方案参考。
- `color-font-skill`: 用于 Layer 1 的色彩与字体决策。
- `design-style-skill`: 提供 Sharp, Soft, Rounded 等视觉风格定义。
- `ppt-editing-skill`: 支撑策略 S11 的模板编辑流程。
- `slide-making-skill`: 指导单页 PptxGenJS 渲染规范。
- `ppt-orchestra-skill`: 大纲规划与 QA 流程参考。

### 6.3 ppt-master 转换器代码量参考
- `drawingml_paths.py`: 429 行（核心参考）。
- `drawingml_elements.py`: 848 行。
- `drawingml_styles.py`: 359 行。
- **合计**: 约 2,700 行。通过 PptxGenJS 封装后，预期实现代码量可缩减至 500 行以内。

### 6.4 SVG 生成 Prompt 约束模板
```text
你是一个专业的 PPT 视觉设计师。请为以下内容生成一个 SVG 布局。
画布尺寸：960x540 (16:9)

设计约束：
- 仅允许使用: rect, circle, ellipse, line, polygon, path, text, g
- 禁止使用: clipPath, mask, <style>, class, foreignObject, animate
- 文本处理: 每个 <text> 标签仅限单行，手动控制 y 坐标实现换行。
- 颜色规范: 必须严格遵守 design_spec 中定义的 primary 和 accent 色值。
- 坐标系: 使用绝对坐标，确保元素不超出画布边界。
- 字体: 标题使用 {design_spec.typography.title_font}, 正文使用 {design_spec.typography.body_font}。
```

---

## 七、详细代码参考与实现细节

### 7.1 混合渲染器核心逻辑 (Node.js)

```javascript
/**
 * 将 SVG 元素映射到 PptxGenJS API
 */
async function mapSvgElementToPptx(slide, el, designSpec) {
  const { type, x, y, width, height, fill, stroke, d, content, fontSize } = el;
  
  const commonOpts = {
    x: x / 96, // 转换为英寸
    y: y / 96,
    w: width / 96,
    h: height / 96,
  };

  switch (type) {
    case 'rect':
      slide.addShape(pptx.ShapeType.rect, {
        ...commonOpts,
        fill: { color: fill },
        line: stroke ? { color: stroke, width: 1 } : undefined,
        rectRadius: el.rx ? el.rx / 96 : 0
      });
      break;
      
    case 'text':
      slide.addText(content, {
        ...commonOpts,
        fontFace: designSpec.typography.body_font,
        fontSize: fontSize || designSpec.typography.body_size,
        color: fill || designSpec.colors.text_primary,
        align: 'left',
        valign: 'middle'
      });
      break;
      
    case 'path':
      // 核心：将 SVG path 转换为 PptxGenJS points
      const points = svgPathToPptxPoints(d);
      slide.addShape({
        points: points,
        fill: { color: fill },
        line: stroke ? { color: stroke, width: 1 } : undefined
      });
      break;
  }
}
```

### 7.2 密度节奏引擎实现 (Python)

```python
class DensityEngine:
    def __init__(self):
        self.history = []
        
    def process_layouts(self, layouts: list[str]) -> list[str]:
        optimized = []
        consecutive_high = 0
        
        for i, layout in enumerate(layouts):
            density = DENSITY_MAP.get(layout, "medium")
            
            # 规则 1: 禁止连续 3 页高密度
            if density == "high":
                consecutive_high += 1
                if consecutive_high >= 3:
                    layout = self._downgrade(layout)
                    density = "medium"
                    consecutive_high = 0
            else:
                consecutive_high = 0
                
            # 规则 2: 每 5 页强制呼吸
            if len(optimized) > 0 and len(optimized) % 5 == 0:
                if not any(DENSITY_MAP.get(l) == "breathing" for l in optimized[-5:]):
                    optimized.append("section")
            
            optimized.append(layout)
            
        return optimized

    def _downgrade(self, layout: str) -> str:
        return {
            "grid_4": "grid_3",
            "bento_6": "split_2",
            "bento_5": "asymmetric_2"
        }.get(layout, "grid_3")
```

### 7.3 视觉 QA 审查 Prompt (Multimodal)

```text
你是一个 PPT 视觉质量审查专家。请分析这张幻灯片截图，并检查以下问题：
1. 文字重叠：是否有文字超出了容器边界或与其他元素重叠？
2. 对比度：文字颜色与背景颜色是否有足够的对比度？
3. 对齐：主要元素是否对齐？是否有明显的视觉错位？
4. 占位符：是否遗留了 "xxxx", "lorem ipsum" 或 "[Placeholder]" 等占位符？

如果发现问题，请详细描述问题所在的坐标区域及改进建议。
输出格式：
- 状态: [PASS/FAIL]
- 问题列表: [描述]
- 修复建议: [描述]
```

---

## 分阶段闭环交付计划（2026-03-31 增补，重构版）

目标：基于“官方 + 社区”最佳实践，把当前新增方案升级为**评测驱动（EDD）+ 测试闭环 + 可回归**的最优执行闭环。

适用范围：本节仅覆盖新增分阶段方案，不改动前文已完成历史记录。

---

## 0. 总体原则（重构后）

- 评测先行：每次改动必须先定义可量化评测，再允许代码变更。
- 双集防过拟合：开发集（dev set）用于迭代；保留集（holdout）仅用于阶段验收。
- 单变量优化：同一轮只改一个主变量，避免“多改动导致归因失败”。
- 硬门禁优先：图片、主题、页数、PSNR 走 hard gate；其余指标走 soft gate。
- 测试分层：单测、集成、端到端回归必须分层执行，且每层都有失败即停策略。
- 失败簇驱动：按失败类型分簇修复（媒体、主题、布局、文本），禁止跨簇混改。
- 回归优先：每阶段必须完成 dev/holdout/challenge 三套回归，结果可复现实验。

---

## 1. 通用验收契约（所有阶段统一）

### 1.1 必交付产物

- 代码变更（仅限本阶段范围）
- 测试证据（命令 + 通过数 + 失败数）
- 真实样例：`output/regression/generated.<phase>.pptx`
- 对比报告：`output/regression/issues.<phase>.json`
- 变更记录：`output/regression/fix_record.json`
- 阶段结论：`pass/fail` + 失败簇说明 + 下一轮测试计划

### 1.2 统一评分协议（强约束）

- 主分：`score = min(structural_score, psnr_score)`
- Hard fail 条件（任一命中即失败）：
  - 图片覆盖率低于阈值
  - 主题一致性低于阈值
  - 页数不一致（22/20 等）
  - PSNR 低于阈值
- Soft fail 条件：布局节奏、图表语义、文案覆盖不足等
- 失败必须输出可定位字段：`slide_id`、`issue_code`、`retry_scope`、`retry_target_ids`

### 1.3 数据集与防过拟合

- `dev_set`：用于日常调参与快速迭代
- `holdout_set`：阶段验收专用，不参与日常调参
- `challenge_set`：极端案例（图形复杂、媒体密集、多语种）
- 规则：连续 3 轮只涨 dev 不涨 holdout，判定为过拟合并触发策略重置

### 1.4 测试门禁与冻结策略

- 门禁通过条件：
  - 单测/集成测试全绿
  - holdout_set 达到阶段目标
  - 无新增 blocker 级失败用例
- 冻结触发条件：
  - 连续 2 轮 hard fail
  - holdout_set 连续回退超过阈值（如 score 回退 > 5 分）
  - flaky case 比率超过阈值
  - 关键指标回退超过阈值（如 score 回退 > 5 分）

---

## 2. 分阶段执行（自闭环、可测试、可回归）

### Phase 0 - 基线冻结（0.5 天）

目标：建立可信对照组。

实施：
- 固化 `pipeline-only` / `reconstruct` / `source-replay` 三条基线
- 固化三套数据集（dev/holdout/challenge）
- 固化当前 hard/soft gate 阈值

验收：
- 基线报告可复现（同输入、同版本、同结果）
- 评分与问题桶统计入库

---

### Phase 1 - 输入保真与合同加固（1-2 天）

目标：消除 extraction -> planning -> render 的信息损失。

主改文件：
- `scripts/extract_to_minimax_json.py`
- `scripts/generate_ppt_from_desc.py`
- `agent/src/ppt_service.py`

关键动作：
- 去除硬编码文案兜底，统一改为“输入派生兜底”
- 强制透传 `required_facts/anchors/theme/media_manifest`
- 新增 payload 完整性校验（缺字段直接 fail-fast）

验收：
- 合同字段完整率 100%
- 关键锚点命中率达到阈值

---

### Phase 2 - 设计合同 V2 与 Archetype 编排（2 天）

目标：建立稳定视觉语法，减少“每页临场发挥”。

主改文件：
- `agent/src/ppt_service.py`
- `scripts/minimax/render-contract.mjs`
- `scripts/minimax/templates/archetype-catalog.json`

关键动作：
- 引入 `PresentationDesignContractV2`（deck token + slide spec）
- 建立“页面角色 -> archetype”映射（cover/toc/section/content/summary）
- 增加模板能力约束校验，避免误用 fallback

验收：
- 20 页样例 archetype 覆盖 >= 6
- 模板能力冲突全部可诊断（非静默）

---

### Phase 3 - Skill 治理与单写者策略（1-2 天）

目标：解决多 skill 相互覆盖与风格漂移。

主改文件：
- `agent/src/installed_skill_executor.py`
- `agent/src/ppt_service.py`

关键动作：
- 增加 `skill_write_policy`（字段所有权矩阵）
- 增加 `skill_write_conflict` 诊断
- `dev_strict` 下：越权写入直接失败

验收：
- 越权覆盖为 0
- 冲突诊断可追溯到 skill、字段、slide

---

### Phase 4 - 主题/媒体强对齐（2 天）

目标：优先修复当前最大扣分项（theme/media）。

主改文件：
- `scripts/extract_to_minimax_json.py`
- `scripts/generate-pptx-minimax.mjs`
- `agent/src/minimax_exporter.py`
- `scripts/compare_ppt_visual.py`

关键动作：
- 抽取并透传主题 token（主色/辅色/字体/字号层级）
- 抽取并透传媒体清单（含 base64/hash/位置）
- 本地重建链路强制执行媒体插入与主题色落地

验收（hard gate）：
- 主题一致性 >= 阈值
- 媒体覆盖率 >= 阈值（建议 >= 70%）
- 缺图缺色直接 fail

---

### Phase 5 - 评分器升级与门禁重平衡（1-2 天）

目标：让分数真实反映视觉质量，避免“高分低质”。

主改文件：
- `scripts/compare_ppt_visual.py`
- `agent/src/ppt_quality_gate.py`

关键动作：
- 强制 PSNR 必跑
- 加入“页数明确扣分”（如 22/20）
- 对 image/theme 增加 hard penalty 与 hard fail
- 输出结构化失败原因，直接驱动下一轮修复

验收：
- 评分报告可解释（结构分/PSNR/扣分项）
- 不再出现“缺图缺色但高分通过”

---

### Phase 6 - 优化循环工程化（2-3 天）

目标：把“像训练模型一样迭代优化”制度化。

关键动作：
- 引入 champion/challenger 机制（旧策略 vs 新策略）
- 单变量实验协议（每轮仅一个主改动）
- 自动生成 `fix_plan.json`，并把失败类型映射到固定修复策略
- 每轮写入 `fix_record.json`，沉淀可复用经验

验收：
- holdout_set 中位分持续提升
- 修复策略命中率持续提升
- 回归次数下降

---

### Phase 7 - 测试资产与可观测加固（1 天）

目标：确保测试体系稳定演进，问题可快速发现与定位。

主改文件：
- `agent/src/ppt_routes.py`
- `agent/src/ppt_service.py`
- runbook 文档

关键动作：
- 测试配置开关：`PPT_DEV_STRICT`, `PPT_GATE_STRICT`, `PPT_TEST_PROFILE`
- 建立 nightly 回归任务（dev/holdout/challenge）
- 固化失败簇看板（score、hard_fail_rate、fallback_ratio、flaky_rate）
- 失败样例自动归档到 `output/regression/failures/`

验收：
- 任一阶段可复现实验结果
- 指标异常可在 SLA 时间内告警并定位到失败簇

---

## 3. 阶段执行矩阵（升级版）

每个阶段固定记录以下字段：
- `baseline_score`
- `after_score`
- `delta`
- `hard_fail_rate`
- `main_bucket_improvement`（content/layout/theme/media/geometry）
- `gate_decision`（pass/fail）
- `regression_verified`（yes/no）

模板：

| Phase | Baseline | After | Delta | Hard Fail Rate | Main Bucket Improvement | Test Status | Gate Decision | Regression Verified |
|------|----------|-------|-------|----------------|--------------------------|-------------|---------|-------------------|
| P0 | - | - | - | - | baseline only | pass | n/a | yes |
| P1 | | | | | | | | |
| P2 | | | | | | | | |
| P3 | | | | | | | | |
| P4 | | | | | | | | |
| P5 | | | | | | | | |
| P6 | | | | | | | | |
| P7 | | | | | | | | |

---

## 4. 参考依据（官方 + 社区）

### 官方
- OpenAI：Evaluation best practices（评测驱动、自动化评测、与人工评估对齐、持续迭代）  
  https://platform.openai.com/docs/guides/evaluation-best-practices
- OpenAI：Evals drive next chapter of AI（持续评测与改进）  
  https://openai.com/index/evals-drive-next-chapter-of-ai/
- Google：Rules of ML（数据与特征优先、迭代与系统化评测）  
  https://developers.google.com/machine-learning/guides/rules-of-ml
- pytest 官方文档（测试组织、参数化、fixture 最佳实践）  
  https://docs.pytest.org/

### 社区
- Martin Fowler：Test Pyramid（分层测试思想）  
  https://martinfowler.com/articles/practical-test-pyramid.html
- Google Testing Blog（自动化测试与回归实践）  
  https://testing.googleblog.com/

---

## 五、覆盖核对与补强（针对“从零创作”七项要求）

### 5.1 七项要求覆盖结论

| 要求 | 当前覆盖情况 | 现有落点 | 补强动作 |
| :--- | :--- | :--- | :--- |
| 先定设计系统，再生成内容 | 已覆盖 | S1、Phase 2（DesignContractV2） | 增加“Token 只读约束”，禁止 slide 自由覆写 |
| 内容生成与视觉编排拆通道 | 部分覆盖 | Layer 2、S6 | 增加双通道 Schema（content/visual）并做合同校验 |
| 页面语法库（12-20 archetype） | 已覆盖（方向） | S5、Phase 2 | 固化最小可用 16 个 archetype 清单 |
| 媒体与图形语义强约束 | 部分覆盖 | S2、S7、Phase 4 | 新增 `media_required/chart_required/diagram_type` 硬门禁 |
| Skill 主从制（单写者） | 已覆盖 | Phase 3（skill_write_policy） | 明确字段写权限矩阵并落地 fail-fast |
| 质量门创作目标导向 | 已覆盖 | S8/S9、Phase 5 | 增加“字体层级完整性”硬/软门禁指标 |
| 失败类型驱动迭代 | 已覆盖 | Phase 6（single-variable/fix_plan） | 固化失败簇与修复策略映射表 |

结论：7 项里 4 项已覆盖、3 项部分覆盖。本节补强内容用于把“部分覆盖”升级为“可执行强约束”。

### 5.2 从零创作专用 Schema V2（双通道）

```jsonc
{
  "deck_spec": {
    "topic": "string",
    "design_tokens": {
      "color": { "primary": "#22223B", "secondary": "#4A4E69", "accent": "#9A8C98", "bg": "#F2E9E4" },
      "typography": {
        "title_font": "Microsoft YaHei",
        "body_font": "Arial",
        "size_scale": { "h1": 34, "h2": 26, "h3": 20, "body": 15, "caption": 11 }
      },
      "shape": { "radius": [0, 4, 8, 12], "shadow": ["none", "soft", "medium"] },
      "spacing": { "page_margin": 0.45, "grid_gap": 0.2, "section_gap": 0.32 }
    },
    "guardrails": {
      "token_only_mode": true,
      "max_text_only_slide_ratio": 0.2,
      "min_media_coverage_ratio": 0.7
    }
  },
  "slides": [
    {
      "slide_id": "s01",
      "archetype": "cover_hero",
      "content_channel": {
        "title": "string",
        "assertion": "string",
        "evidence": ["string"],
        "data_points": [{ "label": "营收", "value": 120, "unit": "亿" }],
        "chart_data": { "type": "bar", "series": [] },
        "media_intent": "人物/产品/场景"
      },
      "visual_channel": {
        "layout": "hero_1",
        "render_path": "pptxgenjs",
        "component_slots": ["title", "subtitle", "hero_media", "footer_note"],
        "animation_rhythm": "calm"
      },
      "semantic_constraints": {
        "media_required": true,
        "chart_required": false,
        "diagram_type": "none"
      }
    }
  ]
}
```

执行规则：
- 通道 A（`content_channel`）只允许写内容与数据，不允许写布局与主题。
- 通道 B（`visual_channel`）只允许写布局与视觉，不允许改写事实与数据。
- `token_only_mode=true` 时，所有颜色/字号/圆角必须取自 `design_tokens`，越权即 fail-fast。

### 5.3 页面语法库（Archetype）最小清单

建议先固化 16 个 archetype，覆盖“叙事 + 数据 + 关系 +结论”四类场景：

1. `cover_hero`
2. `toc_compact`
3. `section_divider`
4. `thesis_assertion`
5. `evidence_cards_3`
6. `comparison_2col`
7. `process_flow_4step`
8. `timeline_horizontal`
9. `matrix_2x2`
10. `dashboard_kpi_4`
11. `chart_single_focus`
12. `chart_dual_compare`
13. `media_showcase_1p2s`
14. `quote_hero`
15. `risk_mitigation`
16. `summary_action`

路由约束：
- 每页先选 archetype，再填 slot，不允许“自由布局直出”。
- 同一 deck 内单 archetype 占比建议 <= 25%，TOP-2 占比 <= 60%。

### 5.4 质量门指标表（创作目标导向）

| 指标 | 类型 | 计算口径 | 建议阈值 | 失败动作 |
| :--- | :--- | :--- | :--- | :--- |
| 媒体覆盖率 | Hard | `media_required=true` 且实际有媒体的页占比 | >= 70% | slide 重试，失败则降级 |
| 图表覆盖率 | Hard | `chart_required=true` 且图表数据有效占比 | >= 90% | 回退到 chart archetype 重排 |
| 主题一致性 | Hard | token 命中率（颜色/字体/字号） | >= 95% | 直接 fail-fast |
| 页数一致性 | Hard | 输出页数与计划页数一致 | 100% | 直接 fail-fast |
| PSNR | Hard | 与参考输出视觉差异 | >= 阈值 | 触发视觉重试 |
| 版式多样性 | Soft | TOP-2 占比 + ABAB 检测 | TOP-2 <= 60% | 触发布局重排 |
| 密度节奏 | Soft | 连续高密度页/五页呼吸页规则 | 连高 <= 2 | 触发 density 降级 |
| 字体层级完整性 | Soft | H1/H2/body/caption 是否齐全且有序 | >= 95% | 回写 typography 纠偏 |
| 文案覆盖率 | Soft | assertion/evidence 命中率 | >= 90% | 触发内容通道重写 |

### 5.5 Skill 主从写权限矩阵（落地版）

| 字段域 | 主写 Skill | 从 Skill 权限 | 冲突策略 |
| :--- | :--- | :--- | :--- |
| `layout/template/render_path` | `visual-orchestrator` | 只读 | 从 skill 写入直接拒绝 |
| `theme/tokens/typography` | `design-style-skill` + `color-font-skill` | 建议值 | 主写覆盖并记录冲突 |
| `title/assertion/evidence` | `content-strategy-skill` | 建议值 | 以主写为准 |
| `chart_type/chart_data` | `slide-making-skill` | 可补全 | 不可降级为占位图表 |
| `template_edit/xml_patch` | `ppt-editing-skill` | 禁写 | 非模板路由禁用 |

执行建议：
- 在 `skill_write_policy` 中把上表配置化。
- 在 `dev_strict` 与 `PPT_GATE_STRICT` 下启用“越权即失败”。
