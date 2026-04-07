# PPT + 视频生成方案文档 v2.0

## 项目背景

基于当前项目的视频生成能力，扩展支持：
1. 对话式 PPT 生成（用户输入需求 → 大纲确认 → PPT 导出）
2. 基于 PPT 的讲解视频生成（Remotion Lambda 渲染）
3. 浏览器端分段渲染（作为降级方案，支持最长 40 分钟视频）

**技术栈**：
- 前端：Next.js + Vercel AI SDK
- 后端：Python FastAPI (Railway CPU)
- 视频渲染：AWS Lambda + @remotion/lambda
- 视频存储：Cloudflare R2 (现有)

---

## 一、系统架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  前端 (Next.js)                                                           │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐ │
│  │ 对话输入    │→│ 大纲确认    │→│ PPT 导出    │→│ 视频渲染进度       │ │
│  │             │ │ (修改/确认) │ │ (.pptx)     │ │ (轮询状态)         │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  Railway CPU (现有)                                                       │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────────────┐ │
│  │ /api/outline    │→│ /api/pptx      │→│ /api/render/lambda       │ │
│  │ (大纲生成)       │  │ (PPT生成)       │  │ (触发 Lambda 渲染)        │ │
│  └─────────────────┘ └─────────────────┘ └─────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  AWS Lambda (Remotion)                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │  自动分段渲染 → 每段输出到 R2                                            │ │
│  │  Chromium + FFmpeg (Remotion 官方镜像)                                  │ │
│  │  15分钟/段 (自动分段)                                                   │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  Cloudflare R2 (现有存储)                                                 │
│  视频文件存储 → public URL / presigned URL                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、功能模块

### 2.1 对话式大纲生成

**目标**：用户输入需求，AI 生成可修改确认的大纲

```typescript
// 用户输入
{ "requirement": "Python 入门教程", "language": "zh-CN" }

// AI 返回大纲
{
  "outlines": [
    {
      "id": "scene_1",
      "title": "变量和数据类型",
      "description": "介绍 Python 的基本数据类型",
      "keyPoints": ["变量定义", "整数和浮点数", "字符串", "布尔值"],
      "mediaGenerations": [
        { "type": "image", "prompt": "Python 变量概念图", "aspectRatio": "16:9" }
      ],
      "estimatedDuration": 120
    }
  ]
}
```

**用户确认界面**：
- 大纲列表展示（可编辑标题/描述）
- 知识点增删
- 媒体生成标记
- [上一步] [确认生成 PPT] 按钮

---

### 2.2 PPT 导出

**输出格式**：`.pptx`（可编辑）

| 功能 | 说明 |
|------|------|
| 文本 | HTML 富文本 → PPTX 文本属性 |
| 图片 | 支持本地/远程 URL |
| 视频 | 嵌入视频 + 封面图 |
| LaTeX 公式 | temml → MathML → OMML（可编辑） |
| Shape | SVG Path → pptxgen custom geometry |
| Chart | 柱状图/折线图/饼图 |
| Table | 合并单元格、边框、主题色 |
| Speaker Notes | 演讲者备注 |

**核心依赖**：
- `svg_to_pptx` - PPT 生成
- `temml` - LaTeX → MathML
- `mathml2omml` - MathML → OMML

---

### 2.3 视频生成

**输入**：PPT 内容 + Actions（讲解动作）

**Actions 类型**：
| Action | 效果 |
|--------|------|
| `speech` | 字幕 + TTS 音频 |
| `spotlight` | 高亮元素 + 放大动画 |
| `draw` | 笔画绘制动画 |
| `discussion` | Agent 对话切换 |

**Remotion Lambda 渲染**：
- 文本层
- 图片层
- 视频层
- 音频层（TTS + 背景音乐）
- 转场效果（fade/slide/wipe）

---

### 2.4 AWS Lambda 渲染

**设计目标**：
- 最长支持 40 分钟视频
- 自动分段（15 分钟/段）
- 输出到 Cloudflare R2
- 按需计费

**分段策略**：
| 总时长 | 段数 | 每段时长 | Lambda 超时 |
|--------|------|----------|-------------|
| 10 分钟 | 1 | 10 分钟 | 1 个 Lambda |
| 20 分钟 | 2 | 10 分钟 | 2 个 Lambda |
| 40 分钟 | 3 | 13-14 分钟 | 3 个 Lambda |

