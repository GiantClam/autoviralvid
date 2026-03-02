export enum ItemType {
  VIDEO = 'video',
  IMAGE = 'image',
  TEXT = 'text',
  AUDIO = 'audio'
}

export interface TimelineItem {
  id: string;
  type: ItemType;
  content: string;
  startTime: number;
  duration: number;
  trackId: number;
  name: string;
  style?: {
    fontSize?: number;
    color?: string;
    backgroundColor?: string;
    x?: number;
    y?: number;
    width?: number;
    height?: number;
    opacity?: number;
    rotation?: number;
    scale?: number;
  };
}

export interface Track {
  id: number;
  type: 'video' | 'audio' | 'overlay';
  name: string;
  items: TimelineItem[];
}

export interface VideoProject {
  name: string;
  width: number;
  height: number;
  fps?: number;
  duration: number;
  backgroundColor?: string;
  tracks: Track[];
  runId?: string;
  threadId?: string;
}

export interface Asset {
  id: string;
  type: ItemType;
  url: string;
  name: string;
  thumbnail?: string;
}

export type StoryboardScene = {
  idx: number;
  desc: string;
  narration?: string;
  script?: string;
  prompt?: string;
}

export type Storyboard = {
  scenes: StoryboardScene[];
}

export type AgentState = {
  next_question?: string | null;
  options?: string[];
  status?: string | null;
  interaction_type?: string | null;
  node?: string | null;
  thoughts?: string | null;
  thought?: string | null;
  storyboard?: Storyboard;
  video_tasks?: Array<Record<string, unknown>>;
  collected_info?: Record<string, unknown>;
  run_id?: string;
  messages?: Array<Record<string, unknown>>;
  error?: string | null;
}
