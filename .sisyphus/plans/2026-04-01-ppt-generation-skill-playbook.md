# PPT 生成 Skill Playbook

> 日期：2026-04-01
> 定位：Skill 层面的 PPT 生成最佳实践手册，补充现有 `ppt_service.py` 工程体系。
> 适用范围：从零生成（zero-create）与模板编辑（template-edit）双路径。
> 来源：MiniMax pptx-plugin + pptx-generator skill、Anthropic pptx skill、ppt-master skill 走读综合。

---

## 1. 方案全景

### 1.1 四个来源定位

| 方案 | 路径 | 核心技术 | 定位 |
|------|------|----------|------|
| MiniMax pptx-generator | `vendor/minimax-skills/skills/pptx-generator` | PptxGenJS + markitdown | 独立 skill，从零生成，含完整设计系统 |
| MiniMax pptx-plugin | `vendor/minimax-skills/plugins/pptx-plugin` | PptxGenJS + 5类专用 agent | Plugin 形态，agent 分工最清晰 |
| Anthropic pptx | `agent/tests/fixtures/skills_reference/anthropic/skills/pptx` | PptxGenJS + LibreOffice 视觉 QA | 同 MiniMax 但增加图像视觉检查 |
| ppt-master | `agent/tests/fixtures/skills_reference/ppt-master/skills/ppt-master` | SVG → PPTX pipeline | 重量级，文档驱动，串行主 agent |

### 1.2 核心差异

**生成技术路线**

```
MiniMax / Anthropic:  需求 → 规划 → JS模块(每张幻灯片) → compile.js → .pptx
ppt-master:           源文档 → Markdown → 设计规格 → SVG逐页生成 → svg_to_pptx.py → .pptx
```

关键分歧：
- MiniMax/Anthropic 用 PptxGenJS 原生 API，输出真正可编辑的 .pptx（矢量文字、可选中）
- ppt-master 用 SVG 嵌入，视觉还原度高但文字不可编辑（除非用 `--only native` 模式）

**并行策略**

| 方案 | 并行度 | 方式 |
|------|--------|------|
| MiniMax pptx-plugin | 最高，max 5 concurrent | 5类专用 agent 同时跑 |
| MiniMax pptx-generator | 高，up to 5 | 通用 subagent 并行 |
| Anthropic pptx | 高 | 同上 + 视觉 QA subagent |
| ppt-master | **禁止并行** | 主 agent 串行，明确禁止 subagent 生成 SVG |

**QA 机制**

| 方案 | 文本 QA | 视觉 QA |
|------|---------|---------|
| MiniMax | `markitdown` 文本提取 | 无 |
| Anthropic | `markitdown` | LibreOffice→PDF→图片→subagent 视觉检查 |
| ppt-master | `markitdown` | `svg_quality_checker.py` |

### 1.3 推荐方案

**MiniMax pptx-plugin 架构 + Anthropic 视觉 QA**

理由：
1. pptx-plugin 的 agent 分工最清晰，5类 agent 各司其职，prompt 边界明确
2. MiniMax 设计系统最完整：color-font-skill + design-style-skill + 18套配色 + 4种风格配方
3. Anthropic 的视觉 QA 补充了 MiniMax 的唯一缺口
4. ppt-master 不适合集成：串行强制、禁止 subagent、依赖本地脚本，与现有 Python 后端冲突

**路径选择决策树**

```
有现成模板？
  ├─ 是 → ppt-editing-skill（XML 解包 → 并行编辑 → 重打包）
  └─ 否 → 从零生成
           ├─ 需要高视觉还原（设计稿转PPT）→ ppt-master（SVG路线）
           └─ 需要可编辑原生PPT → MiniMax pptx-plugin（推荐）
                                    + Anthropic 视觉 QA 补充
```

---

## 2. 从零生成完整执行流程

### Phase 1：需求理解 & 设计决策

**输入**：用户需求（主题、受众、页数、语言、风格偏好）

**Step 1.1 选配色方案**（color-font-skill）

从 18 套配色中选择，匹配主题：

| # | 名称 | 适用场景 |
|---|------|----------|
| 2 | 商务与权威 | 年度汇报、金融分析、企业介绍 |
| 7 | 活力与科技 | 体育赛事、创业路演、少儿教育 |
| 9 | 科技与夜景 | 科技发布会、高端汽车 |
| 10 | 教育与图表 | 统计报告、市场分析、通用商务 |
| 14 | 轻奢与神秘 | 珠宝展示、高端咨询 |
| 15 | 纯净科技蓝 | 云计算/AI、医疗 |