**渲染流程**：
```
用户点击 "生成视频"
    ↓
┌───────────────────────────┐
│ Railway CPU                 │
│ /api/render/lambda         │
└─────────────┬─────────────┘
              ↓
┌─────────────────────────────────────────────────────────┐
│  AWS Lambda (Remotion)                                   │
│  ┌─────────────────────────────────────────────────────┐│
│  │  deployFunction() → 部署 Lambda 函数 (首次)        ││
│  │  renderMediaOnLambda() → 触发渲染                  ││
│  └─────────────────────────────────────────────────────┘│
└─────────────┬───────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────┐
│  Lambda 1 (0-15min)    ──▶ R2                         │
│  Lambda 2 (15-30min)   ──▶ R2                         │
│  Lambda 3 (30-40min)   ──▶ R2                         │
│           ↓                                              │
│  Lambda 合并 → final.mp4 → R2                          │
└─────────────┬───────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────┐
│  Cloudflare R2                                          │
│  生成下载链接                                            │
└─────────────────────────────────────────────────────────┘
```

---

### 2.5 浏览器端分段渲染（降级方案）

当 Lambda 不可用时，使用浏览器端渲染作为降级：

**设计目标**：
- 每段 < 2 分钟，保证浏览器稳定性
- 保留转场效果
- 断点续传

**渲染流程**：
```
用户点击 "生成视频"
    ↓
┌───────────────────────────┐
│ 设备检测                    │
│ GPU / 内存评估             │
└─────────────┬─────────────┘
              ↓
┌───────────────────────────┐
│ 分段控制器                 │ 40分钟 → 20段
│ (ChunkController)         │
└─────────────┬─────────────┘
              ↓
    ┌─────┴─────┐
    │ Chunk 1   │ ──▶ 渲染 ──▶ webm1
    │ Chunk 2   │ ──▶ 渲染 ──▶ webm2
    │ ...       │ ──▶ 渲染 ──▶ ...
    │ Chunk 20  │ ──▶ 渲染 ──▶ webm20
    └─────┬─────┘
          ↓
┌───────────────────────────┐
│ 视频拼接器                 │ 重叠 1 秒转场
│ (FFmpeg.wasm)             │
└─────────────┬─────────────┘
              ↓
     最终视频.mp4
```

---

### 2.6 任务持久化

**存储**：IndexedDB（浏览器端）+ Redis（服务器端）

**数据模型**：
```typescript
interface RenderTask {
  id: string;
  projectId: string;
  status: 'pending' | 'queued' | 'rendering' | 'completed' | 'failed';
  mode: 'lambda' | 'browser';
  totalDuration: number;
  chunkCount: number;
  progress: number;
  renderId?: string;        // Lambda render ID
  outputUrl?: string;       // R2 下载链接
  error?: string;
}

interface BrowserRenderTask {
  id: string;
  projectId: string;
  status: 'pending' | 'rendering' | 'paused' | 'completed' | 'failed';
  totalDuration: number;
  chunks: ChunkInfo[];
  finalBlob?: Blob;
}

interface ChunkInfo {
  index: number;
  startTime: number;
  endTime: number;
  status: 'pending' | 'rendering' | 'completed' | 'failed';
  progress: number;
  blob?: Blob;
  retryCount: number;
}
```

**恢复流程**：
```
页面加载
    ↓
检查是否有未完成的渲染任务
    ↓
    ├─ Lambda 任务 → 轮询状态
    │
    ├─ 浏览器任务 → 显示恢复对话框
    │         ├─ "继续渲染" → 从断点恢复
    │         └─ "放弃" → 删除任务
    │
    └─ 无 → 正常开始渲染
```

---

### 2.7 可靠性保障

| 机制 | 说明 |
|------|------|
| **自动降级** | Lambda 失败 → 浏览器渲染 |
| **失败重试** | 单段失败自动重试 3 次 |
| **断点续传** | 浏览器渲染进度保存到 IndexedDB |
| **Lambda 分段** | Remotion 自动拆分长视频 |
| **设备检测** | 弱设备自动走浏览器渲染 |

---

## 三、实施计划

