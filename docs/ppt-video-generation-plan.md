# PPT讲解视频生成方案

## 一、概述

### 1.1 项目背景

基于对OpenMAIC项目的深入分析，结合当前项目的Remotion视频生成能力，设计一套**对话式PPT生成 → 自动讲解视频**的完整方案。

### 1.2 核心需求

1. **对话式生成**：通过多轮对话，先生成大纲，再填充内容
2. **PPT生成**：生成可编辑的PPT，支持导出PPTX
3. **讲解视频**：基于PPT自动生成讲解视频，支持数字人
4. **浏览器端渲染**：全部在浏览器端完成视频渲染，减少服务器负载

### 1.3 使用场景

- **企业培训**：内部课程培训材料
- **教育课程**：知识讲解类视频
- **产品演示**：商业展示类视频

---

## 二、架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           浏览器端（Next.js + Remotion）                      │
│                                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ LangGraph   │->│ PPT编辑器   │->│ Remotion    │->│ MP4导出     │        │
│  │ 对话状态机  │  │ (Canvas)    │  │ Player预览  │  │ (浏览器渲染)│        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│        │                │                │                │                │
│        └────────────────┴────────────────┴────────────────┘                │
│                                    │                                        │
│                        ┌───────────▼───────────┐                            │
│                        │ Zustand Store         │                            │
│                        │ (PPT状态 + 视频状态)   │                            │
│                        └───────────────────────┘                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
            │ 服务端API   │ │ 外部服务    │ │ 数字人服务  │
            │ - LLM对话   │ │ - 高质量TTS │ │ (可选)      │
            │ - JSON解析  │ │             │ │             │
            └─────────────┘ └─────────────┘ └─────────────┘
```

### 2.2 生成流程

```
用户对话 → 大纲生成 → 用户确认 → 内容填充 → PPT编辑 → 视频渲染
    │           │           │           │           │           │
    ▼           ▼           ▼           ▼           ▼           ▼
 收集需求   LLM生成    交互确认    LLM填充    Canvas编辑  分段渲染
```

---

## 三、核心模块设计

### 3.1 LangGraph 对话状态机

借鉴OpenMAIC的两阶段生成流程：

```python
# agent/src/ppt_conversation/state.py

from typing import TypedDict, Literal, List, Optional
from langgraph.graph import StateGraph

class PPTConversationState(TypedDict):
    # 用户需求
    user_id: str
    topic: str                    # PPT主题
    purpose: str                  # 企业培训/产品演示/教育课程
    target_audience: str          # 目标受众
    duration_minutes: int         # 预计时长
    
    # 大纲数据
    outline: Optional[List[dict]] # 场景大纲
    outline_confirmed: bool       # 用户是否确认大纲
    
    # 内容数据
    slides: Optional[List[dict]]  # 完整幻灯片数据
    speech_texts: Optional[List[str]]  # 每页讲解文本
    
    # 视频配置
    video_mode: Literal["animation", "digital_human", "both"]
    voice_style: str              # 声音风格
    avatar_style: str             # 数字人风格（可选）
    
    # 状态控制
    current_stage: Literal["collecting", "outline", "confirming", "content", "video", "complete"]
    messages: List[dict]          # 对话历史
```

**状态转换规则**：

```python
STAGE_TRANSITIONS = {
    "collecting": ["outline"],        # 收集需求 → 生成大纲
    "outline": ["confirming"],        # 生成大纲 → 等待确认
    "confirming": ["content", "outline"],  # 确认 → 填充内容 或 重新生成
    "content": ["video"],             # 填充内容 → 生成视频
    "video": ["complete"],            # 生成视频 → 完成
}
```

### 3.2 PPT 大纲生成器

借鉴OpenMAIC的 `outline-generator.ts`：

```python
# agent/src/ppt_generation/outline_generator.py

async def generate_ppt_outline(
    topic: str,
    purpose: str,           # "企业培训"
    target_audience: str,
    duration_minutes: int,
    ai_call: Callable,
) -> List[dict]:
    """
    生成PPT大纲，每个场景包含：
    - title: 场景标题
    - key_points: 关键要点
    - narration: 讲解文本（简短版）
    - suggested_visuals: 建议的视觉元素
    - duration_seconds: 预计时长
    """
    num_slides = max(5, duration_minutes * 2)  # 约2分钟/页
    
    prompt = f"""
你是企业培训课程设计师。请为以下培训主题设计PPT大纲：

主题：{topic}
目的：{purpose}
目标受众：{target_audience}
时长：{duration_minutes}分钟
幻灯片数量：{num_slides}页

请按以下JSON格式返回：
{{
    "slides": [
        {{
            "index": 1,
            "title": "幻灯片标题",
            "key_points": ["要点1", "要点2"],
            "narration": "这页的讲解内容（100字左右）",
            "suggested_visuals": ["图表", "流程图", "实拍图"],
            "duration_seconds": 120
        }}
    ],
    "total_duration_seconds": {duration_minutes * 60},
    "narrative_structure": "引入 → 核心内容 → 案例 → 总结"
}}
"""
    
    response = await ai_call(prompt)
    return parse_json_response(response)["slides"]
```

### 3.3 PPT 内容生成器

借鉴OpenMAIC的 `scene-generator.ts`：

```python
# agent/src/ppt_generation/content_generator.py

async def generate_slide_content(
    slide_outline: dict,
    ai_call: Callable,
) -> dict:
    """
    根据大纲生成完整的幻灯片内容
    """
    prompt = f"""
你是PPT内容设计师。请为以下大纲生成具体的幻灯片内容：

标题：{slide_outline['title']}
关键要点：{slide_outline['key_points']}
讲解内容：{slide_outline['narration']}

请生成以下元素（JSON格式）：
{{
    "elements": [
        {{
            "type": "text",
            "content": "标题文本",
            "position": {{"x": 50, "y": 50}},
            "style": {{"fontSize": 36, "bold": true}}
        }},
        {{
            "type": "chart",
            "chartType": "bar",
            "data": {{
                "labels": ["Q1", "Q2", "Q3", "Q4"],
                "values": [[100, 150, 200, 180]]
            }},
            "position": {{"x": 100, "y": 200}}
        }},
        {{
            "type": "image",
            "prompt": "生成一张展示...的图片",
            "position": {{"x": 500, "y": 150}}
        }}
    ],
    "background": "#ffffff",
    "speaker_notes": "讲师备注（用于数字人讲解）"
}}
"""
    
    response = await ai_call(prompt)
    return parse_json_response(response)
```

### 3.4 PPTX 导出器

直接借鉴OpenMAIC的 `use-export-pptx.ts`：

```typescript
// src/lib/pptx/pptx-exporter.ts

import pptxgen from 'svg_to_pptx';

interface Slide {
    id: string;
    elements: PPTElement[];
    background?: string;
    speakerNotes?: string;
}

export async function exportToPPTX(
    slides: Slide[],
    projectName: string
): Promise<Blob> {
    const pptx = new pptxgen();
    
    for (const slide of slides) {
        const pptxSlide = pptx.addSlide();
        
        // 添加演讲者备注（用于数字人讲解）
        if (slide.speakerNotes) {
            pptxSlide.addNotes(slide.speakerNotes);
        }
        
        // 遍历元素
        for (const el of slide.elements) {
            switch (el.type) {
                case 'text':
                    pptxSlide.addText(el.content, {
                        x: el.position.x / 96,
                        y: el.position.y / 96,
                        w: el.width / 96,
                        h: el.height / 96,
                        fontSize: el.style?.fontSize || 24,
                        fontFace: 'Microsoft YaHei',
                        color: el.style?.color || '#333333',
                    });
                    break;
                    
                case 'image':
                    if (el.src?.startsWith('gen_')) {
                        // AI生成图片占位符，需要异步填充
                        await resolveGeneratedImage(el);
                    }
                    pptxSlide.addImage({
                        data: el.src,
                        x: el.position.x / 96,
                        y: el.position.y / 96,
                        w: el.width / 96,
                        h: el.height / 96,
                    });
                    break;
                    
                case 'chart':
                    pptxSlide.addChart(
                        el.chartType === 'bar' ? pptx.ChartType.bar : pptx.ChartType.line,
                        [{
                            name: 'Data',
                            labels: el.data.labels,
                            values: el.data.values[0]
                        }],
                        {
                            x: el.position.x / 96,
                            y: el.position.y / 96,
                            w: el.width / 96,
                            h: el.height / 96,
                        }
                    );
                    break;
                    
                case 'latex':
                    // 使用 OpenMAIC 的 LaTeX → OMML 转换
                    const omml = latexToOmml(el.latex, 24);
                    if (omml) {
                        pptxSlide.addFormula({
                            omml,
                            x: el.position.x / 96,
                            y: el.position.y / 96,
                            w: el.width / 96,
                            h: el.height / 96,
                        });
                    }
                    break;
            }
        }
    }
    
    return pptx.write({ outputType: 'blob' }) as Promise<Blob>;
}
```

---

## 四、PPT编辑器设计

### 4.1 编辑器组件结构

```typescript
// src/components/ppt-editor/PPTEditor.tsx