字体配对规则：
- 中文：Microsoft YaHei（唯一选择）
- 英文：Arial（默认）/ Georgia / Calibri / Cambria / Trebuchet MS

**Step 1.2 选风格配方**（design-style-skill）

| 风格 | rectRadius 范围 | 适合场景 |
|------|----------------|----------|
| Sharp & Compact | 0 ~ 0.05" | 数据密集、专业报告 |
| Soft & Balanced | 0.08" ~ 0.12" | 企业汇报、通用PPT |
| Rounded & Spacious | 0.15" ~ 0.25" | 产品介绍、营销演示 |
| Pill & Airy | 0.3" ~ 0.5" | 品牌展示、发布会 |

**Step 1.3 确定 theme 对象**

```javascript
// 5个固定 key，不可更改名称
const theme = {
  primary:   "22223b",  // 最深色，用于标题
  secondary: "4a4e69",  // 深色强调，用于正文
  accent:    "9a8c98",  // 中间调强调
  light:     "c9ada7",  // 浅色强调
  bg:        "f2e9e4"   // 背景色
};
```

---

### Phase 2：内容规划（ppt-orchestra-skill）

**Step 2.1 幻灯片分类**

每张幻灯片必须归属 5 种页面类型之一：

| 类型 | 用途 | 内容要素 |
|------|------|----------|
| Cover Page | 开场定调 | 大标题、副标题/演讲者、日期、背景图/主题元素 |
| Table of Contents | 导航（3-5节） | 章节列表（可选图标/页码） |
| Section Divider | 章节过渡 | 章节编号+标题（可选1-2行简介） |
| Content Page | 内容主体 | 见 Step 2.2 |
| Summary / Closing | 收尾+行动 | 关键要点、CTA/下一步、联系方式/二维码 |

**Step 2.2 Content Page 子类型**

| 子类型 | 适用内容 | 布局特征 |
|--------|----------|----------|
| Text | 要点/引言/短段落 | 必须加图标或形状，不能纯文字 |
| Mixed Media | 图文混排 | 两栏或半出血图+文字叠加 |
| Data Visualization | 图表+1-3个关键结论 | 必须标注数据来源 |
| Comparison | A vs B、优缺点 | 并排卡片，视觉区分明确 |
| Timeline / Process | 步骤/流程/阶段 | 带箭头的编号步骤 |
| Image Showcase | 视觉主导 | 主图为主，文字为辅 |

**Step 2.3 视觉多样性强制规则**

- 相邻幻灯片不得使用相同布局
- 不得连续超过2张相同子类型
- 标题居中，正文/列表左对齐
- 每张内容页必须有至少一个非文字元素（图片/图标/图表/形状）

**Step 2.4 字体层级**

| 元素 | 字号 | 说明 |
|------|------|------|
| 封面主标题 | 72-120pt | bold，视觉锚点 |
| 幻灯片标题 | 36-44pt | bold |
| 章节标题 | 20-24pt | bold |
| 正文 | 14-16pt | 不加粗 |
| 说明/来源 | 10-12pt | 不加粗，muted 颜色 |
| 数据高亮 | 60-72pt | 大数字展示 |

---

### Phase 3：并行生成（max 5 concurrent subagents）

**Step 3.1 文件结构**

```
slides/
├── slide-01.js          # 每张幻灯片一个 JS 模块
├── slide-02.js
├── ...
├── imgs/                # 幻灯片使用的图片
└── output/
    └── presentation.pptx
```

**Step 3.2 按类型分发 agent**

| Agent | 负责页面类型 | 必须加载的 skill |
|-------|-------------|-----------------|
| cover-page-generator | Cover Page | slide-making-skill |
| table-of-contents-generator | Table of Contents | slide-making-skill |
| section-divider-generator | Section Divider | slide-making-skill |
| content-page-generator | Content Page（所有子类型） | slide-making-skill + design-style-skill |
| summary-page-generator | Summary / Closing | slide-making-skill |

**Step 3.3 每个 JS 模块的标准格式**

