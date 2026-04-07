# PPT + Remotion 讲解视频全链路方案

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现"对话式大纲生成 → 内容填充 → PPT导出 → Remotion讲解视频生成"全链路，通过 AWS Lambda 分布式渲染 + Cloudflare R2 存储，支持最长 40 分钟长视频。

**Architecture:** 两阶段生成流水线（大纲 + 内容），PPT 与视频共享同一内容源，Remotion Lambda 分布式渲染自动分片并行，渲染结果上传 Cloudflare R2。

**Tech Stack:** React, Remotion (@remotion/transitions, renderMediaOnLambda), svg_to_pptx, AWS Lambda, Cloudflare R2 (S3-compatible), FastAPI, Supabase

---

## 一、整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户对话界面                              │
│  "帮我做一个关于量子计算入门的10页PPT讲解视频"                     │
└───────────────────────┬─────────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────────┐
│                  Stage 1: 大纲生成 (Outline)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ 意图理解      │→│ 结构化大纲    │→│ 大纲确认/编辑  │           │
│  │ (LLM Chat)   │  │ (JSON Schema)│  │ (UI交互)     │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└───────────────────────┬─────────────────────────────────────────┘
                        │ Outline[]
┌───────────────────────▼─────────────────────────────────────────┐
│                  Stage 2: 内容生成 (Content)                      │
│  ┌──────────────────────────────────────────────────────┐       │
│  │              并行生成 (Promise.all)                    │       │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐    │       │
│  │  │ Slide 1 │ │ Slide 2 │ │ Slide 3 │ │ Slide N │    │       │
│  │  │ 元素生成 │ │ 元素生成 │ │ 元素生成 │ │ 元素生成 │    │       │
│  │  │ + TTS   │ │ + TTS   │ │ + TTS   │ │ + TTS   │    │       │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘    │       │
│  └──────────────────────────────────────────────────────┘       │
│                        │                                         │
│  ┌─────────────────────▼─────────────────────────────────┐      │
│  │  SlideContent[] = {                                    │      │
│  │    elements: [text, image, shape, chart, table, latex] │      │
│  │    background, narration: string, duration: number     │      │
│  │  }                                                     │      │
│  └────────────────────────────────────────────────────────┘      │
└───────┬────────────────────────┬────────────────────────────────┘
        │                        │
┌───────▼────────────┐  ┌───────▼────────────────────────────────┐
│  Stage 3a: PPT导出  │  │  Stage 3b: Remotion Lambda 渲染         │
│                     │  │                                         │
│  FastAPI 后端       │  │  ┌───────────────────────────────────┐  │
│  svg_to_pptx          │  │  │  renderMediaOnLambda()            │  │
│  ↓                  │  │  │                                   │  │
│  slides.pptx → R2   │  │  │  自动分片 → 并行 Lambda 渲染       │  │
│                     │  │  │  ┌─────┐ ┌─────┐     ┌─────┐     │  │
│                     │  │  │  │chunk│ │chunk│ ... │chunk│     │  │
│                     │  │  │  │  0  │ │  1  │     │  N  │     │  │
│                     │  │  │  └──┬──┘ └──┬──┘     └──┬──┘     │  │
│                     │  │  │     └───┬───┘           │         │  │
│                     │  │  │         ▼               │         │  │
│                     │  │  │     combineChunks()     │         │  │
│                     │  │  │         │               │         │  │
│                     │  │  │         ▼               │         │  │
│                     │  │  │     final.mp4           │         │  │
│                     │  │  │         │               │         │  │
│                     │  │  │         ▼               │         │  │
│                     │  │  │     Cloudflare R2       │         │  │
│                     │  │  └───────────────────────────────────┘  │
│                     │  │                                         │
│                     │  │  进度跟踪: Supabase (webhook/callback)   │
└─────────────────────┘  └────────────────────────────────────────┘
```

---

## 二、核心数据模型

### 2.1 大纲层

```typescript
interface SlideOutline {
  id: string;
  order: number;
  title: string;
  description: string;
  keyPoints: string[];
  suggestedElements: ElementType[];
  estimatedDuration: number; // seconds
}

interface PresentationOutline {
  id: string;
  title: string;
  theme: string;
  slides: SlideOutline[];
  totalDuration: number;      // seconds
  style: PresentationStyle;
  createdAt: string;
}
```

### 2.2 内容层

```typescript
type SlideElement =
  | TextElement | ImageElement | ShapeElement
  | ChartElement | TableElement | LatexElement;

