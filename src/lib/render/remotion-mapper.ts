import { ItemType, TimelineItem, VideoProject } from "../types";
import {
  BuildRenderJobOptions,
  RenderAudioTrack,
  RenderJobRequest,
  RenderJobSummary,
  RenderLayer,
  RemotionCompositionPayload,
  getProjectFps,
  secondsToFrames,
} from "./types";

function normalizeDurationFrames(item: TimelineItem, fps: number): number {
  return Math.max(1, secondsToFrames(item.duration, fps));
}

function buildLayer(item: TimelineItem, fps: number): RenderLayer | null {
  const startFrame = secondsToFrames(item.startTime, fps);
  const durationInFrames = normalizeDurationFrames(item, fps);

  if (item.type === ItemType.VIDEO) {
    return {
      id: item.id,
      itemType: item.type,
      type: "video",
      trackId: item.trackId,
      name: item.name,
      source: item.content,
      startFrame,
      durationInFrames,
      style: item.style,
    };
  }

  if (item.type === ItemType.IMAGE) {
    return {
      id: item.id,
      itemType: item.type,
      type: "image",
      trackId: item.trackId,
      name: item.name,
      source: item.content,
      startFrame,
      durationInFrames,
      style: item.style,
    };
  }

  if (item.type === ItemType.TEXT) {
    return {
      id: item.id,
      itemType: item.type,
      type: "text",
      trackId: item.trackId,
      name: item.name,
      text: item.content,
      startFrame,
      durationInFrames,
      style: item.style,
    };
  }

  return null;
}

function buildAudioTrack(item: TimelineItem, fps: number): RenderAudioTrack | null {
  if (item.type !== ItemType.AUDIO) return null;

  return {
    id: item.id,
    trackId: item.trackId,
    name: item.name,
    source: item.content,
    startFrame: secondsToFrames(item.startTime, fps),
    durationInFrames: normalizeDurationFrames(item, fps),
    volume: item.style?.opacity ?? 1,
  };
}

export function toRemotionComposition(project: VideoProject): RemotionCompositionPayload {
  const fps = getProjectFps(project);
  const durationInFrames = Math.max(1, secondsToFrames(project.duration, fps));

  const allItems = project.tracks
    .flatMap((track) => track.items)
    .sort((a, b) => {
      if (a.trackId !== b.trackId) return a.trackId - b.trackId;
      if (a.startTime !== b.startTime) return a.startTime - b.startTime;
      return a.id.localeCompare(b.id);
    });

  const layers = allItems
    .map((item) => buildLayer(item, fps))
    .filter((layer): layer is RenderLayer => layer !== null);

  const audioTracks = allItems
    .map((item) => buildAudioTrack(item, fps))
    .filter((track): track is RenderAudioTrack => track !== null);

  return {
    id: `composition-${project.runId || "editor"}`,
    width: project.width,
    height: project.height,
    fps,
    durationInFrames,
    backgroundColor: project.backgroundColor || "#000000",
    layers,
    audioTracks,
    metadata: {
      projectName: project.name,
      runId: project.runId,
      threadId: project.threadId,
      generatedAt: new Date().toISOString(),
    },
  };
}

export function buildRenderJobRequest(
  project: VideoProject,
  options: BuildRenderJobOptions = {},
): RenderJobRequest {
  const composition = toRemotionComposition({
    ...project,
    runId: options.runId || project.runId,
    threadId: options.threadId || project.threadId,
  });

  return {
    engine: options.engine || "remotion",
    project: {
      name: project.name,
      runId: options.runId || project.runId,
      threadId: options.threadId || project.threadId,
    },
    composition,
  };
}

export function summarizeRenderJob(request: RenderJobRequest): RenderJobSummary {
  const { composition } = request;
  return {
    fps: composition.fps,
    durationInFrames: composition.durationInFrames,
    durationSeconds: composition.durationInFrames / composition.fps,
    layerCount: composition.layers.length,
    audioTrackCount: composition.audioTracks.length,
  };
}