import { Canvas } from '@/components/ppt-editor/Canvas';
import { Toolbar } from '@/components/ppt-editor/Toolbar';
import { SlideList } from '@/components/ppt-editor/SlideList';
import { PropertyPanel } from '@/components/ppt-editor/PropertyPanel';
import { usePPTStore } from '@/store/ppt-store';

export function PPTEditor() {
    const { slides, currentSlideIndex } = usePPTStore();
    
    return (
        <div className="flex h-screen">
            {/* 左侧：幻灯片列表 */}
            <SlideList
                slides={slides}
                currentIndex={currentSlideIndex}
                onSelect={(index) => usePPTStore.getState().setCurrentSlide(index)}
            />
            
            {/* 中间：画布 */}
            <div className="flex-1 flex flex-col">
                <Toolbar />
                <Canvas slide={slides[currentSlideIndex]} />
            </div>
            
            {/* 右侧：属性面板 */}
            <PropertyPanel />
        </div>
    );
}
```

### 4.2 PPT状态管理

```typescript
// src/store/ppt-store.ts

import { create } from 'zustand';

interface PPTElement {
    id: string;
    type: 'text' | 'image' | 'chart' | 'shape' | 'latex';
    position: { x: number; y: number };
    size: { width: number; height: number };
    content: string;
    style?: Record<string, any>;
    animation?: {
        type: 'fadeIn' | 'slideIn' | 'scaleIn' | 'draw';
        duration: number;
        delay: number;
    };
}

interface Slide {
    id: string;
    index: number;
    elements: PPTElement[];
    background: string;
    narration: string;      // 讲解文本
    duration: number;       // 秒
}

interface PPTState {
    // 项目信息
    projectId: string;
    title: string;
    
    // 幻灯片
    slides: Slide[];
    currentSlideIndex: number;
    
    // 编辑状态
    selectedElementId: string | null;
    
    // 视频配置
    videoConfig: {
        width: number;
        height: number;
        fps: number;
        voiceStyle: string;
    };
    
    // Actions
    addSlide: (slide: Slide) => void;
    updateSlide: (index: number, slide: Partial<Slide>) => void;
    deleteSlide: (index: number) => void;
    setCurrentSlide: (index: number) => void;
    addElement: (slideIndex: number, element: PPTElement) => void;
    updateElement: (slideIndex: number, elementId: string, updates: Partial<PPTElement>) => void;
    deleteElement: (slideIndex: number, elementId: string) => void;
    selectElement: (elementId: string | null) => void;
    
    // 导入导出
    importFromJSON: (data: any) => void;
    exportToJSON: () => any;
    exportToPPTX: () => Promise<Blob>;
}

export const usePPTStore = create<PPTState>((set, get) => ({
    projectId: '',
    title: '未命名演示文稿',
    slides: [],
    currentSlideIndex: 0,
    selectedElementId: null,
    videoConfig: {
        width: 1920,
        height: 1080,
        fps: 30,
        voiceStyle: 'zh-CN-female',
    },
    
    // ... 实现所有actions
}));
```

---

## 五、Remotion视频组件

### 5.1 PPT视频组件

```typescript
// src/remotion/compositions/PPTVideo.tsx

import React from 'react';
import {
    AbsoluteFill,
    Sequence,
    Video,
    Img,
    Audio,
    Text,
    useCurrentFrame,
    useVideoConfig,
    interpolate,
    spring,
    registerRoot,
} from 'remotion';
import type { Slide } from '@/store/ppt-store';

interface PPTVideoProps {
    slides: Slide[];
    ttsAudios?: (string | null)[];  // 服务端TTS或null（使用Web Speech API）
    bgmUrl?: string;
    bgmVolume?: number;
}

export const PPTVideo: React.FC<PPTVideoProps> = ({
    slides,
    ttsAudios = [],
    bgmUrl,
    bgmVolume = 0.15,
}) => {
    const { fps } = useVideoConfig();
    
    return (
        <AbsoluteFill style={{ backgroundColor: '#ffffff' }}>
            {slides.map((slide, index) => {
                const slideStartFrame = slides
                    .slice(0, index)
                    .reduce((sum, s) => sum + Math.round(s.duration * fps), 0);
                const slideDurationFrames = Math.round(slide.duration * fps);
                
                return (
                    <Sequence
                        key={slide.id}
                        from={slideStartFrame}
                        durationInFrames={slideDurationFrames}
                    >
                        <SlideScene
                            slide={slide}
                            fps={fps}
                            ttsAudio={ttsAudios[index]}
                        />
                    </Sequence>
                );
            })}
            
            {bgmUrl && <Audio src={bgmUrl} volume={bgmVolume} loop />}
        </AbsoluteFill>
    );
};

const SlideScene: React.FC<{
    slide: Slide;
    fps: number;
    ttsAudio?: string | null;
}> = ({ slide, fps, ttsAudio }) => {
    return (
        <AbsoluteFill style={{ backgroundColor: slide.background }}>
            {/* 元素逐个出现 */}
            {slide.elements.map((element, index) => (
                <ElementRenderer
                    key={element.id}
                    element={element}
                    index={index}
                    fps={fps}
                />
            ))}
            
            {/* 页码 */}
            <div style={{
                position: 'absolute',
                bottom: 20,
                right: 30,
                fontSize: 14,
                color: '#999',
                fontFamily: 'sans-serif',
            }}>
                {slide.index}
            </div>
            
            {/* TTS音频 */}
            {ttsAudio && <Audio src={ttsAudio} volume={1} />}
        </AbsoluteFill>
    );
};

const ElementRenderer: React.FC<{
    element: PPTElement;
    index: number;
    fps: number;
}> = ({ element, index, fps }) => {
    const frame = useCurrentFrame();
    const animation = element.animation;
    
    // 计算动画进度
    const animationStartFrame = (animation?.delay ?? index * 0.2) * fps;
    const animationDuration = (animation?.duration ?? 0.5) * fps;
    const animationProgress = Math.max(0, (frame - animationStartFrame) / animationDuration);
    
    // 动画效果
    let opacity = 1;
    let transform = 'none';
    
    if (animation) {
        switch (animation.type) {
            case 'fadeIn':
                opacity = interpolate(animationProgress, [0, 1], [0, 1], {
                    extrapolateRight: 'clamp',
                });
                break;
                
            case 'scaleIn':
                const scale = spring({
                    frame: frame - animationStartFrame,
                    fps,
                    config: { damping: 12, stiffness: 100 },
                });
                transform = `scale(${scale})`;
                opacity = interpolate(animationProgress, [0, 0.5], [0, 1], {
                    extrapolateRight: 'clamp',
                });
                break;
                
            case 'slideIn':
                const slideProgress = interpolate(animationProgress, [0, 1], [-100, 0], {
                    extrapolateRight: 'clamp',
                });
                transform = `translateX(${slideProgress}px)`;
                opacity = interpolate(animationProgress, [0, 1], [0, 1], {
                    extrapolateRight: 'clamp',
                });
                break;
        }
    }
    
    // 渲染元素
    const style: React.CSSProperties = {
        position: 'absolute',
        left: element.position.x,
        top: element.position.y,
        width: element.size.width,
        height: element.size.height,
        opacity,
        transform,
    };
    
    switch (element.type) {
        case 'text':
            return (
                <div style={{ ...style, ...element.style }}>
                    <Text>{element.content}</Text>
                </div>
            );
            
        case 'image':
            return (
                <div style={style}>
                    <Img
                        src={element.content}
                        style={{
                            width: '100%',
                            height: '100%',
                            objectFit: 'cover'
                        }}
                    />
                </div>
            );
            
        case 'chart':
            return (
                <div style={style}>
                    <ChartRenderer
                        type={element.style?.chartType}
                        data={element.content}
                    />
                </div>
            );
            
        default:
            return null;
    }
};