interface TextElement {
  type: 'text';
  id: string;
  content: string;          // HTML富文本
  left: number; top: number;
  width: number; height: number;
  style: TextStyle;
}

interface ImageElement {
  type: 'image';
  id: string;
  src: string;              // R2 CDN URL
  left: number; top: number;
  width: number; height: number;
  objectFit?: 'cover' | 'contain';
}

interface ChartElement {
  type: 'chart';
  id: string;
  chartType: 'bar' | 'line' | 'pie' | 'doughnut' | 'radar' | 'area';
  data: ChartData;
  left: number; top: number;
  width: number; height: number;
}

interface TableElement {
  type: 'table';
  id: string;
  rows: string[][];
  colWidths?: number[];
  style: TableStyle;
  left: number; top: number;
  width: number; height: number;
}

interface LatexElement {
  type: 'latex';
  id: string;
  formula: string;
  left: number; top: number;
  width: number; height: number;
  fontSize?: number;
}

interface SlideContent {
  id: string;
  outlineId: string;
  order: number;
  title: string;
  elements: SlideElement[];
  background: Background;
  narration: string;
  narrationAudioUrl?: string;  // R2 CDN URL
  duration: number;            // seconds
}
```

### 2.3 渲染层

```typescript
// Lambda 渲染输入
interface RemotionSlidePresentation {
  slides: SlideContent[];
  bgmUrl?: string;            // R2 CDN URL
  bgmVolume?: number;
  defaultTransition?: 'fade' | 'slide' | 'wipe';
}

// 渲染任务 (存储在 Supabase)
interface RenderJob {
  id: string;
  projectId: string;
  status: 'pending' | 'rendering' | 'done' | 'failed';
  progress: number;           // 0-1
  lambdaJobId?: string;
  error?: string;
  outputUrl?: string;         // R2 CDN URL
  createdAt: string;
  updatedAt: string;
}
```

---

## 三、AWS Lambda 分布式渲染

### 3.1 核心优势

Remotion Lambda 自动将长视频拆分为多个 chunk，分布到多个 Lambda 函数并行渲染，再自动合并。

| 维度 | Remotion Lambda | 浏览器分段 | 单机 FFmpeg |
|------|----------------|-----------|------------|
| 40min 渲染耗时 | **2-5 分钟** (并行) | 30-40 分钟 | 20-30 分钟 |
| 可靠性 | 高 (AWS 自动重试) | 中 (用户设备) | 中 |
| 内存风险 | 无 (每 chunk 独立) | 高 (长视频 OOM) | 高 |
| 实现复杂度 | 低 (开箱即用) | 高 | 中 |
| 成本 | ~$0.02-0.08/min | 免费 | 免费 |

### 3.2 渲染流程

```
1. 前端调用 POST /api/v1/projects/:id/render
       │
2. 后端 (FastAPI) 构建 inputProps (SlideContent[])
       │
3. 调用 renderMediaOnLambda() 异步启动
       │
   ┌───▼───────────────────────────────────────┐
   │  renderMediaOnLambda({                     │
   │    functionName: 'remotion-render',        │
   │    serveUrl: 'https://s3/serve-bundle',    │
   │    composition: 'SlidePresentation',       │
   │    inputProps: { slides: [...] },          │
   │    codec: 'h264',                          │
   │    outName: '{run_id}_video.mp4',          │
   │    framesPerLambda: 100,  // ~3.3s/chunk   │
   │    concurrency: 10,       // 10 并行 Lambda │
   │  })                                        │
   │                                            │
   │  内部流程:                                  │
   │  1. 将 inputProps + bundle 上传到 S3        │
   │  2. 按 framesPerLambda 分片帧范围           │
   │  3. 并发启动 N 个 Lambda 渲染 chunk          │
   │  4. 每个 Lambda:                            │
   │     - 启动 headless Chrome                  │
   │     - 渲染指定帧范围                         │
   │     - 编码为 MP4 chunk                      │
   │     - 上传 chunk 到 S3                      │
   │  5. 所有 chunk 完成后自动合并                │
   │  6. 最终视频上传到指定位置                    │
   └───────────────────────────────────────────┘
       │