### 阶段一：PPT 生成（2 周）

| 任务 | 文件 | 工期 | 说明 |
|------|------|------|------|
| 1.1 Chat 状态管理 | `src/lib/types/chat.ts` | 0.5 天 | 添加 ChatSessionState, SceneOutline |
| 1.2 大纲生成 API | `src/app/api/outline/route.ts` | 1 天 | 对话式生成场景大纲 |
| 1.3 大纲确认 UI | `src/components/OutlineConfirm.tsx` | 0.5 天 | 大纲展示 + 修改 + 确认 |
| 1.4 内容生成 Pipeline | `src/lib/generation/pipeline.ts` | 1.5 天 | Outline → Scene Content + Actions |
| 1.5 PPT 导出核心 | `src/lib/export/pptx-generator.ts` | 2 天 | svg_to_pptx 封装 |
| 1.6 LaTeX 公式支持 | `src/lib/export/latex-to-omml.ts` | 1 天 | temml + mathml2omml |
| 1.7 Shape/Chart/Table | `src/lib/export/layer-mappers.ts` | 1 天 | 扩展层类型映射 |

### 阶段二：Remotion Lambda 集成（1 周）

| 任务 | 文件 | 工期 | 说明 |
|------|------|------|------|
| 2.1 Lambda 配置 | `src/lib/render/lambda-config.ts` | 0.5 天 | AWS 凭证、R2 endpoint |
| 2.2 渲染触发器 | `src/lib/render/lambda-renderer.ts` | 1 天 | @remotion/lambda SDK |
| 2.3 渲染状态 API | `src/app/api/render/lambda/[id]/route.ts` | 0.5 天 | 轮询 Lambda 状态 |
| 2.4 R2 集成 | `src/lib/r2.ts` | 0.5 天 | 读取 R2 输出 |
| 2.5 前端进度 UI | `src/components/RenderProgress.tsx` | 0.5 天 | 显示 Lambda 进度 |

### 阶段三：浏览器降级方案（1 周）

| 任务 | 文件 | 工期 | 说明 |
|------|------|------|------|
| 3.1 分段控制器 | `src/lib/render/chunk-controller.ts` | 1 天 | 40分钟 → 20段 × 2分钟 |
| 3.2 浏览器渲染器 | `src/lib/render/browser-renderer.ts` | 1.5 天 | WebCodecs + 内存管理 |
| 3.3 视频拼接器 | `src/lib/render/video-stitcher.ts` | 1 天 | 保留转场的重叠拼接 |
| 3.4 断点续传 | `src/lib/render/checkpoint-store.ts` | 0.5 天 | IndexedDB 保存进度 |
| 3.5 设备检测 | `src/lib/render/device-capability.ts` | 0.5 天 | 检测 GPU/内存/性能 |

**总计：约 4 周**

---

## 四、文件清单

```
src/
├── lib/
│   ├── types/
│   │   └── chat.ts                      # ChatSessionState, SceneOutline
│   │
│   ├── generation/
│   │   ├── pipeline.ts                  # 大纲→内容生成
│   │   └── outline-generator.ts         # AI生成大纲
│   │
│   ├── export/
│   │   ├── pptx-generator.ts            # PPT导出核心
│   │   ├── latex-to-omml.ts           # LaTeX支持
│   │   └── layer-mappers.ts            # Shape/Chart/Table
│   │
│   └── render/
│       ├── lambda-config.ts             # Lambda 配置
│       ├── lambda-renderer.ts          # @remotion/lambda 触发
│       ├── chunk-controller.ts         # 分段控制器
│       ├── browser-renderer.ts         # 浏览器渲染
│       ├── video-stitcher.ts           # 视频拼接
│       ├── checkpoint-store.ts          # 断点续传
│       └── device-capability.ts        # 设备检测
│
├── app/api/
│   ├── outline/route.ts                # 大纲生成API
│   ├── pptx/route.ts                   # PPT生成API
│   └── render/
│       ├── lambda/route.ts             # Lambda 触发
│       └── lambda/[id]/route.ts        # Lambda 状态
│
└── components/
    ├── OutlineConfirm.tsx               # 大纲确认UI
    ├── RenderProgress.tsx              # 渲染进度UI
    └── ResumeDialog.tsx                # 恢复对话框
```