// 注册组件
registerRoot(PPTVideo);
```

---

## 六、TTS集成（双模式）

### 6.1 Web Speech API（预览用）

```typescript
// src/lib/tts/tts-service.ts

export async function speakWithWebTTS(
    text: string,
    options: TTSOptions
): Promise<void> {
    return new Promise((resolve, reject) => {
        if (!window.speechSynthesis) {
            reject(new Error('Web Speech API not supported'));
            return;
        }
        
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = options.lang || 'zh-CN';
        utterance.rate = options.rate || 1.0;
        utterance.pitch = options.pitch || 1.0;
        utterance.volume = options.volume || 1.0;
        
        // 选择声音
        const voices = window.speechSynthesis.getVoices();
        const voice = voices.find(v => v.lang.startsWith(options.lang)) || voices[0];
        if (voice) utterance.voice = voice;
        
        utterance.onend = () => resolve();
        utterance.onerror = (e) => reject(e);
        
        window.speechSynthesis.speak(utterance);
    });
}
```

### 6.2 服务端TTS（导出用）

```typescript
export async function generateServerTTS(
    texts: string[],
    options: TTSOptions
): Promise<string[]> {
    const response = await fetch('/api/tts/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ texts, options }),
    });
    
    const data = await response.json();
    return data.audioUrls;  // 返回音频URL数组
}
```

### 6.3 统一接口

```typescript
export class TTSService {
    private mode: 'web' | 'server' = 'web';
    
    setMode(mode: 'web' | 'server') {
        this.mode = mode;
    }
    
    async generate(texts: string[], options: TTSOptions): Promise<(string | null)[]> {
        if (this.mode === 'web') {
            // Web Speech API不支持导出音频文件
            // 返回null，使用实时播放
            return texts.map(() => null);
        } else {
            // 服务端TTS返回音频URL
            return generateServerTTS(texts, options);
        }
    }
}
```

---

## 七、混合渲染架构（AWS Lambda + 浏览器端）

### 7.1 架构概述

采用**浏览器端预览 + AWS Lambda正式渲染**的混合架构：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              整体渲染架构                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         浏览器端（预览）                              │   │
│  │  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                │   │
│  │  │ Remotion    │-> │ 720p预览    │-> │ Web Speech  │                │   │
│  │  │ Player      │   │ 实时播放    │   │ API TTS     │                │   │
│  │  └─────────────┘   └─────────────┘   └─────────────┘                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    │ 用户确认渲染                            │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      AWS Lambda（正式渲染）                           │   │
│  │  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                │   │
│  │  │ 分段渲染    │-> │ Lambda并发  │-> │ FFmpeg合并  │                │   │
│  │  │ (每段30秒)  │   │ (多实例)    │   │ (最终视频)  │                │   │
│  │  └─────────────┘   └─────────────┘   └─────────────┘                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Cloudflare R2（存储）                              │   │
│  │  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                │   │
│  │  │ 分段视频    │-> │ 最终视频    │-> │ CDN分发     │                │   │
│  │  │ 临时存储    │   │ 永久存储    │   │ 全球加速    │                │   │
│  │  └─────────────┘   └─────────────┘   └─────────────┘                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 渲染模式对比

| 模式 | 适用场景 | 渲染位置 | 分辨率 | 优势 | 劣势 |
|------|----------|----------|--------|------|------|
| **预览模式** | 编辑时实时预览 | 浏览器端 | 720p | 即时反馈，无需等待 | 质量较低，TTS为Web Speech |
| **快速导出** | 短视频(<3分钟) | 浏览器端 | 1080p | 无需服务器，离线可用 | 占用浏览器资源 |
| **标准渲染** | 中长视频(3-10分钟) | AWS Lambda | 1080p | 高质量，不占用本地资源 | 需等待，有成本 |
| **高质量渲染** | 长视频(>10分钟) | AWS Lambda | 4K | 最高质量，支持复杂特效 | 渲染时间长，成本较高 |

### 7.3 AWS Lambda渲染架构

```
渲染请求流程：

┌─────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ 浏览器  │ -> │ API Gateway │ -> │ Lambda      │ -> │ R2存储      │
│ 提交    │    │ 路由/限流   │    │ Orchestrator│    │ 任务队列    │
└─────────┘    └─────────────┘    └─────────────┘    └─────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
              ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
              │ Lambda      │    │ Lambda      │    │ Lambda      │
              │ Worker 1    │    │ Worker 2    │    │ Worker N    │
              │ (分段渲染)  │    │ (分段渲染)  │    │ (分段渲染)  │
              └─────────────┘    └─────────────┘    └─────────────┘
                    │                   │                   │
                    └───────────────────┼───────────────────┘
                                        ▼
                              ┌─────────────┐
                              │ Lambda      │
                              │ Merger      │
                              │ (视频合并)  │
                              └─────────────┘
```

### 7.4 AWS Lambda配置

#### 7.4.1 Lambda层配置

```yaml
# lambda-layers/remotion-layer/serverless.yml

service: remotion-render-layer

provider:
  name: aws
  runtime: nodejs20.x
  region: us-east-1
  memorySize: 2048
  timeout: 900  # 15分钟最大超时

layers:
  remotionLayer:
    path: layer
    description: Remotion + FFmpeg + Chromium dependencies
    compatibleRuntimes:
      - nodejs20.x

functions:
  renderSegment:
    handler: src/handlers/render-segment.handler
    layers:
      - { Ref: RemotionLayerLambdaLayer }
    environment:
      R2_BUCKET: ${env:R2_BUCKET}
      R2_ACCOUNT_ID: ${env:R2_ACCOUNT_ID}
      R2_ACCESS_KEY: ${env:R2_ACCESS_KEY}
      R2_SECRET_KEY: ${env:R2_SECRET_KEY}
    events:
      - sqs:
          arn: ${env:RENDER_QUEUE_ARN}
          batchSize: 1

  mergeVideo:
    handler: src/handlers/merge-video.handler
    layers:
      - { Ref: RemotionLayerLambdaLayer }
    environment:
      R2_BUCKET: ${env:R2_BUCKET}
      R2_ACCOUNT_ID: ${env:R2_ACCOUNT_ID}
      R2_ACCESS_KEY: ${env:R2_ACCESS_KEY}
      R2_SECRET_KEY: ${env:R2_SECRET_KEY}
```

#### 7.4.2 渲染Worker实现

```typescript
// lambda/src/handlers/render-segment.ts

import { renderMediaOnLambda } from '@remotion/lambda';
import { S3Client, PutObjectCommand, GetObjectCommand } from '@aws-sdk/client-s3';
import { SQSHandler } from 'aws-lambda';

const r2Client = new S3Client({
  region: 'auto',
  endpoint: `https://${process.env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com`,
  credentials: {
    accessKeyId: process.env.R2_ACCESS_KEY!,
    secretAccessKey: process.env.R2_SECRET_KEY!,
  },
});

interface RenderSegmentMessage {
  jobId: string;
  segmentIndex: number;
  startFrame: number;
  endFrame: number;
  composition: string;
  inputProps: any;
  fps: number;
  width: number;
  height: number;
}

export const handler: SQSHandler = async (event) => {
  for (const record of event.Records) {
    const message: RenderSegmentMessage = JSON.parse(record.body);
    
    try {
      // 1. 从R2获取composition数据
      const compositionData = await r2Client.send(
        new GetObjectCommand({
          Bucket: process.env.R2_BUCKET!,
          Key: `jobs/${message.jobId}/composition.json`,
        })
      );
      
      // 2. 渲染分段视频
      const result = await renderMediaOnLambda({
        region: 'us-east-1',
        functionName: 'remotion-render',
        composition: message.composition,
        inputProps: message.inputProps,
        outputBucket: process.env.R2_BUCKET!,
        outputKey: `jobs/${message.jobId}/segments/segment_${message.segmentIndex}.mp4`,
        startFrame: message.startFrame,
        endFrame: message.endFrame,
        fps: message.fps,
        width: message.width,
        height: message.height,
        codec: 'h264',
        crf: 20,
      });
      
      // 3. 更新任务状态
      await r2Client.send(
        new PutObjectCommand({
          Bucket: process.env.R2_BUCKET!,
          Key: `jobs/${message.jobId}/status/segment_${message.segmentIndex}.json`,
          Body: JSON.stringify({
            status: 'completed',
            segmentIndex: message.segmentIndex,
            completedAt: new Date().toISOString(),
            url: result.url,
          }),
        })
      );
      
    } catch (error) {
      // 错误处理
      await r2Client.send(
        new PutObjectCommand({
          Bucket: process.env.R2_BUCKET!,
          Key: `jobs/${message.jobId}/status/segment_${message.segmentIndex}.json`,
          Body: JSON.stringify({
            status: 'failed',
            segmentIndex: message.segmentIndex,
            error: error.message,
            failedAt: new Date().toISOString(),
          }),
        })
      );
      
      throw error;
    }
  }
};
```

#### 7.4.3 视频合并Worker

```typescript
// lambda/src/handlers/merge-video.ts