4. 返回 renderMediaOnLambda() 结果
   - outputFile: 最终视频路径/URL
   - costsInDollars: 费用
   - renderId: 唯一渲染 ID
       │
5. 后端将最终视频上传到 Cloudflare R2
       │
6. 更新 Supabase 任务状态 + video_url
```

### 3.3 Remotion Lambda 配置

```typescript
// agent/src/remotion_lambda.py (通过 Node.js 子进程调用)
// 或使用 remotion CLI

// === Remotion Lambda 渲染脚本 ===
// scripts/render-presentation.ts

import { renderMediaOnLambda } from '@remotion/lambda-client';
import { bundle } from '@remotion/bundler';

export async function renderPresentation(
  slides: SlideContent[],
  outputKey: string,
  webhookUrl?: string
): Promise<{ videoUrl: string; renderId: string }> {
  // 1. 打包 Remotion bundle (可复用，缓存到 S3)
  const serveUrl = await getCachedBundle();

  // 2. 调用 Lambda 渲染
  const result = await renderMediaOnLambda({
    functionName: process.env.REMOTION_LAMBDA_FUNCTION!,
    region: process.env.AWS_REGION!,
    serveUrl,
    composition: 'SlidePresentation',
    inputProps: { slides },
    codec: 'h264',
    outName: outputKey,
    framesPerLambda: 100,       // 每个 Lambda 渲染 ~3.3 秒
    maxRetriesPerLambda: 2,     // 每 chunk 最多重试 2 次
    privacy: 'public',

    // Webhook 回调 (可选，用于实时进度)
    webhook: webhookUrl ? {
      url: webhookUrl,
      secret: process.env.WEBHOOK_SECRET,
    } : undefined,
  });

  return {
    videoUrl: result.bucketName
      ? `s3://${result.bucketName}/${result.renderId}/${outputKey}`
      : result.outputFile!,
    renderId: result.renderId,
  };
}

async function getCachedBundle(): Promise<string> {
  // 检查 S3 是否已有缓存 bundle
  // 若无则打包并上传
  const bundleLocation = await bundle({
    entryPoint: './src/remotion/index.ts',
    webpackOverride: (config) => config,
  });
  // upload to S3, return serveUrl
  return bundleLocation;
}
```

### 3.4 成本估算

```
假设: 40 分钟视频, 1920×1080, 30fps = 72,000 帧

Lambda 配置:
- 内存: 2048 MB (Remotion 推荐)
- framesPerLambda: 100
- 并发: 10 个 Lambda

单 Lambda 费用:
- 72,000 / 100 = 720 chunks
- 每 chunk 渲染约 10-15 秒
- 720 × 15s = 10,800 Lambda-seconds
- 分摊到 10 并发: 1,080 实际秒
- Lambda 费用: 1080s × 2GB × $0.0000166667/s ≈ $0.036
- S3 读写: ~$0.01

总计: ~$0.05-0.10 / 40分钟视频

对比浏览器渲染: $0 但耗时 30-40 分钟且不稳定
```

---

## 四、Cloudflare R2 存储策略

### 4.1 已有集成

项目已深度集成 R2 (`agent/src/r2.py`)：
- `get_r2_client()` — boto3 S3 客户端
- `upload_url_to_r2()` — 上传任意 URL 内容到 R2
- `presign_put_url()` — 预签名上传 URL

### 4.2 存储路径规划

```
R2 Bucket: video/
├── projects/
│   └── {project_id}/
│       ├── outline.json           # 大纲数据
│       ├── slides/
│       │   ├── slide_0.json       # 每页内容
│       │   ├── slide_1.json
│       │   └── ...
│       ├── assets/
│       │   ├── img_0.png          # 生成的图片
│       │   ├── audio_0.mp3        # TTS 音频
│       │   └── ...
│       ├── pptx/
│       │   └── presentation.pptx  # 导出的 PPT
│       └── video/
│           └── final.mp4          # 最终视频

# Remotion Lambda 使用的 S3 (AWS)
remotion-serve/
├── bundles/
│   └── {bundle_hash}/            # Remotion 打包
└── renders/
    └── {render_id}/
        ├── chunks/
        │   ├── chunk-0.mp4
        │   └── ...
        └── final.mp4
```

### 4.3 R2 上传封装

```python
# agent/src/r2.py (扩展现有模块)