```javascript
// slides/slide-01.js
const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'cover',   // cover|toc|divider|content|summary
  index: 1,
  title: 'Presentation Title'
};

// 必须是同步函数，不能 async
function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addText(slideConfig.title, {
    x: 0.5, y: 2, w: 9, h: 1.2,
    fontSize: 48, fontFace: "Arial",
    color: theme.primary, bold: true, align: "center"
  });

  return slide;
}

// 独立预览入口（用于单张 QA）
if (require.main === module) {
  const pres = new pptxgen();
  pres.layout = 'LAYOUT_16x9';
  const theme = {
    primary: "22223b", secondary: "4a4e69",
    accent: "9a8c98", light: "c9ada7", bg: "f2e9e4"
  };
  createSlide(pres, theme);
  pres.writeFile({ fileName: "slide-01-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
```

**Step 3.4 页码 badge（非封面页必须）**

```javascript
// 圆形 badge（默认）
slide.addShape(pres.shapes.OVAL, {
  x: 9.3, y: 5.1, w: 0.4, h: 0.4,
  fill: { color: theme.accent }
});
slide.addText("3", {
  x: 9.3, y: 5.1, w: 0.4, h: 0.4,
  fontSize: 12, fontFace: "Arial",
  color: "FFFFFF", bold: true,
  align: "center", valign: "middle"
});

// Pill badge（Pill & Airy 风格用）
slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
  x: 9.1, y: 5.15, w: 0.6, h: 0.35,
  fill: { color: theme.accent }, rectRadius: 0.15
});
slide.addText("03", {
  x: 9.1, y: 5.15, w: 0.6, h: 0.35,
  fontSize: 11, fontFace: "Arial",
  color: "FFFFFF", bold: true,
  align: "center", valign: "middle"
});
```

---

### Phase 4：编译

**Step 4.1 compile.js**

```javascript
// slides/compile.js
const pptxgen = require('pptxgenjs');
const pres = new pptxgen();
pres.layout = 'LAYOUT_16x9';

const theme = {
  primary:   "22223b",
  secondary: "4a4e69",
  accent:    "9a8c98",
  light:     "c9ada7",
  bg:        "f2e9e4"
};

const slideCount = 12; // 按实际页数调整
for (let i = 1; i <= slideCount; i++) {
  const num = String(i).padStart(2, '0');
  const mod = require(`./slide-${num}.js`);
  mod.createSlide(pres, theme);
}

pres.writeFile({ fileName: './output/presentation.pptx' });
```

**Step 4.2 执行**

```bash
mkdir -p slides/output
cd slides && node compile.js
```

---

### Phase 5：QA（必须执行，不可跳过）

**Step 5.1 文本 QA（MiniMax 方式）**

```bash
# 全量文本提取，检查内容完整性
python -m markitdown slides/output/presentation.pptx

# 检查占位符残留
python -m markitdown slides/output/presentation.pptx | grep -iE "xxxx|lorem|ipsum|placeholder|this.*(page|slide).*layout"
# 有输出 → 必须修复，不得声明完成
```

**Step 5.2 单张预览 QA（生成阶段）**

```bash
# 每个 subagent 生成后立即验证
node slides/slide-XX.js
python -m markitdown slide-XX-preview.pptx
python -m markitdown slide-XX-preview.pptx | grep -iE "xxxx|lorem|ipsum|placeholder"
```

**Step 5.3 视觉 QA（Anthropic 方式，补充）**

```bash
# 转换为图片
python scripts/office/soffice.py --headless --convert-to pdf slides/output/presentation.pptx
pdftoppm -jpeg -r 150 presentation.pdf slide
# 生成 slide-01.jpg, slide-02.jpg ...
```

视觉检查 prompt（发给 subagent）：

```
Visually inspect these slides. Assume there are issues — find them.

Look for:
- Overlapping elements (text through shapes, lines through words)
- Text overflow or cut off at edges/box boundaries
- Elements too close (< 0.3" gaps) or nearly touching
- Insufficient margin from slide edges (< 0.5")
- Low-contrast text (light gray on cream background)
- Low-contrast icons (dark icons on dark backgrounds)
- Missing page number badge (all slides except cover)
- Leftover placeholder content
- Same layout repeated on adjacent slides

For each slide, list issues or areas of concern, even if minor.
```

**Step 5.4 验证循环（必须至少一轮）**

```
1. 生成 → 提取文本 → 检查内容
2. 列出发现的问题（若无问题，再仔细看一遍）
3. 修复问题
4. 重新验证受影响的幻灯片（一个修复常常引发另一个问题）
5. 重复直到完整检查无新问题
```

---

## 3. 模板编辑流程（ppt-editing-skill）

### Step 3.1 分析模板