import { S3Client, PutObjectCommand, GetObjectCommand, ListObjectsV2Command } from '@aws-sdk/client-s3';
import { spawn } from 'child_process';
import { writeFile, readFile, unlink } from 'fs/promises';
import { tmpdir } from 'os';
import { join } from 'path';

const r2Client = new S3Client({
  region: 'auto',
  endpoint: `https://${process.env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com`,
  credentials: {
    accessKeyId: process.env.R2_ACCESS_KEY!,
    secretAccessKey: process.env.R2_SECRET_KEY!,
  },
});

interface MergeVideoMessage {
  jobId: string;
  totalSegments: number;
  outputKey: string;
}

export const handler = async (event: MergeVideoMessage) => {
  const { jobId, totalSegments, outputKey } = event;
  const tmpDir = tmpdir();
  
  try {
    // 1. 下载所有分段视频
    const segmentFiles: string[] = [];
    
    for (let i = 0; i < totalSegments; i++) {
      const segmentKey = `jobs/${jobId}/segments/segment_${i}.mp4`;
      const segmentData = await r2Client.send(
        new GetObjectCommand({
          Bucket: process.env.R2_BUCKET!,
          Key: segmentKey,
        })
      );
      
      const segmentBuffer = await streamToBuffer(segmentData.Body);
      const segmentPath = join(tmpDir, `segment_${i}.mp4`);
      await writeFile(segmentPath, segmentBuffer);
      segmentFiles.push(segmentPath);
    }
    
    // 2. 创建concat文件
    const concatList = segmentFiles.map(f => `file '${f}'`).join('\n');
    const concatPath = join(tmpDir, 'concat.txt');
    await writeFile(concatPath, concatList);
    
    // 3. 使用FFmpeg合并视频
    const outputPath = join(tmpDir, 'output.mp4');
    await new Promise((resolve, reject) => {
      const ffmpeg = spawn('ffmpeg', [
        '-f', 'concat',
        '-safe', '0',
        '-i', concatPath,
        '-c', 'copy',
        '-movflags', '+faststart',
        outputPath,
      ]);
      
      ffmpeg.on('close', (code) => {
        if (code === 0) resolve(undefined);
        else reject(new Error(`FFmpeg exited with code ${code}`));
      });
      
      ffmpeg.on('error', reject);
    });
    
    // 4. 上传到R2
    const outputBuffer = await readFile(outputPath);
    await r2Client.send(
      new PutObjectCommand({
        Bucket: process.env.R2_BUCKET!,
        Key: outputKey,
        Body: outputBuffer,
        ContentType: 'video/mp4',
        Metadata: {
          jobId,
          createdAt: new Date().toISOString(),
        },
      })
    );
    
    // 5. 清理临时文件
    for (const file of segmentFiles) {
      await unlink(file);
    }
    await unlink(concatPath);
    await unlink(outputPath);
    
    // 6. 返回结果
    return {
      statusCode: 200,
      body: JSON.stringify({
        jobId,
        status: 'completed',
        url: `https://${process.env.R2_BUCKET}.${process.env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com/${outputKey}`,
      }),
    };
    
  } catch (error) {
    return {
      statusCode: 500,
      body: JSON.stringify({
        jobId,
        status: 'failed',
        error: error.message,
      }),
    };
  }
};

function streamToBuffer(stream: any): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    stream.on('data', (chunk: Buffer) => chunks.push(chunk));
    stream.on('end', () => resolve(Buffer.concat(chunks)));
    stream.on('error', reject);
  });
}
```

### 7.5 Cloudflare R2存储架构

#### 7.5.1 R2 Bucket结构

```
r2://ppt-video-bucket/
├── jobs/
│   └── {jobId}/
│       ├── composition.json      # Remotion composition数据
│       ├── input/
│       │   ├── images/           # 图片素材
│       │   ├── audio/            # 音频素材
│       │   └── fonts/            # 字体文件
│       ├── segments/
│       │   ├── segment_0.mp4     # 分段视频
│       │   ├── segment_1.mp4
│       │   └── segment_n.mp4
│       ├── status/
│       │   ├── job.json          # 任务状态
│       │   └── segment_*.json    # 分段状态
│       └── output/
│           └── final.mp4         # 最终视频
├── pptx/
│   └── {projectId}/
│       └── presentation.pptx     # PPTX文件
└── tts/
    └── {jobId}/
        ├── narration_0.mp3       # TTS音频
        ├── narration_1.mp3
        └── narration_n.mp3
```

#### 7.5.2 R2配置

```typescript
// src/lib/storage/r2-client.ts

import { S3Client, PutObjectCommand, GetObjectCommand } from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';

export class R2StorageClient {
  private client: S3Client;
  private bucket: string;
  
  constructor() {
    this.client = new S3Client({
      region: 'auto',
      endpoint: `https://${process.env.NEXT_PUBLIC_R2_ACCOUNT_ID}.r2.cloudflarestorage.com`,
      credentials: {
        accessKeyId: process.env.R2_ACCESS_KEY!,
        secretAccessKey: process.env.R2_SECRET_KEY!,
      },
    });
    this.bucket = process.env.NEXT_PUBLIC_R2_BUCKET!;
  }
  
  async uploadJobComposition(jobId: string, composition: any): Promise<string> {
    const key = `jobs/${jobId}/composition.json`;
    await this.client.send(
      new PutObjectCommand({
        Bucket: this.bucket,
        Key: key,
        Body: JSON.stringify(composition),
        ContentType: 'application/json',
      })
    );
    return key;
  }
  
  async uploadImage(jobId: string, imageName: string, buffer: Buffer): Promise<string> {
    const key = `jobs/${jobId}/input/images/${imageName}`;
    await this.client.send(
      new PutObjectCommand({
        Bucket: this.bucket,
        Key: key,
        Body: buffer,
        ContentType: 'image/png',
      })
    );
    return key;
  }
  
  async uploadAudio(jobId: string, audioName: string, buffer: Buffer): Promise<string> {
    const key = `jobs/${jobId}/input/audio/${audioName}`;
    await this.client.send(
      new PutObjectCommand({
        Bucket: this.bucket,
        Key: key,
        Body: buffer,
        ContentType: 'audio/mpeg',
      })
    );
    return key;
  }
  
  async getSignedUrl(key: string, expiresIn: number = 3600): Promise<string> {
    const command = new GetObjectCommand({
      Bucket: this.bucket,
      Key: key,
    });
    return getSignedUrl(this.client, command, { expiresIn });
  }
  
  async getPublicUrl(key: string): string {
    return `https://${process.env.NEXT_PUBLIC_R2_PUBLIC_DOMAIN}/${key}`;
  }
}
```

### 7.6 渲染任务协调器

```typescript
// src/lib/render/render-coordinator.ts

import { R2StorageClient } from '@/lib/storage/r2-client';
import { SQSClient, SendMessageCommand } from '@aws-sdk/client-sqs';

interface RenderJobRequest {
  jobId: string;
  slides: Slide[];
  videoConfig: VideoConfig;
  ttsAudios: string[];
}

export class RenderCoordinator {
  private r2Client: R2StorageClient;
  private sqsClient: SQSClient;
  
  constructor() {
    this.r2Client = new R2StorageClient();
    this.sqsClient = new SQSClient({
      region: process.env.AWS_REGION!,
      credentials: {
        accessKeyId: process.env.AWS_ACCESS_KEY_ID!,
        secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY!,
      },
    });
  }
  
