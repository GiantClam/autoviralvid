# PPT讲解视频生成 - 最终实施方案 (v2)

> 整合自三份方案，拆分为**两个独立功能**：
> 1. **Feature A: PPT生成** — 对话式大纲 → 内容填充 → PPTX导出
> 2. **Feature B: PPT/PDF视频生成** — 导入PPT/PDF → Remotion讲解视频

---

## 一、功能拆分总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Feature A: PPT 生成                            │
│                                                                     │
│  用户对话 → 大纲生成 → 用户确认 → 内容填充 → PPTX导出 → R2存储       │
│                                                                     │
│  输入: 用户需求文本                                                   │
│  输出: .pptx 文件 (可编辑, 可下载)                                    │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ PPTX / 已有PPT / PDF
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Feature B: PPT/PDF 视频生成                        │
│                                                                     │
│  导入PPT/PDF → 解析内容 → Remotion组件 → Lambda渲染 → MP4视频       │
│                                                                     │
│  输入: .pptx / .ppt / .pdf 文件                                      │
│  输出: .mp4 讲解视频 (支持TTS + 转场 + 动画)                          │
└─────────────────────────────────────────────────────────────────────┘
```

### 技术栈
- 前端: Next.js + React + Zustand + Remotion Player
- 后端: Python FastAPI (现有 agent)
- 视频渲染: @remotion/lambda + AWS Lambda
- 存储: Cloudflare R2 (现有 `agent/src/r2.py`)
- 数据库: Supabase (现有)
- LLM: OpenRouter (现有 `openrouter_client.py`)
- PPT解析: python-pptx (PPTX), pdfplumber/PyMuPDF (PDF)

---

## 二、Feature A: PPT 生成

### 2.1 流程

```
用户输入需求 ("做一个Python入门10页PPT")
    │
    ▼
Stage 1: 大纲生成 (LLM + JSON Schema)
    │  → SlideOutline[] (标题/要点/预计时长)
    ▼
用户确认/编辑大纲
    │
    ▼
Stage 2: 内容生成 (并行 LLM)
    │  → SlideContent[] (元素/背景/讲解文本)
    ▼
Stage 3: PPTX导出 (pptxgenjs)
    │
    ▼
上传R2 → 返回下载链接
```

### 2.2 数据模型

**Python 端** (`agent/src/schemas/ppt.py`):

```python
class SlideOutline(BaseModel):
    id: str
    order: int
    title: str
    description: str
    key_points: List[str]
    suggested_elements: List[str]  # "text","image","chart","table","latex"
    estimated_duration: int  # seconds

class PresentationOutline(BaseModel):
    id: str
    title: str
    theme: str
    slides: List[SlideOutline]
    total_duration: int
    style: str  # "professional","education","creative"

class SlideElement(BaseModel):
    id: str
    type: str  # "text","image","shape","chart","table","latex"
    left: float; top: float; width: float; height: float
    content: Optional[str] = None
    src: Optional[str] = None
    style: Optional[Dict[str, Any]] = None

class SlideContent(BaseModel):
    id: str; outline_id: str; order: int; title: str
    elements: List[SlideElement]
    background: Optional[Dict[str, Any]] = None
    narration: str
    duration: int  # seconds
```

**TypeScript 端** (`src/lib/types/ppt.ts`):

```typescript
export interface SlideOutline { id, order, title, description, keyPoints[], suggestedElements[], estimatedDuration }
export interface PresentationOutline { id, title, theme, slides[], totalDuration, style }
export interface SlideElement { id, type, left, top, width, height, content?, src?, style? }
export interface SlideContent { id, outlineId, order, title, elements[], background?, narration, duration }
```

### 2.3 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/ppt/outline` | POST | 生成大纲 |
| `/api/v1/ppt/outline` | PUT | 编辑大纲 |
| `/api/v1/ppt/content` | POST | 填充内容(并行) |
| `/api/v1/ppt/export` | POST | 导出PPTX → R2 |
| `/api/v1/ppt/tts` | POST | TTS合成(可选) |

---

## 三、Feature B: PPT/PDF 视频生成

### 3.1 流程

```
用户上传 PPT/PDF 文件
    │
    ▼
Stage 1: 文件解析
    │  python-pptx / pdfplumber → SlideContent[]
    │  提取: 文本/图片/布局/备注
    ▼
Stage 2: 内容增强 (可选)
    │  LLM优化讲解文本(narration)
    │  TTS合成音频
    ▼
Stage 3: Remotion 渲染
    │  SlidePresentation 组件
    │  @remotion/transitions (fade/slide/wipe)
    │  元素动画 (spring + interpolate)
    ▼
Stage 4: Lambda 分布式渲染
    │  renderMediaOnLambda() → S3 chunks → combine → final.mp4
    ▼
上传R2 → 返回视频URL
```

### 3.2 数据模型

```python
# 复用 Feature A 的 SlideContent, SlideElement
# 新增:

class VideoRenderConfig(BaseModel):
    width: int = 1920
    height: int = 1080
    fps: int = 30
    transition: str = "fade"  # "fade","slide","wipe"
    bgm_url: Optional[str] = None
    bgm_volume: float = 0.15
    include_narration: bool = True

class ParsedDocument(BaseModel):
    """PPT/PDF解析结果"""
    source_type: str  # "pptx","ppt","pdf"
    source_url: str
    title: str
    slides: List[SlideContent]
    total_pages: int
```

