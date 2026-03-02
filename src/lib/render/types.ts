import { ItemType, TimelineItem, VideoProject } from "../types";

export const DEFAULT_RENDER_FPS = 30;

export type RenderEngine = "native" | "remotion";

export type RenderLayerType = "video" | "image" | "text";

export type RenderLayer = {
  id: string;
  itemType: ItemType;
  type: RenderLayerType;
  trackId: number;
  name: string;
  source?: string;
  text?: string;
  startFrame: number;
  durationInFrames: number;
  style?: TimelineItem["style"];
};

export type RenderAudioTrack = {
  id: string;
  trackId: number;
  name: string;
  source: string;
  startFrame: number;
  durationInFrames: number;
  volume: number;
};

export type RemotionCompositionPayload = {
  id: string;
  width: number;
  height: number;
  fps: number;
  durationInFrames: number;
  backgroundColor: string;
  layers: RenderLayer[];
  audioTracks: RenderAudioTrack[];
  metadata: {
    projectName: string;
    runId?: string;
    threadId?: string;
    generatedAt: string;
  };
};

export type RenderJobRequest = {
  engine: RenderEngine;
  project: {
    name: string;
    runId?: string;
    threadId?: string;
  };
  composition: RemotionCompositionPayload;
};

export type RenderJobSummary = {
  fps: number;
  durationInFrames: number;
  durationSeconds: number;
  layerCount: number;
  audioTrackCount: number;
};

export type BuildRenderJobOptions = {
  engine?: RenderEngine;
  runId?: string;
  threadId?: string;
};

export function getProjectFps(project: VideoProject): number {
  return Number.isFinite(project.fps) && (project.fps || 0) > 0
    ? Math.floor(project.fps as number)
    : DEFAULT_RENDER_FPS;
}

export function secondsToFrames(seconds: number, fps: number): number {
  return Math.max(0, Math.round(seconds * fps));
}