  async submitRenderJob(request: RenderJobRequest): Promise<string> {
    const { jobId, slides, videoConfig, ttsAudios } = request;
    const { fps, width, height } = videoConfig;
    
    // 1. 计算分段
    const segmentDuration = 30; // 每段30秒
    const totalDuration = slides.reduce((sum, s) => sum + s.duration, 0);
    const totalFrames = Math.round(totalDuration * fps);
    const segmentFrames = Math.round(segmentDuration * fps);
    const numSegments = Math.ceil(totalFrames / segmentFrames);
    
    // 2. 准备composition数据
    const composition = {
      id: `ppt-video-${jobId}`,
      component: 'PPTVideo',
      durationInFrames: totalFrames,
      fps,
      width,
      height,
      props: {
        slides,
        ttsAudios,
      },
    };
    
    // 3. 上传composition到R2
    await this.r2Client.uploadJobComposition(jobId, composition);
    
    // 4. 创建任务状态
    await this.updateJobStatus(jobId, {
      status: 'pending',
      totalSegments: numSegments,
      completedSegments: 0,
      createdAt: new Date().toISOString(),
    });
    
    // 5. 发送分段渲染任务到SQS
    for (let i = 0; i < numSegments; i++) {
      const startFrame = i * segmentFrames;
      const endFrame = Math.min((i + 1) * segmentFrames, totalFrames);
      
      await this.sqsClient.send(
        new SendMessageCommand({
          QueueUrl: process.env.SQS_RENDER_QUEUE_URL!,
          MessageBody: JSON.stringify({
            jobId,
            segmentIndex: i,
            startFrame,
            endFrame,
            composition: composition.id,
            inputProps: composition.props,
            fps,
            width,
            height,
          }),
        })
      );
    }
    
    return jobId;
  }
  
  async updateJobStatus(jobId: string, status: any): Promise<void> {
    // 更新R2中的任务状态
    await this.r2Client.client.send(
      new PutObjectCommand({
        Bucket: this.r2Client.bucket,
        Key: `jobs/${jobId}/status/job.json`,
        Body: JSON.stringify(status),
        ContentType: 'application/json',
      })
    );
  }
  
  async getJobStatus(jobId: string): Promise<any> {
    const response = await this.r2Client.client.send(
      new GetObjectCommand({
        Bucket: this.r2Client.bucket,
        Key: `jobs/${jobId}/status/job.json`,
      })
    );
    
    const body = await streamToString(response.Body);
    return JSON.parse(body);
  }
}
```

### 7.7 浏览器端分段渲染（备选方案）

针对不需要云渲染的场景，仍保留浏览器端渲染能力：

```
渲染流程：

┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐
│ PPT  │-> │ 分段 │-> │ 段1  │-> │ 段2  │-> │ 段3  │-> │ 合并 │-> │ 最终 │
│ 数据 │   │ 规划 │   │渲染中│   │等待  │   │等待  │   │ 视频 │   │ MP4 │
└──────┘   └──────┘   └──────┘   └──────┘   └──────┘   └──────┘   └──────┘
```

**分段策略**：
- 每段30秒
- 10分钟视频 → 20个分段
- 支持断点续传（IndexedDB持久化）
- 并发控制：同时渲染2个分段

### 7.2 分段渲染器

```typescript
// src/lib/ppt-video/segmented-renderer.ts

import { openDB } from 'idb';
import { renderMedia } from '@remotion/renderer';

interface RenderSegment {
    id: string;
    projectId: string;
    index: number;              // 分段索引
    startFrame: number;
    endFrame: number;
    status: 'pending' | 'rendering' | 'completed' | 'failed';
    progress: number;           // 0-1
    blob?: Blob;
    createdAt: number;
    updatedAt: number;
}

interface RenderJob {
    id: string;
    projectId: string;
    totalSegments: number;
    completedSegments: number;
    overallProgress: number;
    status: 'pending' | 'running' | 'paused' | 'completed' | 'failed';
    startedAt?: number;
    completedAt?: number;
}

class RenderDatabase {
    private dbPromise;
    
    constructor() {
        this.dbPromise = openDB('ppt-video-render', 1, {
            upgrade(db) {
                // 分段存储
                const segmentStore = db.createObjectStore('segments', { keyPath: 'id' });
                segmentStore.createIndex('projectId', 'projectId');
                segmentStore.createIndex('status', 'status');
                
                // 任务存储
                const jobStore = db.createObjectStore('jobs', { keyPath: 'id' });
                jobStore.createIndex('projectId', 'projectId');
            },
        });
    }
    
    async saveSegment(segment: RenderSegment) {
        const db = await this.dbPromise;
        await db.put('segments', { ...segment, updatedAt: Date.now() });
    }
    
    async getSegment(id: string) {
        const db = await this.dbPromise;
        return db.get('segments', id);
    }
    
    async getSegmentsByProject(projectId: string) {
        const db = await this.dbPromise;
        return db.getAllFromIndex('segments', 'projectId', projectId);
    }
    
    async saveJob(job: RenderJob) {
        const db = await this.dbPromise;
        await db.put('jobs', job);
    }
    
    async getJob(id: string) {
        const db = await this.dbPromise;
        return db.get('jobs', id);
    }
}

export class SegmentedRenderer {
    private db: RenderDatabase;
    private maxConcurrentSegments = 2;  // 同时渲染的分段数
    private segmentDuration = 30;        // 每段30秒
    private onProgress?: (progress: OverallProgress) => void;
    
    constructor() {
        this.db = new RenderDatabase();
    }
    
    /**
     * 规划分段
     * 10分钟视频 → 20个30秒分段
     */
    planSegments(slides: Slide[], fps: number): RenderSegment[] {
        const totalDuration = slides.reduce((sum, s) => sum + s.duration, 0);
        const totalFrames = Math.round(totalDuration * fps);
        const segmentFrames = Math.round(this.segmentDuration * fps);
        const segments: RenderSegment[] = [];
        
        let currentFrame = 0;
        let index = 0;
        
        while (currentFrame < totalFrames) {
            const endFrame = Math.min(currentFrame + segmentFrames, totalFrames);
            segments.push({
                id: `seg-${index}`,
                projectId: '',  // 稍后设置
                index,
                startFrame: currentFrame,
                endFrame,
                status: 'pending',
                progress: 0,
                createdAt: Date.now(),
                updatedAt: Date.now(),
            });
            currentFrame = endFrame;
            index++;
        }
        
        return segments;
    }
    
    /**
     * 开始渲染任务
     */
    async startRender(
        projectId: string,
        slides: Slide[],
        fps: number,
        onProgress?: (progress: OverallProgress) => void
    ): Promise<string> {
        this.onProgress = onProgress;
        
        // 1. 规划分段
        const segments = this.planSegments(slides, fps);
        segments.forEach(seg => seg.projectId = projectId);
        
        // 2. 检查是否有未完成的分段（断点续传）
        const existingSegments = await this.db.getSegmentsByProject(projectId);
        const pendingSegments = segments.filter(seg => {
            const existing = existingSegments.find(e => e.index === seg.index);
            return !existing || existing.status !== 'completed';
        });
        
        // 3. 创建任务
        const job: RenderJob = {
            id: `job-${Date.now()}`,
            projectId,
            totalSegments: segments.length,
            completedSegments: segments.length - pendingSegments.length,
            overallProgress: 0,
            status: 'running',
            startedAt: Date.now(),
        };
        await this.db.saveJob(job);
        
        // 4. 存储所有分段
        for (const seg of segments) {
            await this.db.saveSegment(seg);
        }
        
        // 5. 启动渲染
        this.renderSegments(projectId, pendingSegments, slides, fps, job);
        
        return job.id;
    }
    
    /**
     * 渲染分段（并发控制）
     */
    private async renderSegments(
        projectId: string,
        segments: RenderSegment[],
        slides: Slide[],
        fps: number,
        job: RenderJob
    ) {
        const queue = [...segments];
        const active: Map<string, Promise<void>> = new Map();
        
        while (queue.length > 0 || active.size > 0) {
            // 填充并发槽位
            while (active.size < this.maxConcurrentSegments && queue.length > 0) {
                const segment = queue.shift()!;
                const promise = this.renderSingleSegment(projectId, segment, slides, fps, job);
                active.set(segment.id, promise);
                promise.finally(() => active.delete(segment.id));
            }
            
            // 等待任意一个完成
            if (active.size > 0) {
                await Promise.race(active.values());
            }
        }
        
        // 所有分段完成，合并视频
        const finalBlob = await this.mergeSegments(projectId, fps);
        
        // 更新任务状态
        job.status = 'completed';
        job.completedAt = Date.now();
        job.overallProgress = 1;
        await this.db.saveJob(job);
        
        this.onProgress?.({
            jobId: job.id,
            overallProgress: 1,
            status: 'completed',
            finalBlob,
        });
    }
}

interface OverallProgress {
    jobId: string;
    overallProgress: number;  // 0-1
    status: 'pending' | 'running' | 'paused' | 'completed';
    finalBlob?: Blob;
}
```

### 7.3 视频合并

```typescript
// src/lib/ppt-video/video-merger.ts

