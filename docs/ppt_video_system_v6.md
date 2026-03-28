# PPT & 视频生成系统 — 技术方案 (v7)

> 最后更新: 2026-03-23
> 状态: 已落地验证，可生成商业级 PPT + 讲解视频
> v7 改进: Skill目录架构 + Marp双路输出 + Remotion截图序列 + Ken Burns动效 + 并发工作流 + 文本溢出校验

---

## 一、系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    用户输入                                       │
│  "灵创智能企业介绍PPT，包含企业简介、核心产品、技术优势..."          │
└───────────────┬─────────────────────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────────────────┐
│  Step 1: LLM 内容生成 (Premium Generator)                       │
│  - 角色人设: 制造业20年资深顾问「老周」                            │
│  - 布局编排: 强制相邻页不同 (cover→bullet→comparison→quote→big)  │
│  - 内容填充: 每页3-5条要点，含具体数据                            │
│  - 多样化script: 8种模板随机选择，消除语音重复                     │
└───────────────┬─────────────────────────────────────────────────┘
                │ slides[]
┌───────────────▼─────────────────────────────────────────────────┐
│  Step 2: TTS 音频合成 (Minimax API)                              │
│  - 批量合成 + 音频时长获取                                        │
│  - 音频时长驱动每页播放时间                                       │
└───────────────┬─────────────────────────────────────────────────┘
                │ slides[] + audio_urls[]
┌───────────┬───┴────────────────────────────────────────────────┐
│           │                                                     │
│  Step 3a  │  Step 3b                                            │
│  HTML截图  │  Remotion渲染                                       │
│  (PPTX)   │  (视频)                                             │
│           │                                                     │
│  Playwright│  @marp-team/marp-core                              │
│  截图1920  │  Markdown → HTML → 视频帧                          │
│  ×1080    │  TransitionSeries + spring动画                      │
│     │     │     │                                               │
│     ▼     │     ▼                                               │
│  python   │  Remotion                                           │
│  -pptx    │  renderMedia()                                      │
│  嵌入截图  │  → MP4                                              │
│  → PPTX   │                                                     │
└───────────┴─────────────────────────────────────────────────────┘
```

---

## 二、两个独立功能

### Feature A: PPT 生成
```
用户需求 → LLM 大纲 → 用户确认 → LLM 内容 → HTML截图 → PPTX导出
```
- 输入: 用户需求文本
- 输出: .pptx 文件 (可编辑，可下载)

### Feature B: PPT/PDF 视频生成
```
导入PPT/PDF → 解析内容 → LLM增强 → TTS合成 → Remotion渲染 → MP4
```
- 输入: .pptx / .ppt / .pdf 文件
- 输出: .mp4 讲解视频 (含TTS音频)

---

## 三、数据模型

### Python 端 (`agent/src/schemas/ppt_v3.py`)

```python
# 版式类型 (7种)
LayoutType = Literal[
    "cover",           # 封面 (全屏渐变+超大标题)
    "bullet_points",   # 要点列表 (顶部标题栏+要点+右侧高亮)
    "comparison",      # 对比 (红绿双栏)
    "big_number",      # 大数字 (超大渐变数字+说明)
    "quote",           # 金句 (深色背景+大号引用)
    "section_divider", # 章节过渡
    "closing",         # 致谢页
]

# 角色与动作
RoleType = Literal["host"]
ActionType = Literal["none", "spotlight", "draw_circle", "underline"]

class DialogueLine(BaseModel):
    role: str = "host"
    text: str = ""
    target_id: str = ""
    action: ActionType = "none"
    audio_url: str = ""
    audio_duration: float = 0

class VisualContent(BaseModel):
    title: str = ""
    subtitle: str = ""
    body_items: List[str] = []      # 3-5条要点
    emphasis_words: List[str] = []  # 1-2个核心数字
    comparison: Optional[dict] = None  # {left_title, left_items, right_title, right_items}
    bg_style: str = "dark"

class SlideContentV3(BaseModel):
    order: int
    layout_type: LayoutType
    content: VisualContent
    script: List[DialogueLine]
    duration: float = 0  # 由音频时长决定