```bash
cp /path/to/user-provided.pptx template.pptx
python -m markitdown template.pptx > template.md
# 查看 template.md 了解占位符文字和幻灯片结构
```

### Step 3.2 规划幻灯片映射

- 主动寻找多样布局：多栏、图文组合、全出血图、引言、章节分隔、数据展示
- 避免：每张都用相同的标题+要点布局

### Step 3.3 解包 → 结构操作 → 内容编辑 → 清理 → 打包

```bash
python unpack.py template.pptx unpacked/

# 结构操作（必须在内容编辑前完成）
# 删除幻灯片：从 ppt/presentation.xml 的 <p:sldIdLst> 移除 <p:sldId>
# 复制幻灯片：python add_slide.py（不要手动复制文件）
# 重排顺序：重排 <p:sldIdLst> 中的 <p:sldId> 元素

# 内容编辑（可用 subagent 并行，每张幻灯片是独立 XML 文件）
# 编辑 unpacked/ppt/slides/slide{N}.xml
# 使用 Edit 工具，不用 sed 或 Python 脚本

python clean.py unpacked/
python pack.py unpacked/ edited.pptx
```

### Step 3.4 XML 编辑规则

```xml
<!-- 标题/子标题/行内标签加粗 -->
<a:rPr lang="en-US" sz="2799" b="1" .../>

<!-- 多条目用独立 <a:p>，不要拼接成一个字符串 -->
<a:p>
  <a:pPr algn="l"><a:lnSpc><a:spcPts val="3919"/></a:lnSpc></a:pPr>
  <a:r><a:rPr lang="en-US" sz="2799" b="1" .../><a:t>Step 1</a:t></a:r>
</a:p>
<a:p>
  <a:pPr algn="l"><a:lnSpc><a:spcPts val="3919"/></a:lnSpc></a:pPr>
  <a:r><a:rPr lang="en-US" sz="2799" .../><a:t>Do the first thing.</a:t></a:r>
</a:p>

<!-- 引号用 XML 实体 -->
<a:t>the &#x201C;Agreement&#x201D;</a:t>

<!-- 前后有空格的文字 -->
<a:t xml:space="preserve"> text with spaces </a:t>
```

---

## 4. PptxGenJS 关键约束（硬性规则）

### 4.1 会静默损坏文件的三个错误

```javascript
// ❌ 错误1：hex 颜色带 #
color: "#FF0000"
// ✅ 正确
color: "FF0000"

// ❌ 错误2：在 hex 字符串里编码透明度
shadow: { color: "00000020" }
// ✅ 正确
shadow: { color: "000000", opacity: 0.12 }

// ❌ 错误3：async createSlide（compile.js 不会 await）
async function createSlide(pres, theme) { ... }
// ✅ 正确
function createSlide(pres, theme) { ... }
```

### 4.2 复用 options 对象导致静默错误

```javascript
// ❌ 错误：PptxGenJS 会 mutate 对象
const shadow = { type: "outer", blur: 6, offset: 2, color: "000000", opacity: 0.15 };
slide.addShape(pres.shapes.RECTANGLE, { shadow, x: 0.5, y: 1, w: 4, h: 2 });
slide.addShape(pres.shapes.RECTANGLE, { shadow, x: 5, y: 1, w: 4, h: 2 }); // 第二次出错

// ✅ 正确：工厂函数每次返回新对象
const makeShadow = () => ({ type: "outer", blur: 6, offset: 2, color: "000000", opacity: 0.15 });
slide.addShape(pres.shapes.RECTANGLE, { shadow: makeShadow(), x: 0.5, y: 1, w: 4, h: 2 });
slide.addShape(pres.shapes.RECTANGLE, { shadow: makeShadow(), x: 5, y: 1, w: 4, h: 2 });
```

### 4.3 长标题防截断

```javascript
slide.addText("Long Title Here", {
  x: 0.5, y: 2, w: 9, h: 1,
  fontSize: 48, fit: "shrink"  // 自动缩小防止换行
});
```

### 4.4 尺寸与坐标参考

```
幻灯片尺寸：10" × 5.625"（LAYOUT_16x9）
安全边距：0.5"（最小）
页码 badge 位置：x: 9.3", y: 5.1"
```

---

## 5. 设计硬性规则

### 5.1 颜色

- 只用 theme 对象的 5 个 key（primary/secondary/accent/light/bg）
- 不自造颜色，不修改配色（亮度/饱和度/混合）
- 唯一例外：用 `transparency` 属性加透明度（0-100）
- 无渐变，无动画，纯静态