import { FFmpeg } from '@ffmpeg/ffmpeg';
import { fetchFile } from '@ffmpeg/util';

export class VideoMerger {
    private ffmpeg: FFmpeg | null = null;
    private loaded = false;
    
    async init() {
        if (this.loaded) return;
        
        this.ffmpeg = new FFmpeg();
        await this.ffmpeg.load({
            coreURL: '/ffmpeg/ffmpeg-core.js',
            wasmURL: '/ffmpeg/ffmpeg-core.wasm',
        });
        
        this.loaded = true;
    }
    
    async merge(blobs: Blob[], fps: number): Promise<Blob> {
        if (!this.ffmpeg || !this.loaded) {
            throw new Error('FFmpeg not loaded');
        }
        
        const ffmpeg = this.ffmpeg;
        
        // 写入分段文件
        for (let i = 0; i < blobs.length; i++) {
            const data = await fetchFile(blobs[i]);
            await ffmpeg.writeFile(`segment_${i}.mp4`, data);
        }
        
        // 创建concat列表文件
        const concatList = blobs.map((_, i) => `file 'segment_${i}.mp4'`).join('\n');
        await ffmpeg.writeFile('concat.txt', concatList);
        
        // 合并
        await ffmpeg.exec([
            '-f', 'concat',
            '-safe', '0',
            '-i', 'concat.txt',
            '-c', 'copy',
            'output.mp4',
        ]);
        
        // 读取输出
        const data = await ffmpeg.readFile('output.mp4');
        return new Blob([data], { type: 'video/mp4' });
    }
}
```

### 7.4 渲染配置预设

```typescript
const RENDER_PRESETS = {
    // 快速预览（适合测试）
    preview: {
        width: 1280,
        height: 720,
        fps: 24,
        segmentDuration: 60,  // 1分钟一段
    },
    
    // 标准输出
    standard: {
        width: 1920,
        height: 1080,
        fps: 30,
        segmentDuration: 30,  // 30秒一段
    },
    
    // 高质量输出
    high: {
        width: 1920,
        height: 1080,
        fps: 60,
        segmentDuration: 20,  // 20秒一段（更频繁保存）
    },
};
```

---

## 八、性能与成本分析

### 8.1 渲染时间预估

#### 浏览器端渲染

| 视频时长 | 分辨率 | 帧数 | 预估渲染时间 | 内存占用 |
|---------|--------|------|-------------|---------|
| 30秒 | 1080p | 900帧 | 1-2分钟 | ~500MB |
| 1分钟 | 1080p | 1800帧 | 3-5分钟 | ~800MB |
| 3分钟 | 1080p | 5400帧 | 8-15分钟 | ~1.5GB |
| 5分钟 | 1080p | 9000帧 | 15-25分钟 | ~2GB |
| 10分钟 | 1080p | 18000帧 | 30-50分钟 | ~3GB |

#### AWS Lambda渲染

| 视频时长 | 分辨率 | Lambda实例数 | 预估渲染时间 | 说明 |
|---------|--------|-------------|-------------|------|
| 1分钟 | 1080p | 2个 | 1-2分钟 | 2个分段并行 |
| 3分钟 | 1080p | 6个 | 1-2分钟 | 6个分段并行 |
| 5分钟 | 1080p | 10个 | 2-3分钟 | 10个分段并行 |
| 10分钟 | 1080p | 20个 | 2-3分钟 | 20个分段并行 |
| 30分钟 | 1080p | 60个 | 5-8分钟 | 60个分段并行 |

**Lambda优势**：
- 并行渲染，时间不受视频长度线性增长
- 用户无需等待，后台异步处理
- 支持通知机制（邮件/Webhook）告知渲染完成

### 8.2 AWS Lambda成本估算

#### 计算成本（us-east-1）

| 项目 | 规格 | 单价 | 备注 |
|------|------|------|------|
| Lambda请求 | 2048MB内存 | $0.0000083333/秒 | 前400,000 GB-秒免费 |
| Lambda请求次数 | 每次 | $0.0000002 | 前100万次请求免费 |
| 数据传输出 | R2到Lambda | 免费 | AWS内部传输 |
| 数据传输出 | R2到用户 | 免费 | Cloudflare免费出站 |

#### 月度成本估算（假设每月1000个10分钟视频）

```
计算假设：
- 每个视频：10分钟 = 600秒
- 分段数：20个（每段30秒）
- 每段渲染时间：约45秒（Lambda执行时间）
- 总Lambda执行时间：20 × 45秒 = 900秒
- 内存：2048MB

月度计算：
- 总Lambda执行时间：1000视频 × 900秒 = 900,000秒
- GB-秒：900,000秒 × 2GB = 1,800,000 GB-秒
- 免费额度：400,000 GB-秒
- 计费GB-秒：1,400,000 GB-秒
- 计算成本：1,400,000 × $0.0000083333 = $11.67

总成本估算：约 $12/月（不含R2存储）
```

### 8.3 Cloudflare R2存储成本

| 项目 | 单价 | 备注 |
|------|------|------|
| 存储 | $0.015/GB/月 | 前10GB免费 |
| Class A操作 | $4.50/百万次 | 写入操作 |
| Class B操作 | $0.36/百万次 | 读取操作 |
| 出站流量 | 免费 | 与S3主要区别 |

#### 月度存储成本估算

```
计算假设：
- 每个视频：500MB（10分钟1080p）
- 保留时长：7天（分段临时存储）+ 30天（最终视频）
- 每月新视频：1000个

存储计算：
- 最终视频存储：1000 × 500MB = 500GB
- 分段临时存储（平均保留1天）：1000 × 500MB × (1/30) = 17GB
- 总存储：约520GB

存储成本：
- 免费额度：10GB
- 计费存储：510GB
- 月度存储成本：510 × $0.015 = $7.65

总存储成本：约 $8/月
```

### 8.4 总成本对比

| 渲染方案 | 服务器成本 | 存储成本 | 总成本/月 | 优势 |
|---------|-----------|---------|----------|------|
| 自建渲染服务器 | $100-200 | $10 | $110-210 | 完全可控 |
| AWS Lambda + R2 | $12 | $8 | $20 | 按需付费，弹性扩展 |
| 纯浏览器渲染 | $0 | $8 | $8 | 零服务器成本 |

### 8.5 性能优化策略

| 策略 | 效果 | 实现复杂度 | 适用场景 |
|------|------|-----------|---------|
| Lambda并行渲染 | 渲染时间降低90% | 中 | 中长视频 |
| 分段渲染 | 支持断点续传 | 中 | 浏览器端 |
| 降低分辨率 | 720p渲染速度提升2x | 低 | 预览模式 |
| 减少FPS | 24fps减少20%帧数 | 低 | 预览模式 |
| R2 CDN加速 | 全球分发，加载快 | 低 | 所有场景 |
| Web Worker | 不阻塞主线程 | 高 | 浏览器渲染 |
| OffscreenCanvas | GPU加速 | 高 | 浏览器渲染 |

---

## 九、API设计

### 9.1 渲染API（AWS Lambda）

```python
# agent/src/api_ppt.py

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uuid
import json

router = APIRouter(prefix="/api/v1/ppt")

class RenderRequest(BaseModel):
    slides: List[dict]
    video_config: dict
    tts_mode: str = "server"  # "web" or "server"
    render_mode: str = "lambda"  # "browser" or "lambda"
    
class RenderJobResponse(BaseModel):
    job_id: str
    status: str
    message: str

@router.post("/render", response_model=RenderJobResponse)
async def submit_render_job(request: RenderRequest):
    """提交渲染任务到AWS Lambda"""
    job_id = str(uuid.uuid4())
    
    # 1. 生成TTS音频（如果使用服务端TTS）
    tts_urls = []
    if request.tts_mode == "server":
        narrations = [slide.get("narration", "") for slide in request.slides]
        tts_urls = await generate_tts_batch(narrations)
    
    # 2. 上传composition到R2
    composition = {
        "id": f"ppt-video-{job_id}",
        "slides": request.slides,
        "videoConfig": request.video_config,
        "ttsAudios": tts_urls,
    }
    await r2_client.upload_composition(job_id, composition)
    
    # 3. 计算分段并发送到SQS
    total_duration = sum(s.get("duration", 120) for s in request.slides)
    num_segments = math.ceil(total_duration / 30)  # 30秒一段
    
    for i in range(num_segments):
        await sqs_client.send_message(
            queue_url=RENDER_QUEUE_URL,
            message_body={
                "job_id": job_id,
                "segment_index": i,
                "start_frame": i * 30 * request.video_config["fps"],
                "end_frame": min((i + 1) * 30, total_duration) * request.video_config["fps"],
            }
        )
    
    # 4. 更新任务状态
    await r2_client.update_job_status(job_id, {
        "status": "pending",
        "total_segments": num_segments,
        "completed_segments": 0,
        "created_at": datetime.utcnow().isoformat(),
    })
    
    return RenderJobResponse(
        job_id=job_id,
        status="pending",
        message=f"渲染任务已提交，共{num_segments}个分段"
    )