---

## 五、API 设计

### 5.1 大纲生成

```http
POST /api/outline
Content-Type: application/json

{
  "requirement": "Python 入门教程",
  "language": "zh-CN"
}

Response:
{
  "success": true,
  "data": {
    "outlines": [
      {
        "id": "scene_1",
        "title": "变量和数据类型",
        "description": "介绍 Python 的基本数据类型",
        "keyPoints": ["变量定义", "整数和浮点数", "字符串", "布尔值"],
        "mediaGenerations": [...],
        "estimatedDuration": 120
      }
    ]
  }
}
```

### 5.2 PPT 生成

```http
POST /api/pptx
Content-Type: application/json

{
  "outlines": [...],
  "scenes": [...]
}

Response:
{
  "success": true,
  "data": {
    "url": "/downloads/pptx/xxx.pptx"
  }
}
```

### 5.3 Lambda 渲染触发

```http
POST /api/render/lambda
Content-Type: application/json

{
  "composition": {
    "id": "video-1",
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "durationInFrames": 18000,
    "layers": [...]
  },
  "outputFormat": "mp4",
  "region": "us-east-1"
}

Response:
{
  "success": true,
  "data": {
    "renderId": "abc123",
    "status": "queued",
    "estimatedDuration": 600
  }
}
```

### 5.4 Lambda 渲染状态

```http
GET /api/render/lambda/{renderId}

Response:
{
  "success": true,
  "data": {
    "renderId": "abc123",
    "status": "rendering",
    "progress": 45,
    "currentChunk": 2,
    "totalChunks": 3,
    "outputUrl": null
  }
}

Response (completed):
{
  "success": true,
  "data": {
    "renderId": "abc123",
    "status": "completed",
    "progress": 100,
    "outputUrl": "https://xxx.r2.cloudflarestorage.com/video.mp4"
  }
}
```

---

## 六、技术选型

| 功能 | 技术选型 |
|------|----------|
| PPT 生成 | svg_to_pptx + Railway CPU |
| LaTeX 公式 | temml + mathml2omml |
| 视频渲染 | @remotion/lambda + AWS Lambda |
| 视频存储 | Cloudflare R2 |
| 浏览器渲染 | @remotion/renderer + FFmpeg.wasm |
| 浏览器存储 | IndexedDB (idb) |
| 状态管理 | React Context + Zustand |
| 对话生成 | Vercel AI SDK |

---

## 七、参考项目

**OpenMAIC** (THU-MAIC/OpenMAIC)：
- https://github.com/THU-MAIC/OpenMAIC
- 关键参考文件：
  - `lib/export/use-export-pptx.ts` - PPT 导出
  - `lib/export/latex-to-omml.ts` - LaTeX 转换
  - `lib/generation/outline-generator.ts` - 大纲生成
  - `lib/generation/scene-generator.ts` - 内容生成
  - `lib/server/classroom-generation.ts` - 服务端编排

**Remotion Lambda**：
- https://www.remotion.dev/docs/lambda/
- @remotion/lambda SDK

---

## 八、费用估算

| 服务 | 单次成本 | 月成本（100视频） | 说明 |
|------|----------|-------------------|------|
| **Railway CPU** | 已有 | ~$10-20/月 | 包含在现有账单 |
| **Remotion Lambda** | ~$0.15-0.30/视频 | ~$15-30/月 | 按渲染时长计费 |
| **Cloudflare R2** | 已有 | ~$0 | 复用现有存储 |
| **S3 数据传输** | ~$0.01/GB | 可忽略 | 极少量 |

**月总成本**：~$25-50/月（100个视频）

---

## 九、注意事项

1. **Lambda 首次部署**：需要执行 `npx remotion lambda deploy` 部署函数
2. **R2 兼容 S3**：Remotion 默认输出到 S3，需配置 endpoint 指向 R2
3. **浏览器内存**：每段渲染限制 2 分钟，超出自动分段
4. **转场处理**：段间保留 1 秒重叠，确保转场效果
5. **自动降级**：连续 2 次失败自动切换到浏览器渲染

---

**文档版本**：v2.0
**创建时间**：2026-03-21
**适用范围**：with-langgraph-fastapi 项目