async def upload_bytes_to_r2(
    data: bytes, key: str,
    content_type: str = "application/octet-stream",
    bucket: str = None
) -> str:
    """上传字节数据到 R2，返回公网 CDN URL"""
    bucket = bucket or os.getenv("R2_BUCKET", "video")
    r2 = get_r2_client()
    if not r2:
        raise RuntimeError("R2 is not configured")
    r2.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
    public_base = os.getenv("R2_PUBLIC_BASE")
    if public_base:
        return f"{public_base.rstrip('/')}/{key}"
    account_id = os.getenv("R2_ACCOUNT_ID")
    return f"https://pub-{account_id}.r2.dev/{key}"


async def upload_pptx_to_r2(pptx_buffer: bytes, project_id: str) -> str:
    """上传 PPTX 到 R2"""
    key = f"projects/{project_id}/pptx/presentation.pptx"
    return await upload_bytes_to_r2(pptx_buffer, key, "application/vnd.openxmlformats-officedocument.presentationml.presentation")


async def upload_final_video_from_s3(
    s3_bucket: str, s3_key: str, project_id: str
) -> str:
    """从 AWS S3 (Lambda 渲染输出) 拉取视频并上传到 R2"""
    import boto3
    aws_s3 = boto3.client("s3")
    obj = aws_s3.get_object(Bucket=s3_bucket, Key=s3_key)
    video_bytes = obj["Body"].read()
    r2_key = f"projects/{project_id}/video/final.mp4"
    return await upload_bytes_to_r2(video_bytes, r2_key, "video/mp4")
```

---

## 五、Remotion 组件设计

### 5.1 SlidePresentation 组件

```tsx
// src/remotion/compositions/SlidePresentation.tsx
import React from 'react';
import {
  AbsoluteFill, Sequence, Audio, Img,
  interpolate, useCurrentFrame, useVideoConfig, spring,
} from 'remotion';
import { TransitionSeries, linearTiming } from '@remotion/transitions';
import { fade } from '@remotion/transitions/fade';
import { slide } from '@remotion/transitions/slide';

export interface SlidePresentationProps {
  slides: SlideContent[];
  bgmUrl?: string;
  bgmVolume?: number;
  defaultTransition?: 'fade' | 'slide' | 'wipe';
}

export default function SlidePresentation({
  slides,
  bgmUrl,
  bgmVolume = 0.3,
  defaultTransition = 'fade',
}: SlidePresentationProps) {
  const { fps } = useVideoConfig();

  const transitionFn = defaultTransition === 'fade' ? fade() :
    defaultTransition === 'slide' ? slide() : fade();

  return (
    <AbsoluteFill style={{ backgroundColor: '#000000' }}>
      <TransitionSeries>
        {slides.map((s, idx) => (
          <React.Fragment key={idx}>
            <TransitionSeries.Sequence
              durationInFrames={Math.round(s.duration * fps)}
            >
              <SingleSlide content={s} />
            </TransitionSeries.Sequence>

            {idx < slides.length - 1 && (
              <TransitionSeries.Transition
                presentation={transitionFn}
                timing={linearTiming({ durationInFrames: Math.round(0.5 * fps) })}
              />
            )}
          </React.Fragment>
        ))}
      </TransitionSeries>

      {/* TTS Audio tracks synced per slide */}
      {slides.map((s, idx) => {
        if (!s.narrationAudioUrl) return null;
        const startFrame = slides.slice(0, idx)
          .reduce((sum, sl) => sum + Math.round(sl.duration * fps), 0);
        return (
          <Sequence
            key={`audio-${idx}`}
            from={startFrame}
            durationInFrames={Math.round(s.duration * fps)}
          >
            <Audio src={s.narrationAudioUrl} />
          </Sequence>
        );
      })}

      {bgmUrl && <Audio src={bgmUrl} volume={bgmVolume} />}
    </AbsoluteFill>
  );
}
```

### 5.2 SingleSlide + 元素动画

```tsx
function SingleSlide({ content }: { content: SlideContent }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill style={{ backgroundColor: content.background?.color || '#ffffff' }}>
      {content.background?.imageUrl && (
        <Img
          src={content.background.imageUrl}
          style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.3 }}
        />
      )}

      {content.elements.map((el, idx) => {
        const enterDelay = Math.round(idx * 0.3 * fps);
        const progress = spring({
          frame: frame - enterDelay,
          fps,
          config: { damping: 15, stiffness: 120 },
        });

        return (
          <div
            key={el.id}
            style={{
              position: 'absolute',
              left: el.left, top: el.top,
              width: el.width, height: el.height,
              opacity: interpolate(progress, [0, 1], [0, 1], { extrapolateRight: 'clamp' }),
              transform: `translateY(${interpolate(progress, [0, 1], [30, 0], { extrapolateRight: 'clamp' })}px)`,
            }}
          >
            <SlideElementRenderer element={el} />
          </div>
        );
      })}

      <div style={{
        position: 'absolute', top: 40, left: 60,
        fontSize: 36, fontWeight: 'bold',
        color: '#333333', fontFamily: 'sans-serif',
      }}>
        {content.title}
      </div>
    </AbsoluteFill>
  );
}