@router.get("/render/{job_id}/status")
async def get_render_status(job_id: str):
    """查询渲染任务状态"""
    status = await r2_client.get_job_status(job_id)
    
    # 检查所有分段是否完成
    segments = await r2_client.list_segments(job_id)
    completed = [s for s in segments if s["status"] == "completed"]
    
    return {
        "job_id": job_id,
        "status": status["status"],
        "progress": len(completed) / len(segments) if segments else 0,
        "completed_segments": len(completed),
        "total_segments": len(segments),
        "video_url": status.get("video_url"),
    }

@router.post("/render/{job_id}/merge")
async def merge_render_segments(job_id: str):
    """合并所有分段（由最后一个完成的分段触发）"""
    # 检查所有分段是否完成
    segments = await r2_client.list_segments(job_id)
    if any(s["status"] != "completed" for s in segments):
        raise HTTPException(status_code=400, detail="Not all segments completed")
    
    # 发送合并任务到SQS
    await sqs_client.send_message(
        queue_url=MERGE_QUEUE_URL,
        message_body={
            "job_id": job_id,
            "total_segments": len(segments),
            "output_key": f"jobs/{job_id}/output/final.mp4",
        }
    )
    
    return {"status": "merging", "message": "视频合并任务已提交"}
```

### 9.2 服务端API（最小化）

```python
@router.post("/chat")
async def chat_with_ppt_assistant(message: str, context: dict):
    """与PPT助手对话（LLM调用）"""
    response = await process_conversation(message, context)
    return {
        "response": response.text,
        "outline": response.outline,    # 如果生成了大纲
        "slides": response.slides,      # 如果生成了内容
    }

@router.post("/tts/generate")
async def generate_tts(request: TTSRequest):
    """生成高质量TTS音频"""
    audio_urls = await generate_tts_audios(request.texts, request.options)
    return {"audioUrls": audio_urls}

@router.post("/export/pptx")
async def export_pptx(request: PPTExportRequest):
    """导出PPTX文件（可选）"""
    pptx_url = await generate_pptx(request.slides)
    return {"pptxUrl": pptx_url}

@router.post("/tts/batch")
async def generate_tts_batch(texts: List[str]):
    """批量生成TTS音频，返回R2 URL"""
    audio_urls = []
    for text in texts:
        # 调用TTS服务生成音频
        audio_buffer = await tts_service.generate(text)
        
        # 上传到R2
        audio_key = f"tts/{uuid.uuid4()}.mp3"
        await r2_client.upload_audio(audio_key, audio_buffer)
        
        # 获取公开URL
        audio_url = r2_client.get_public_url(audio_key)
        audio_urls.append(audio_url)
    
    return {"audioUrls": audio_urls}
```

### 9.3 前端渲染API

```typescript
// src/app/api/render/submit/route.ts

import { NextRequest, NextResponse } from 'next/server';
import { RenderCoordinator } from '@/lib/render/render-coordinator';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { slides, videoConfig, ttsAudios } = body;
    
    const coordinator = new RenderCoordinator();
    const jobId = await coordinator.submitRenderJob({
      jobId: crypto.randomUUID(),
      slides,
      videoConfig,
      ttsAudios,
    });
    
    return NextResponse.json({
      success: true,
      jobId,
      status: 'pending',
    });
    
  } catch (error) {
    return NextResponse.json(
      { success: false, error: error.message },
      { status: 500 }
    );
  }
}
```

```typescript
// src/app/api/render/status/[jobId]/route.ts

import { NextRequest, NextResponse } from 'next/server';
import { RenderCoordinator } from '@/lib/render/render-coordinator';

export async function GET(
  request: NextRequest,
  { params }: { params: { jobId: string } }
) {
  try {
    const { jobId } = params;
    const coordinator = new RenderCoordinator();
    const status = await coordinator.getJobStatus(jobId);
    
    return NextResponse.json({
      success: true,
      ...status,
    });
    
  } catch (error) {
    return NextResponse.json(
      { success: false, error: error.message },
      { status: 500 }
    );
  }
}
```

---

## 十、文件结构

```
src/
├── components/
│   ├── ppt-editor/
│   │   ├── PPTEditor.tsx           # 主编辑器
│   │   ├── Canvas.tsx              # 画布组件
│   │   ├── Toolbar.tsx             # 工具栏
│   │   ├── SlideList.tsx           # 幻灯片列表
│   │   ├── PropertyPanel.tsx       # 属性面板
│   │   └── ElementRenderer.tsx     # 元素渲染器
│   ├── RemotionPreview.tsx         # 视频预览
│   ├── RenderProgress.tsx          # 渲染进度
│   └── PPTVideoGenerator.tsx       # 主流程组件
│
├── store/
│   └── ppt-store.ts                # PPT状态管理
│
├── remotion/
│   └── compositions/
│       └── PPTVideo.tsx            # Remotion视频组件
│
├── lib/
│   ├── ppt-to-remotion/
│   │   └── mapper.ts               # PPT→Remotion转换
│   ├── ppt-video/
│   │   ├── segmented-renderer.ts   # 浏览器端分段渲染器
│   │   ├── video-merger.ts         # 视频合并
│   │   └── render-state-machine.ts # 渲染状态机
│   ├── render/
│   │   ├── render-coordinator.ts   # Lambda渲染协调器
│   │   └── lambda-client.ts        # Lambda API客户端
│   ├── storage/
│   │   └── r2-client.ts            # Cloudflare R2客户端
│   ├── pptx/
│   │   └── pptx-exporter.ts        # PPTX导出
│   └── tts/
│       └── tts-service.ts          # TTS服务
│
└── app/
    └── api/
        ├── chat/route.ts           # 对话API
        ├── tts/route.ts            # TTS API
        └── render/
            ├── submit/route.ts     # 提交渲染任务
            └── status/[jobId]/route.ts  # 查询渲染状态

lambda/
├── src/
│   ├── handlers/
│   │   ├── render-segment.ts       # 分段渲染Worker
│   │   └── merge-video.ts          # 视频合并Worker
│   └── utils/
│       └── r2-helper.ts            # R2操作辅助函数
├── layer/                          # Lambda层（Remotion + FFmpeg）
│   └── nodejs/
│       └── node_modules/
└── serverless.yml                  # Serverless Framework配置

agent/
└── src/
    ├── api_ppt.py                  # PPT相关API端点
    ├── ppt_conversation/
    │   └── state.py                # LangGraph对话状态
    └── ppt_generation/
        ├── outline_generator.py    # 大纲生成
        └── content_generator.py    # 内容生成
```

---

## 十一、技术栈总结

| 组件 | 技术 | 参考来源 |
|------|------|---------|
| 对话状态机 | LangGraph | 当前项目 + OpenMAIC多轮对话 |
| 大纲生成 | LLM + JSON Schema | OpenMAIC `outline-generator.ts` |
| 内容生成 | LLM + Vision | OpenMAIC `scene-generator.ts` |
| PPTX导出 | svg_to_pptx | OpenMAIC `use-export-pptx.ts` |
| LaTeX支持 | temml + mathml2omml | OpenMAIC `latex-to-omml.ts` |
| 视频合成 | Remotion | 当前项目 remotion-mapper |
| 云端渲染 | AWS Lambda | 本方案设计 |
| 存储 | Cloudflare R2 | 当前项目已有集成 |
| 任务队列 | AWS SQS | 本方案设计 |
| 分段渲染 | IndexedDB + FFmpeg.wasm | 本方案设计（浏览器端备选） |
| TTS | Web Speech API + 服务端TTS | 双模式 |

---

## 十二、AWS Lambda部署指南

### 12.1 前置条件

1. **AWS账户配置**
   ```bash
   # 安装AWS CLI
   brew install awscli
   
   # 配置AWS凭证
   aws configure
   # 输入 Access Key ID, Secret Access Key, Region (us-east-1)
   ```

2. **Serverless Framework安装**
   ```bash
   npm install -g serverless
   ```

3. **Cloudflare R2配置**
   - 创建R2 Bucket
   - 获取Account ID, Access Key, Secret Key
   - 配置公开访问域名（可选）

### 12.2 Lambda层部署

```bash
cd lambda

