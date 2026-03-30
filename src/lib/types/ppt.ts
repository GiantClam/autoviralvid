/**
 * PPT 数据模型 (TypeScript)
 * 同时服务于 PPT生成(Feature A) 和 PPT/PDF视频生成(Feature B)
 */

// ── 大纲层 ─────────────────────────────────────────────────────────

export interface SlideOutline {
  id: string;
  order: number;
  title: string;
  description: string;
  keyPoints: string[];
  suggestedElements: string[];
  estimatedDuration: number; // seconds
}

export interface PresentationOutline {
  id: string;
  title: string;
  theme: string;
  slides: SlideOutline[];
  totalDuration: number; // seconds
  style: "professional" | "education" | "creative";
}

// ── 内容层 ─────────────────────────────────────────────────────────

export type SlideElementType =
  | "text"
  | "image"
  | "shape"
  | "chart"
  | "table"
  | "latex"
  | "video"
  | "audio";

export interface SlideElement {
  id: string;
  blockId?: string;
  type: SlideElementType;
  left: number;
  top: number;
  width: number;
  height: number;
  content?: string;
  src?: string;
  style?: Record<string, any>;
  chartType?: string;
  chartData?: Record<string, any>;
  tableRows?: string[][];
  tableColWidths?: number[];
  latexFormula?: string;
}

export interface SlideBackground {
  type: "solid" | "gradient" | "image";
  color?: string;
  gradient?: { start: string; end: string; angle: number };
  imageUrl?: string;
}

export interface SlideContent {
  id: string;
  slideId?: string;
  outlineId: string;
  order: number;
  title: string;
  elements: SlideElement[];
  background?: SlideBackground;
  narration: string;
  narrationAudioUrl?: string;
  speakerNotes: string;
  duration: number; // seconds
}

// ── 渲染层 (Feature B) ─────────────────────────────────────────────

export interface VideoRenderConfig {
  width: number;
  height: number;
  fps: number;
  transition: "fade" | "slide" | "wipe";
  bgmUrl?: string;
  bgmVolume: number;
  includeNarration: boolean;
  voiceStyle: string;
}

export interface RemotionSlidePresentation {
  slides: SlideContent[];
  bgmUrl?: string;
  bgmVolume?: number;
  defaultTransition?: "fade" | "slide" | "wipe";
}

export interface RenderJob {
  id: string;
  projectId: string;
  status: "pending" | "rendering" | "done" | "failed";
  progress: number;
  lambdaJobId?: string;
  outputUrl?: string;
  error?: string;
  createdAt: string;
  updatedAt: string;
}

// ── API 请求 ───────────────────────────────────────────────────────

export interface OutlineRequest {
  requirement: string;
  language: "zh-CN" | "en-US";
  numSlides: number;
  style: "professional" | "education" | "creative";
  purpose: string;
}

export interface ContentRequest {
  outline: PresentationOutline;
  language: "zh-CN" | "en-US";
}

export interface ExportRequest {
  slides: SlideContent[];
  title: string;
  author: string;
  deckId?: string;
  pptxSkill?: "minimax_pptx_generator";
  minimaxStyleVariant?: "auto" | "sharp" | "soft" | "rounded" | "pill";
  minimaxPaletteKey?: string;
  verbatimContent?: boolean;
  verbatim_content?: boolean;
  retryScope?: "deck" | "slide" | "block";
  retryHint?: string;
  targetSlideIds?: string[];
  targetBlockIds?: string[];
  idempotencyKey?: string;
  routeMode?: "auto" | "fast" | "standard" | "refine";
  route_mode?: "auto" | "fast" | "standard" | "refine";
  originalStyle?: boolean;
  disableLocalStyleRewrite?: boolean;
  original_style?: boolean;
  disable_local_style_rewrite?: boolean;
  visualPriority?: boolean;
  visual_priority?: boolean;
}

export interface ExportResponse {
  url: string;
  deck_id?: string;
  attempts?: number;
  retry_scope?: "deck" | "slide" | "block";
  diagnostics?: Record<string, any>[];
  route_mode?: "fast" | "standard" | "refine" | string;
  quality_score?: Record<string, any>;
  visual_qa?: Record<string, any>;
  observability_report?: Record<string, any>;
  skill?: "minimax_pptx_generator" | string;
  video_mode?: string;
  video_slide_count?: number;
  video_slides?: Record<string, any>[];
  generator_meta?: Record<string, any>;
}

export interface ParseRequest {
  fileUrl: string;
  fileType: "pptx" | "ppt" | "pdf";
}

export interface TTSRequest {
  texts: string[];
  voiceStyle: string;
}

export interface EnhanceRequest {
  slides: SlideContent[];
  language: "zh-CN" | "en-US";
  enhanceNarration: boolean;
  generateTts: boolean;
  voiceStyle: string;
}

export interface ApiResponse<T = any> {
  success: boolean;
  data?: T;
  error?: string;
}