function SlideElementRenderer({ element }: { element: SlideElement }) {
  switch (element.type) {
    case 'text':
      return (
        <div
          style={{
            fontSize: element.style.fontSize,
            color: element.style.color,
            fontWeight: element.style.fontWeight,
            fontFamily: element.style.fontFamily || 'sans-serif',
            lineHeight: 1.6,
          }}
          dangerouslySetInnerHTML={{ __html: element.content }}
        />
      );
    case 'image':
      return (
        <Img
          src={element.src}
          style={{ width: '100%', height: '100%', objectFit: element.objectFit || 'cover', borderRadius: 8 }}
        />
      );
    case 'chart':
      return <ChartRenderer data={element.data} type={element.chartType} />;
    case 'table':
      return <TableRenderer rows={element.rows} style={element.style} />;
    case 'latex':
      return <LatexRenderer formula={element.formula} fontSize={element.fontSize} />;
    default:
      return null;
  }
}
```

---

## 六、PPT 导出 (svg_to_pptx)

参考 OpenMAIC 的 `lib/export/use-export-pptx.ts`。

```typescript
// src/lib/export/use-export-pptx.ts
import pptxgen from 'svg_to_pptx';

export async function exportToPPTX(
  slides: SlideContent[],
  metadata: { title: string; author: string }
): Promise<Blob> {
  const pptx = new pptxgen();
  pptx.title = metadata.title;
  pptx.author = metadata.author;
  pptx.layout = 'LAYOUT_16x9';

  for (const slide of slides) {
    const pptxSlide = pptx.addSlide();
    if (slide.background?.color) {
      pptxSlide.background = { color: slide.background.color.replace('#', '') };
    }
    for (const el of slide.elements) {
      const pos = { x: el.left / 96, y: el.top / 96, w: el.width / 96, h: el.height / 96 };
      switch (el.type) {
        case 'text':
          slide.addText(formatHTML(el.content), {
            ...pos, fontSize: el.style.fontSize,
            color: el.style.color?.replace('#', ''),
            fontFace: el.style.fontFamily,
            bold: el.style.fontWeight === 'bold',
            valign: 'top', wrap: true,
          });
          break;
        case 'image':
          slide.addImage({ path: el.src, ...pos });
          break;
        case 'chart': {
          const chartTypeMap: Record<string, any> = {
            bar: pptxgen.ChartType.bar,
            line: pptxgen.ChartType.line,
            pie: pptxgen.ChartType.pie,
            doughnut: pptxgen.ChartType.doughnut,
            radar: pptxgen.ChartType.radar,
            area: pptxgen.ChartType.area,
          };
          const chartData = el.data.datasets.map(ds => ({
            name: ds.label, labels: el.data.labels, values: ds.data,
          }));
          slide.addChart(chartTypeMap[el.chartType], chartData, { ...pos, showLegend: true });
          break;
        }
        case 'table': {
          const rows = el.rows.map(row => row.map(cell => ({
            text: cell,
            options: { fontSize: el.style?.fontSize || 12 },
          })));
          slide.addTable(rows, { ...pos, colW: el.colWidths, border: { type: 'solid', pt: 0.5 } });
          break;
        }
        case 'latex': {
          const omml = await latexToOmml(el.formula);
          slide.addFormula({ omml }, pos);
          break;
        }
      }
    }
  }
  return pptx.write({ outputType: 'blob' }) as Promise<Blob>;
}
```

---

## 七、与现有项目集成

### 7.1 集成点映射

| 当前能力 | 新增能力 | 集成方式 |
|---------|---------|---------|
| `agent/agent_skills.py` 故事板生成 | 大纲生成 | 扩展支持 `template_type="ppt_presentation"` |
| `agent/project_service.py` 项目生命周期 | PPT 项目类型 | 新增大纲/内容/渲染生命周期步骤 |
| `agent/src/r2.py` R2 上传 | PPTX/视频上传 | 扩展 `upload_pptx_to_r2()` |
| `src/lib/render/remotion-mapper.ts` | PPT 元素映射 | 扩展 `RenderLayer` 支持 chart/table/latex |
| `src/remotion/compositions/` 模板系统 | SlidePresentation | 新增 `SlidePresentation.tsx` |
| `src/components/VideoEditor/` | PPT 编辑器 | 新增 `SlideEditor/` 组件 |

### 7.2 新增 API

```
POST /api/v1/projects                    — 创建PPT项目 (template_type="ppt_presentation")
POST /api/v1/projects/:id/outline        — 生成大纲
PUT  /api/v1/projects/:id/outline        — 编辑大纲
POST /api/v1/projects/:id/content        — 填充内容 (并行生成所有幻灯片+TTS)
POST /api/v1/projects/:id/export/pptx    — 导出PPTX (上传到 R2, 返回下载链接)
POST /api/v1/projects/:id/render         — 启动 Remotion Lambda 渲染
GET  /api/v1/projects/:id/render/status  — 查询渲染状态 (从 Supabase 读取)
GET  /api/v1/projects/:id/video/download — 下载最终视频 (R2 presigned URL)
```

### 7.3 新增模块

```
agent/src/
├── outline_generator.py          # Stage 1: 大纲生成 (LLM + JSON Schema)
├── content_generator.py          # Stage 2: 内容填充 (并行)
├── presentation_service.py       # PPT 项目生命周期管理
├── tts_synthesizer.py            # TTS 旁白合成
├── pptx_exporter.py              # PPT 导出 (Python 端调用 svg_to_pptx 或原生实现)
└── lambda_renderer.py            # Remotion Lambda 渲染调用