# 安装依赖
npm install

# 部署Lambda层
serverless deploy --stage prod

# 输出：
# - remotionLayerArn: arn:aws:lambda:us-east-1:xxx:layer:remotion-layer
```

### 12.3 环境变量配置

```bash
# .env.production
R2_BUCKET=ppt-video-bucket
R2_ACCOUNT_ID=xxx
R2_ACCESS_KEY=xxx
R2_SECRET_KEY=xxx
R2_PUBLIC_DOMAIN=cdn.yourdomain.com

AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx

SQS_RENDER_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/xxx/render-queue
SQS_MERGE_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/xxx/merge-queue
```

### 12.4 SQS队列创建

```bash
# 创建渲染队列
aws sqs create-queue \
  --queue-name ppt-render-queue \
  --attributes VisibilityTimeout=900

# 创建合并队列
aws sqs create-queue \
  --queue-name ppt-merge-queue \
  --attributes VisibilityTimeout=600
```

### 12.5 IAM权限配置

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
      ],
      "Resource": [
        "arn:aws:sqs:us-east-1:xxx:ppt-render-queue",
        "arn:aws:sqs:us-east-1:xxx:ppt-merge-queue"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::ppt-video-bucket",
        "arn:aws:s3:::ppt-video-bucket/*"
      ]
    }
  ]
}
```

---

## 十三、实施计划

### 13.1 工作量估计

| 优先级 | 任务 | 工作量 | 依赖 | 备注 |
|--------|------|--------|------|------|
| P0 | LangGraph对话状态机 | 3天 | 无 | 核心交互流程 |
| P0 | PPT大纲生成器 | 2天 | P0 | LLM集成 |
| P1 | PPT内容生成器 | 3天 | P0 | LLM集成 |
| P1 | PPTX导出器 | 2天 | P1 | svg_to_pptx |
| P2 | PPT编辑器 | 3天 | P1 | Canvas编辑 |
| P2 | Remotion视频组件 | 2天 | P2 | 视频模板 |
| P2 | AWS Lambda渲染 | 3天 | P2 | 云端渲染 |
| P2 | R2存储集成 | 1天 | P2 | 已有基础 |
| P3 | TTS集成 | 1天 | P2 | 双模式 |
| P3 | 浏览器端渲染备选 | 2天 | P2 | IndexedDB |

**总工作量：约22天**

### 13.2 里程碑

| 里程碑 | 时间 | 交付物 | 验收标准 |
|--------|------|--------|----------|
| **M1** | 第1周 | 对话状态机 + 大纲生成 | 用户可通过对话生成PPT大纲 |
| **M2** | 第2周 | 内容生成 + PPTX导出 | 可生成完整PPT并导出PPTX |
| **M3** | 第3周 | 编辑器 + Remotion组件 | 可实时预览视频效果 |
| **M4** | 第4周 | Lambda渲染 + R2集成 | 可云端渲染并存储视频 |
| **M5** | 第5周 | TTS集成 + 优化 | 完整的讲解视频生成流程 |

### 13.3 开发顺序建议

```
Week 1: M1
├── Day 1-2: LangGraph状态机搭建
├── Day 3-4: 大纲生成器实现
└── Day 5: 对话流程联调

Week 2: M2
├── Day 1-2: 内容生成器实现
├── Day 3-4: PPTX导出器实现
└── Day 5: 导出功能测试

Week 3: M3
├── Day 1-2: PPT编辑器核心组件
├── Day 3: Remotion视频组件
├── Day 4: 预览功能集成
└── Day 5: 编辑器测试

Week 4: M4
├── Day 1: Lambda层部署
├── Day 2: 渲染Worker实现
├── Day 3: 合并Worker实现
├── Day 4: R2存储集成
└── Day 5: 云端渲染测试

Week 5: M5
├── Day 1-2: TTS服务集成
├── Day 3: 浏览器端渲染备选
├── Day 4: 性能优化
└── Day 5: 完整流程测试
```

---

## 十四、风险与对策

| 风险 | 影响 | 概率 | 对策 |
|------|------|------|------|
| 浏览器内存限制 | 长视频浏览器渲染失败 | 中 | 提供Lambda云端渲染选项 |
| Lambda冷启动延迟 | 渲染任务启动慢 | 低 | 使用Provisioned Concurrency |
| Web Speech API质量差 | 预览体验不佳 | 高 | 提示用户使用服务端TTS |
| FFmpeg.wasm加载慢 | 首次合并延迟 | 中 | 预加载 + CDN加速 |
| R2存储成本超预算 | 月度费用增加 | 低 | 设置生命周期策略，自动清理临时文件 |
| Lambda并发限制 | 高峰期渲染排队 | 中 | 申请提高并发配额 |
| Remotion浏览器兼容性 | 部分浏览器不支持 | 低 | 提供Lambda渲染作为备选 |
| SQS消息积压 | 渲染任务延迟 | 低 | 设置CloudWatch告警 |

### 14.1 降级方案

| 场景 | 降级方案 |
|------|----------|
| Lambda不可用 | 自动切换到浏览器端渲染 |
| R2存储失败 | 临时使用本地存储 + 用户手动下载 |
| TTS服务不可用 | 使用Web Speech API |
| 高并发渲染 | 排队机制 + 预计等待时间提示 |

### 14.2 监控与告警

```yaml
# CloudWatch告警配置

PPTRenderQueueDepth:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: PPT-Render-Queue-Depth
    AlarmDescription: 渲染队列积压超过阈值
    MetricName: ApproximateNumberOfMessagesVisible
    Namespace: AWS/SQS
    Dimensions:
      - Name: QueueName
        Value: ppt-render-queue
    Threshold: 100
    EvaluationPeriods: 3
    Period: 300
    ComparisonOperator: GreaterThanThreshold
    AlarmActions:
      - arn:aws:sns:us-east-1:xxx:alert-topic

PPTLambdaErrors:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: PPT-Lambda-Errors
    AlarmDescription: Lambda错误率超过阈值
    MetricName: Errors
    Namespace: AWS/Lambda
    Dimensions:
      - Name: FunctionName
        Value: ppt-render-segment
    Threshold: 10
    EvaluationPeriods: 3
    Period: 300
    ComparisonOperator: GreaterThanThreshold
```

---

## 十五、参考资料

### 15.1 OpenMAIC项目
- 仓库地址：https://github.com/THU-MAIC/OpenMAIC
- 关键文件：
  - `lib/generation/outline-generator.ts` - 大纲生成
  - `lib/generation/scene-generator.ts` - 内容生成
  - `lib/export/use-export-pptx.ts` - PPTX导出
  - `lib/export/latex-to-omml.ts` - LaTeX转换
  - `lib/playback/engine.ts` - 播放引擎

### 15.2 当前项目
- 关键文件：
  - `agent/src/agent_skills.py` - 分镜规划
  - `agent/src/creative_agent.py` - 叙事结构
  - `src/lib/render/remotion-mapper.ts` - Remotion映射
  - `src/remotion/compositions/templates/` - 视频模板
  - `agent/src/r2.py` - R2存储集成

### 15.3 技术文档
- **Remotion**
  - 官方文档：https://remotion.dev
  - Lambda渲染：https://remotion.dev/docs/lambda
  - Server-Side Rendering：https://remotion.dev/docs/ssr

- **AWS Lambda**
  - Lambda开发者指南：https://docs.aws.amazon.com/lambda/
  - SQS触发器：https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html
  - Lambda层：https://docs.aws.amazon.com/lambda/latest/dg/configuration-layers.html

- **Cloudflare R2**
  - R2文档：https://developers.cloudflare.com/r2/
  - S3兼容API：https://developers.cloudflare.com/r2/api/s3/
  - 公开存储桶：https://developers.cloudflare.com/r2/buckets/public-buckets/

- **其他**
  - svg_to_pptx: https://gitbrent.github.io/SVG-to-PPTX/
  - FFmpeg.wasm: https://ffmpegwasm.netlify.app
  - LangGraph: https://langchain-ai.github.io/langgraph/
  - Serverless Framework: https://www.serverless.com/

### 15.4 成本计算参考
- AWS Lambda定价：https://aws.amazon.com/lambda/pricing/
- Cloudflare R2定价：https://developers.cloudflare.com/r2/pricing/
- AWS免费额度：https://aws.amazon.com/free/