### 3.3 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/video/parse` | POST | 解析PPT/PDF → SlideContent[] |
| `/api/v1/video/enhance` | POST | LLM增强讲解文本+TTS |
| `/api/v1/video/render` | POST | 启动Lambda渲染 |
| `/api/v1/video/render/{job_id}` | GET | 查询渲染状态 |
| `/api/v1/video/download/{job_id}` | GET | 下载视频(R2 presigned) |

### 3.4 文件解析

```python
# agent/src/document_parser.py

def parse_pptx(file_path: str) -> ParsedDocument:
    """使用 python-pptx 解析 .pptx 文件"""
    from pptx import Presentation
    prs = Presentation(file_path)
    slides = []
    for i, slide in enumerate(prs.slides):
        elements = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                elements.append(SlideElement(
                    type="text", content=shape.text_frame.text,
                    left=shape.left, top=shape.top,
                    width=shape.width, height=shape.height
                ))
            if shape.shape_type == 13:  # Picture
                elements.append(SlideElement(
                    type="image", src=extract_image(shape),
                    left=shape.left, top=shape.top,
                    width=shape.width, height=shape.height
                ))
        notes = slide.notes_slide.notes_text_frame.text if slide.has_notes_slide else ""
        slides.append(SlideContent(
            id=f"slide-{i}", order=i,
            title=extract_title(slide),
            elements=elements,
            narration=notes,
            duration=120  # 默认2分钟/页
        ))
    return ParsedDocument(source_type="pptx", slides=slides, ...)

def parse_pdf(file_path: str) -> ParsedDocument:
    """使用 pdfplumber/PyMuPDF 解析 PDF"""
    import pdfplumber
    # 提取每页文本+图片 → SlideContent[]
    ...

def parse_ppt(file_path: str) -> ParsedDocument:
    """.ppt → 先转 .pptx (libreoffice), 再解析"""
    ...
```

---

## 四、Remotion 视频组件 (Feature B 核心)

### 4.1 SlidePresentation 组件

```tsx
// src/remotion/compositions/SlidePresentation.tsx
// 使用 @remotion/transitions 的 TransitionSeries
// 每页: SingleSlide + 元素逐个动画(spring)
// 页间: fade/slide/wipe 转场
// 音频: TTS narration 同步 + BGM
```

### 4.2 元素渲染器

支持类型: text, image, chart, table, latex, shape

---

## 五、与现有项目集成

| 现有能力 | 新增 | 集成方式 |
|---------|------|---------|
| `agent/src/r2.py` | PPTX/视频上传 | 扩展 `upload_bytes_to_r2()` |
| `agent/src/openrouter_client.py` | 大纲/内容生成 | 直接复用 |
| `agent/src/api_routes.py` | PPT/视频路由 | 新增 router include |
| `src/lib/render/remotion-mapper.ts` | PPT元素映射 | 扩展 RenderLayer |
| `src/remotion/compositions/` | SlidePresentation | 新增组件 |
| `agent/src/project_service.py` | PPT项目类型 | 新增 template_type |

---

## 六、文件清单

### Feature A: PPT 生成

```
agent/src/
├── schemas/
│   └── ppt.py                     # 数据模型
├── outline_generator.py           # 大纲生成 (LLM)
├── content_generator.py           # 内容填充 (并行LLM)
├── ppt_service.py                 # PPT项目管理
├── ppt_routes.py                  # API路由
└── r2.py                          # 扩展: PPTX上传

前端 (Next.js):
src/lib/types/ppt.ts               # TypeScript类型
src/lib/export/pptx-generator.ts   # PPTX导出 (pptxgenjs)
```

### Feature B: PPT/PDF 视频生成

```
agent/src/
├── document_parser.py             # PPT/PDF解析
├── ppt_video_service.py           # 视频生成服务
└── lambda_renderer.py             # Lambda渲染调用

前端 (Next.js):
src/remotion/
├── compositions/
│   └── SlidePresentation.tsx      # Remotion视频组件
│   └── SlideElementRenderer.tsx   # 元素渲染器
└── index.ts                       # 注册入口

src/lib/render/
├── lambda-config.ts               # Lambda配置
└── lambda-renderer.ts             # 渲染触发器

scripts/
└── render-presentation.mjs        # Lambda渲染脚本
```

---

## 七、实施计划

### Phase 1: 数据模型 + 大纲/内容生成 (Feature A 核心) ← 当前
- Python数据模型、TypeScript类型
- 大纲生成器、内容生成器
- PPT服务管理、API路由

### Phase 2: PPTX导出 (Feature A 完成)
- pptxgenjs封装
- R2上传
- 下载接口

### Phase 3: 文档解析 (Feature B 核心)
- python-pptx解析
- pdfplumber/PyMuPDF解析
- 内容增强(LLM + TTS)

### Phase 4: Remotion视频组件 (Feature B 核心)
- SlidePresentation组件
- 元素渲染器
- 转场效果

### Phase 5: Lambda渲染集成 (Feature B 完成)
- Lambda部署
- 渲染脚本
- R2视频上传
- 进度跟踪

### Phase 6: 前端UI
- 大纲确认界面
- PPT预览
- 视频渲染进度
- 文件上传组件