```

### TypeScript 端 (`src/lib/types/ppt.ts`)

```typescript
export type LayoutType = 'cover' | 'bullet_points' | 'comparison' | 'big_number' | 'quote';

export interface SlideContent {
  id: string;
  layoutType: LayoutType;
  content: {
    title: string;
    bodyItems: string[];
    emphasisWords: string[];
    comparison?: { leftTitle: string; leftItems: string[]; rightTitle: string; rightItems: string[] };
  };
  script: { role: string; text: string; action: string; audioUrl?: string; audioDuration?: number }[];
  duration: number;
}
```

---

## 四、API 端点

### Premium API (`/api/v1/premium`)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/premium/generate` | POST | 一步生成: 布局编排+内容填充+script |
| `/api/v1/premium/tts` | POST | 批量TTS合成+音频时长 |

### PPT API (`/api/v1/ppt`)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/ppt/outline` | POST/PUT | 生成/编辑大纲 |
| `/api/v1/ppt/content` | POST | 填充内容 (并行LLM) |
| `/api/v1/ppt/export` | POST | 导出PPTX |
| `/api/v1/ppt/tts` | POST | TTS合成 |
| `/api/v1/ppt/render` | POST | 启动视频渲染 |
| `/api/v1/ppt/render/:id` | GET | 查询渲染状态 |
| `/api/v1/ppt/download/:id` | GET | 获取下载链接 |

---

## 五、核心模块

### 5.1 内容生成器 (`agent/src/premium_generator.py`)

**角色人设**: 制造业20年资深顾问「老周」
- 稳健专业，用数据和事实说话
- 车间视角：讲精度要说"比头发丝细几倍"
- 避雷指南：禁止赋能、闭环、抓手、颗粒度
- 技术方案强调补强传统工艺，非替代

**布局编排**: 强制相邻页不同布局
```python
layouts = ["cover", "bullet_points", "comparison", "quote", "big_number", "closing"]
# 第1页 cover，最后1页 closing，中间交替
```

**多样化script模板**: 8种随机选择
```python
SCRIPT_TEMPLATES = [
    "关于{title}，{items_str}。",
    "{title}这块，{items_str}。",
    "来看{title}，{items_str}。",
    ...
]
```

### 5.2 HTML 截图引擎 (`agent/src/screenshot_engine.py`)

**7种完全不同的模板**:

| 模板 | 布局 |
|------|------|
| cover | 全屏渐变+超大标题+装饰线 |
| bullet_points | 顶部标题栏+要点列表+右侧高亮框 |
| comparison | 红绿双栏对比 |
| big_number | 超大渐变数字+说明 |
| quote | 深色背景+大号引用 |
| grid_3 | 三列卡片 |
| closing | 致谢页 |

### 5.3 视频生成管线

```
1. 内容生成 (LLM) → slides[]
2. TTS合成 (Minimax) → audio_urls[] + durations[]
3. HTML截图 (Playwright) → slide_XX.png
4. 下载音频 → slide_XX.mp3
5. ffmpeg合成:
   - 每页创建视频片段 (图片+音频+fade-in/out)
   - concat合并所有片段
   - 输出 MP4 (H.264 + AAC)
```

### 5.4 TTS 合成器 (`agent/src/tts_synthesizer.py`)

- API: Minimax TTS (speech-2.6-turbo)
- 声音: 男声/女声可选
- 重试: 3次指数退避
- 并发: 全局 Semaphore=10

### 5.5 文档解析器 (`agent/src/document_parser.py`)

- PPTX: python-pptx (文本/图片/表格)
- PDF: pdfplumber (文本/表格)
- SSRF防护: IP黑名单+DNS解析校验
- 文件限制: 50MB最大

---

## 六、技术栈

| 组件 | 技术 |
|------|------|
| 后端 | Python FastAPI |
| LLM | OpenRouter (gpt-4o-mini) |
| TTS | Minimax (speech-2.6-turbo) |
| 存储 | Cloudflare R2 |
| 数据库 | Supabase |
| 截图 | Playwright Chromium |
| 视频 | ffmpeg (H.264 + AAC) |
| 前端 | Next.js + React + Tailwind CSS |
| 视频组件 | Remotion + @remotion/transitions |

---

## 七、生成效果

### 输出文件