src/
├── lib/export/
│   ├── use-export-pptx.ts        # PPT 导出前端逻辑
│   ├── html-parser.ts            # HTML→PPTX 文本转换
│   └── latex-converter.ts        # LaTeX→OMML 转换
├── remotion/
│   ├── compositions/
│   │   └── SlidePresentation.tsx # Remotion 讲解视频组件
│   └── index.ts                  # Remotion 入口 (注册 SlidePresentation)
├── components/
│   ├── SlideEditor/              # PPT 编辑器
│   └── OutlineEditor/            # 大纲编辑器
└── app/api/
    ├── export/pptx/route.ts      # PPTX 导出 API
    └── render/
        ├── jobs/route.ts          # 渲染任务 (扩展现有端点)
        └── status/[id]/route.ts   # 渲染状态查询
```

### 7.4 Lambda 渲染调用 (后端)

```python
# agent/src/lambda_renderer.py

import subprocess
import json
import os
import logging

logger = logging.getLogger("lambda_renderer")


async def start_lambda_render(
    project_id: str,
    slides: list[dict],
    webhook_url: str = None
) -> dict:
    """
    启动 Remotion Lambda 渲染。
    通过调用 Node.js 脚本实现 (remotion CLI)。
    """
    # 将 slides 数据写入临时文件
    input_file = f"/tmp/render_input_{project_id}.json"
    with open(input_file, "w") as f:
        json.dump({"slides": slides}, f)

    render_output_key = f"projects/{project_id}/video/final.mp4"

    cmd = [
        "node", "scripts/render-presentation.mjs",
        "--input", input_file,
        "--outName", render_output_key,
    ]
    if webhook_url:
        cmd.extend(["--webhook", webhook_url])

    env = {
        **os.environ,
        "REMOTION_LAMBDA_FUNCTION": os.getenv("REMOTION_LAMBDA_FUNCTION", ""),
        "AWS_REGION": os.getenv("AWS_REGION", "us-east-1"),
        "REMOTION_SERVE_URL": os.getenv("REMOTION_SERVE_URL", ""),
    }

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        logger.error(f"Lambda render failed: {stderr.decode()}")
        raise RuntimeError(f"Lambda render failed: {stderr.decode()}")

    result = json.loads(stdout.decode())
    return {
        "render_id": result["renderId"],
        "video_url": result["videoUrl"],
        "cost": result.get("costsInDollars", 0),
    }