### 5.2 字体

- 正文不加粗（bold 只用于标题和行内标签）
- 中文：Microsoft YaHei；英文：Arial（或 Georgia/Calibri/Trebuchet MS）
- 标题和正文可用不同字体配对

### 5.3 禁止的 AI 生成感特征

- 标题下方的装饰线（最典型的 AI 生成感）
- 所有幻灯片相同布局
- 纯文字幻灯片（必须有视觉元素）
- 正文居中对齐（正文/列表必须左对齐）

### 5.4 间距规范

| 用途 | 推荐值 |
|------|--------|
| 页面安全边距 | 0.4" ~ 0.6" |
| 主要区块间距 | 0.5" ~ 0.8" |
| 元素组间距 | 0.3" ~ 0.5" |
| 卡片内边距 | 0.2" ~ 0.4" |
| 列表项间距 | 0.15" ~ 0.25" |

---

## 6. 与现有 Python 后端的集成

### 6.1 调用链路

```
POST /api/v1/v7/export/submit
  ↓
ppt_routes.py
  ↓
ppt_service.py（主流程，8464行）
  ↓ PPT_MODULE_MAINFLOW_ENABLED=true
ppt_subagent_executor.py（LangGraph StateGraph）
  ↓ PPT_INSTALLED_SKILL_EXECUTOR_ENABLED=true
ppt_direct_skill_runtime.py
  ↓ 加载 skills
ppt-orchestra-skill + slide-making-skill + color-font-skill + design-style-skill
  ↓
slides/slide-XX.js → compile.js → presentation.pptx
  ↓
ppt_visual_qa.py（视觉检查）
  ↓
ppt_export_pipeline.py
  ↓
GET /api/v1/v7/export/status/{task_id}
```

### 6.2 环境变量（Railway worker 推荐配置）

```bash
PPT_EXECUTION_ROLE=worker
PPT_MODULE_MAINFLOW_ENABLED=true
PPT_MODULE_MAINFLOW_RENDER_EACH_ENABLED=true
PPT_INSTALLED_SKILL_EXECUTOR_ENABLED=true
PPT_INSTALLED_SKILL_EXECUTOR_BIN=uv
PPT_INSTALLED_SKILL_EXECUTOR_ARGS=["run","python","-m","src.installed_skill_executor"]
PPT_INSTALLED_SKILL_EXECUTOR_TIMEOUT_SEC=30
PPT_DIRECT_SKILL_RUNTIME_ENABLED=true
PPT_DIRECT_SKILL_RUNTIME_BIN=python
PPT_DIRECT_SKILL_RUNTIME_ARGS=["-m","src.ppt_direct_skill_runtime"]
PPT_DIRECT_SKILL_RUNTIME_REQUIRE=true
PPT_EXPORT_SYNC_ENABLED=true
```

### 6.3 Vercel（web role）配置

```bash
PPT_EXECUTION_ROLE=web
PPT_MODULE_RETRY_ENABLED=false
PPT_INSTALLED_SKILL_EXECUTOR_ENABLED=false
PPT_EXPORT_SYNC_ENABLED=false
PPT_EXPORT_WORKER_BASE_URL=https://<railway-worker-domain>
```

---

## 7. 依赖清单

```bash
# Python
pip install "markitdown[pptx]"   # 文本提取 QA（必须）
pip install Pillow                # 视觉 QA 图片处理（可选）

# Node
npm install -g pptxgenjs          # 幻灯片生成（必须）
npm install -g react-icons react react-dom sharp  # 图标（可选）

# 视觉 QA（可选，Anthropic 方式）
# Linux: apt install libreoffice poppler-utils
# macOS: brew install libreoffice poppler
```

---

## 8. 快速检查清单

生成完成前，逐项确认：

- [ ] theme 对象只用 5 个固定 key（primary/secondary/accent/light/bg）
- [ ] 所有 hex 颜色无 `#` 前缀
- [ ] 所有 `createSlide` 函数是同步的（无 async）
- [ ] shadow/options 对象未复用（用工厂函数）
- [ ] 非封面页均有页码 badge（x:9.3", y:5.1"）
- [ ] 正文无加粗
- [ ] 无标题装饰线
- [ ] 相邻幻灯片布局不重复
- [ ] 每张内容页有至少一个非文字视觉元素
- [ ] `markitdown` 文本 QA 通过（无占位符残留）
- [ ] 至少完成一轮修复-再验证循环