```
test_outputs/lingchuang_v6/
├── video.mp4         (1.9MB, 视频)
├── slides.json       (完整数据)
├── slides/           (11张 1920×1080 截图)
└── audio/            (11条 TTS 音频)
```

### 布局分布 (灵创智能示例)

```
cover:         2页 — 封面+致谢
bullet_points: 3页 — 要点列表 (3-5条/页)
comparison:    2页 — 红绿对比 (传统vs灵创)
quote:         2页 — 金句引用
big_number:    2页 — 超大数字高亮
```

### 视频规格

```
分辨率: 1920×1080
编码: H.264 + AAC
转场: 每页 0.3s fade-in/fade-out
音频: TTS + 音频驱动时长
```

---

## 八、文件清单

```
agent/src/
├── schemas/ppt.py              # 数据模型
├── schemas/ppt_v3.py           # v3数据模型 (多角色+动作)
├── outline_generator.py        # 大纲生成器
├── content_generator.py        # 内容生成器
├── premium_generator.py        # Premium生成器 (7种模板+多样化script)
├── document_parser.py          # 文档解析器 (PPTX/PDF)
├── tts_synthesizer.py          # TTS合成器 (Minimax)
├── lambda_renderer.py          # Lambda渲染器
├── ppt_service.py              # PPT服务管理
├── ppt_routes.py               # PPT API路由
├── ppt_v3_routes.py            # v3 API路由
├── premium_routes.py           # Premium API路由
├── screenshot_engine.py        # HTML截图引擎 (7种模板)
└── r2.py                       # R2存储客户端

scripts/
├── run_ppt_v6.py               # 完整管线脚本
├── render-local.mjs            # Remotion本地渲染
└── generate-pptx.mjs           # PPTX导出

src/
├── lib/types/ppt.ts            # TypeScript类型
├── remotion/compositions/
│   ├── SlidePresentation.tsx   # Remotion视频组件
│   └── ImageSlideshow.tsx      # 截图幻灯片组件
└── components/
    ├── OutlineEditor.tsx        # 大纲编辑器
    ├── RenderProgress.tsx       # 渲染进度
    └── PPTPreview.tsx           # PPT预览

---

## 九、V7 改进 (Skill架构 + 并发工作流 + Marp双路输出)

### 9.1 Skill 目录架构（已清理）

```
已移除本地历史 PPT-video skill 目录（未接入运行时）
当前执行链路：agent/src/minimax_exporter.py -> scripts/generate-pptx-minimax.mjs
官方 skill 参考保留在：vendor/minimax-skills/skills/pptx-generator/
```

### 9.2 V7 并发工作流 (`premium_generator_v7.py`)

```
Phase 1 (串行 ~5s): 全局编排 → 大纲+版式分配
Phase 2 (并发 ~8s): 视觉映射 → 每页Markdown+Script (asyncio.gather)
Phase 3 (并发IO):   资源回填 → TTS+背景图
```

### 9.3 Marp 双路输出 (`marp_service_v7.py`)

```
markdown → marp-cli → PPTX (可编辑)
                   → PNG序列 (高清截图)
```

### 9.4 Remotion 截图序列 + Ken Burns 动效

```
PNG序列 + 音频 → Remotion Composition
  ├── ZoomIn: 缓慢推镜 (大数字/金句页)
  ├── PanLeft: 缓慢左移 (全屏背景图)
  └── Static: 静态 (要点页)
```

### 9.5 文本溢出校验

```python
def validate_text_length(markdown: str, max_chars: int = 60):
    text_only = re.sub(r'<[^>]+>', '', markdown)
    if len(text_only) > max_chars:
        raise ValueError(f"Screen text too long ({len(text_only)} chars)")
```

### 9.6 新增文件

```
agent/src/
├── premium_generator_v7.py    # V7并发工作流生成器
├── marp_service_v7.py         # Marp双路输出 (PPTX+PNG)
└── v7_routes.py               # V7 API路由

vendor/minimax-skills/
└── skills/pptx-generator/       # MiniMax 官方 skill 参考（vendor）

src/remotion/components/
└── Animations.tsx             # Ken Burns动效引擎 (ZoomIn/PanLeft/PanRight)
```
```
