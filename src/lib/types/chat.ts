import { nanoid } from 'nanoid';

export type ChatSessionStatus =
  | 'initial'
  | 'outlining'
  | 'generating'
  | 'rendering'
  | 'completed'
  | 'failed';

export interface ChatSession {
  id: string;
  status: ChatSessionStatus;
  requirement?: string;
  language: 'zh-CN' | 'en-US';
  outlines: SceneOutline[];
  scenes: Scene[];
  createdAt: number;
  updatedAt: number;
}

export interface SceneOutline {
  id: string;
  title: string;
  description: string;
  keyPoints: string[];
  order: number;
  estimatedDuration?: number;
  language?: 'zh-CN' | 'en-US';
  mediaGenerations?: MediaGenerationRequest[];
}

export interface MediaGenerationRequest {
  type: 'image' | 'video';
  prompt: string;
  aspectRatio: '16:9' | '9:16' | '1:1' | '4:3';
  elementId?: string;
}

export interface Scene {
  id: string;
  outlineId: string;
  title: string;
  content: SlideContent;
  actions: SceneAction[];
  remarks?: string;
}

export interface SlideContent {
  elements: PPTElement[];
  background?: SlideBackground;
}

export interface PPTElement {
  id: string;
  type: 'text' | 'image' | 'video' | 'shape' | 'chart' | 'table' | 'latex' | 'audio';
  left: number;
  top: number;
  width: number;
  height: number;
  content?: string;
  src?: string;
  style?: ElementStyle;
}

export interface SlideBackground {
  type: 'solid' | 'gradient' | 'image';
  color?: string;
  gradient?: { start: string; end: string; angle: number };
  image?: string;
}

export interface ElementStyle {
  fontSize?: number;
  fontFamily?: string;
  color?: string;
  backgroundColor?: string;
  bold?: boolean;
  italic?: boolean;
  align?: 'left' | 'center' | 'right';
  verticalAlign?: 'top' | 'middle' | 'bottom';
  opacity?: number;
  borderRadius?: number;
  shadow?: boolean;
}

export interface SceneAction {
  type: 'speech' | 'spotlight' | 'draw' | 'discussion' | 'transition';
  text?: string;
  elementId?: string;
  agentId?: string;
  duration?: number;
  startTime?: number;
}

export interface GenerationProgress {
  currentStage: 1 | 2 | 3 | 4;
  overallProgress: number;
  stageProgress: number;
  statusMessage: string;
  scenesGenerated: number;
  totalScenes: number;
}

export function createSceneOutline(partial: Partial<SceneOutline> & { title: string }): SceneOutline {
  return {
    id: partial.id || nanoid(8),
    title: partial.title,
    description: partial.description || '',
    keyPoints: partial.keyPoints || [],
    order: partial.order || 0,
    estimatedDuration: partial.estimatedDuration,
    language: partial.language,
    mediaGenerations: partial.mediaGenerations,
  };
}

export function createScene(outline: SceneOutline, content: SlideContent, actions: SceneAction[]): Scene {
  return {
    id: nanoid(8),
    outlineId: outline.id,
    title: outline.title,
    content,
    actions,
  };
}