async def upload_rendered_video_to_r2(
    s3_bucket: str, s3_key: str, project_id: str
) -> str:
    """将 Lambda 渲染结果从 AWS S3 迁移到 Cloudflare R2"""
    from src.r2 import upload_bytes_to_r2
    import boto3

    aws_s3 = boto3.client("s3")
    obj = aws_s3.get_object(Bucket=s3_bucket, Key=s3_key)
    video_bytes = obj["Body"].read()

    r2_key = f"projects/{project_id}/video/final.mp4"
    return await upload_bytes_to_r2(video_bytes, r2_key, "video/mp4")
```

### 7.5 Remotion CLI 渲染脚本

```javascript
// scripts/render-presentation.mjs
import { bundle } from '@remotion/bundler';
import { renderMediaOnLambda } from '@remotion/lambda-client';
import { parseArgs } from 'node:util';

const { values } = parseArgs({
  options: {
    input: { type: 'string' },
    outName: { type: 'string' },
    webhook: { type: 'string', default: undefined },
  },
});

const input = JSON.parse(await import('node:fs').then(fs => fs.readFileSync(values.input, 'utf-8')));

// Bundle Remotion project (with caching)
const serveUrl = process.env.REMOTION_SERVE_URL || await bundle({
  entryPoint: './src/remotion/index.ts',
  webpackOverride: (config) => config,
});

const result = await renderMediaOnLambda({
  functionName: process.env.REMOTION_LAMBDA_FUNCTION,
  region: process.env.AWS_REGION,
  serveUrl,
  composition: 'SlidePresentation',
  inputProps: input,
  codec: 'h264',
  outName: values.outName,
  framesPerLambda: 100,
  maxRetriesPerLambda: 2,
  privacy: 'public',
  webhook: values.webhook ? { url: values.webhook } : undefined,
});

process.stdout.write(JSON.stringify({
  renderId: result.renderId,
  videoUrl: result.outputFile,
  costsInDollars: result.costsInDollars,
}));
```

---

## 八、技术选型总结

| 组件 | 方案 | 说明 |
|------|------|------|
| 大纲生成 | **LLM + JSON Schema** | 扩展现有 `plan_storyboard_impl()` |
| 内容生成 | **LLM 并行填充** | 每页独立调用，Promise.all |
| PPT 导出 | **svg_to_pptx** | OpenMAIC 验证，图表/表格/LaTeX 支持 |
| 视频组件 | **Remotion SlidePresentation** | TransitionSeries + 元素动画 |
| 渲染引擎 | **renderMediaOnLambda** | 分布式并行，自动分片+合并 |
| 渲染存储 | **AWS S3** (Lambda 临时) | Remotion Lambda 内部使用 |
| 最终存储 | **Cloudflare R2** | 项目已有集成，PPTX + 视频统一存储 |
| 进度跟踪 | **Supabase** | 现有任务队列体系，Webhook 回调 |
| TTS | **现有 agent TTS** | 复用数字人语音合成链路 |

---

## 九、实施路径

### Phase 1: 数据模型 + 大纲生成 (1 周)
- 定义 SlideOutline, SlideContent, SlideElement 类型
- 实现 `outline_generator.py` (LLM + JSON Schema)
- 实现 `content_generator.py` (并行填充)
- API 端点 + 基础 UI

### Phase 2: PPT 导出 (1 周)
- 前端集成 svg_to_pptx
- 实现 HTML→PPTX 文本转换
- 实现图表/表格/LaTeX 导出
- 后端 `pptx_exporter.py` + R2 上传
- 下载接口

### Phase 3: Remotion 视频组件 (1 周)
- 实现 `SlidePresentation.tsx`
- 实现 `SingleSlide` + 元素动画
- 集成 `@remotion/transitions`
- TTS 音频同步
- Remotion 入口注册

### Phase 4: Lambda 渲染集成 (1 周)
- 部署 Remotion Lambda 函数
- 打包 Remotion bundle 并上传 S3
- 实现 `lambda_renderer.py`
- 实现渲染脚本 `render-presentation.mjs`
- R2 最终视频上传
- Supabase 进度跟踪 + Webhook

### Phase 5: 集成 + 测试 (1 周)
- 端到端流程联调
- Lambda 并发/超时/重试调优
- R2 CDN 缓存策略
- 边界情况处理
- 文档完善
