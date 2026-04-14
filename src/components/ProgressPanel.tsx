"use client";

import React from "react";
import { CheckCircle2, Clock3, Loader2, Sparkles, Video } from "lucide-react";
import { useProject } from "@/contexts/ProjectContext";
import { useT } from "@/lib/i18n";

const PHASE_WEIGHT: Record<string, number> = {
  idle: 0,
  configuring: 8,
  generating_storyboard: 28,
  storyboard_ready: 42,
  generating_images: 60,
  images_ready: 74,
  generating_videos: 88,
  stitching: 94,
  rendering: 96,
  videos_ready: 98,
  completed: 100,
  error: 0,
};

function getPhaseLabel(phase: string, t: ReturnType<typeof useT>) {
  switch (phase) {
    case "generating_storyboard":
      return t("progress.generatingStoryboard");
    case "storyboard_ready":
      return t("progress.storyboardReady");
    case "generating_images":
      return t("progress.generatingImages");
    case "images_ready":
      return t("progress.imagesReady");
    case "generating_videos":
      return t("progress.generatingVideos");
    case "stitching":
      return t("progress.stitching");
    case "rendering":
      return t("progress.rendering");
    case "videos_ready":
      return t("progress.videosReady");
    case "completed":
      return t("progress.completed");
    case "error":
      return t("progress.failed");
    default:
      return t("progress.waiting");
  }
}

export default function ProgressPanel({ compact = false }: { compact?: boolean }) {
  const t = useT();
  const { phase, taskSummary, scenes, finalVideoUrl } = useProject();

  if (phase === "idle" || phase === "configuring") return null;

  const progress = PHASE_WEIGHT[phase] ?? 0;
  const isRunning = [
    "generating_storyboard",
    "generating_images",
    "generating_videos",
    "stitching",
    "rendering",
  ].includes(phase);

  return (
    <div className={`${compact ? "mx-3 mt-2 p-3" : "mx-4 mt-4 p-4"} rounded-2xl border border-white/[0.08] bg-gradient-to-br from-[#E11D48]/8 to-purple-500/6`}>
        <div className={`${compact ? "mb-2" : "mb-3"} flex items-center justify-between`}>
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
          <Sparkles className="h-4 w-4 text-[#E11D48]" />
          {t("progress.title")}
        </div>
        <div className="text-xs text-gray-400">{progress}%</div>
      </div>

      <div className="h-2 w-full overflow-hidden rounded-full bg-white/[0.06]">
        <div
          className="h-full rounded-full bg-gradient-to-r from-[#E11D48] to-[#9333EA] transition-all duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>

      <div className={`${compact ? "mt-2" : "mt-3"} flex items-center justify-between text-xs`}>
        <div className="flex items-center gap-1.5 text-gray-300">
          {phase === "completed" ? (
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
          ) : isRunning ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-[#E11D48]" />
          ) : (
            <Clock3 className="h-3.5 w-3.5 text-gray-400" />
          )}
          <span>{getPhaseLabel(phase, t)}</span>
        </div>

        <div className="text-gray-500">
          {taskSummary.total > 0
            ? `${taskSummary.succeeded}/${taskSummary.total}`
            : t("progress.sceneCount", { count: scenes.length })}
        </div>
      </div>

      {finalVideoUrl && (
        <div className={`${compact ? "mt-2" : "mt-3"} inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-1 text-[11px] text-emerald-400`}>
          <Video className="h-3.5 w-3.5" />
          {t("progress.finalVideoReady")}
        </div>
      )}
    </div>
  );
}
