"use client";

import React, { useState, useCallback } from "react";
import { useProject } from "@/contexts/ProjectContext";
import {
  Play,
  RefreshCw,
  Download,
  Film,
  CheckCircle,
  AlertCircle,
  Clock,
  Loader2,
  X,
} from "lucide-react";
import type { VideoTask } from "@/lib/project-client";

// ── Status helpers ──

const STATUS_CONFIG: Record<
  VideoTask["status"],
  { label: string; bg: string; text: string; pulse?: boolean; icon: React.ElementType }
> = {
  pending: {
    label: "等待中",
    bg: "bg-gray-700",
    text: "text-gray-400",
    icon: Clock,
  },
  processing: {
    label: "处理中",
    bg: "bg-yellow-500/20",
    text: "text-yellow-400",
    pulse: true,
    icon: Loader2,
  },
  submitted: {
    label: "已提交",
    bg: "bg-yellow-500/20",
    text: "text-yellow-400",
    pulse: true,
    icon: Loader2,
  },
  succeeded: {
    label: "已完成",
    bg: "bg-green-500/20",
    text: "text-green-400",
    icon: CheckCircle,
  },
  failed: {
    label: "失败",
    bg: "bg-red-500/20",
    text: "text-red-400",
    icon: AlertCircle,
  },
};

function StatusBadge({ status }: { status: VideoTask["status"] }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending;
  const Icon = cfg.icon;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${cfg.bg} ${cfg.text} ${cfg.pulse ? "animate-pulse" : ""}`}
    >
      <Icon className="h-3 w-3" />
      {cfg.label}
    </span>
  );
}

// ── Video preview modal ──

function PreviewModal({
  url,
  clipIdx,
  onClose,
}: {
  url: string;
  clipIdx: number;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-3xl mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute -top-10 right-0 text-gray-400 hover:text-white transition-colors"
        >
          <X className="h-6 w-6" />
        </button>
        <div className="rounded-xl overflow-hidden bg-gray-900 shadow-2xl ring-1 ring-white/10">
          <div className="px-4 py-2 border-b border-white/10 text-sm text-gray-400">
            片段 {clipIdx + 1} 预览
          </div>
          <video
            src={url}
            controls
            autoPlay
            className="w-full aspect-video bg-black"
          />
        </div>
      </div>
    </div>
  );
}

// ── Clip card ──

function ClipCard({
  task,
  onRegenerate,
  onPreview,
}: {
  task: VideoTask;
  onRegenerate: (clipIdx: number) => void;
  onPreview: (clipIdx: number) => void;
}) {
  const isProcessing = task.status === "processing" || task.status === "submitted";

  return (
    <div className="group relative flex flex-col rounded-xl bg-gray-900/80 ring-1 ring-white/[0.06] hover:ring-white/[0.12] transition-all overflow-hidden">
      {/* Video preview area */}
      <div className="relative aspect-video bg-black overflow-hidden rounded-t-xl">
        {task.video_url ? (
          <video
            src={task.video_url}
            muted
            playsInline
            preload="metadata"
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            {isProcessing ? (
              <Loader2 className="h-8 w-8 text-yellow-400/60 animate-spin" />
            ) : task.status === "failed" ? (
              <AlertCircle className="h-8 w-8 text-red-400/60" />
            ) : (
              <Film className="h-8 w-8 text-gray-600" />
            )}
          </div>
        )}

        {/* Overlay play button for completed clips */}
        {task.video_url && (
          <button
            onClick={() => onPreview(task.clip_idx)}
            className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/40 transition-colors"
          >
            <Play className="h-10 w-10 text-white/0 group-hover:text-white/90 transition-colors drop-shadow-lg" />
          </button>
        )}
      </div>

      {/* Card body */}
      <div className="flex flex-1 flex-col gap-2 p-3">
        {/* Header row */}
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-gray-200">
            片段 {task.clip_idx + 1}
          </span>
          <StatusBadge status={task.status} />
        </div>

        {/* Prompt text */}
        {task.prompt && (
          <p className="text-xs leading-relaxed text-gray-500 line-clamp-2">
            {task.prompt}
          </p>
        )}

        {/* Error message */}
        {task.error && (
          <p className="text-xs text-red-400/80 line-clamp-2">
            {task.error}
          </p>
        )}

        {/* Action buttons */}
        <div className="mt-auto flex items-center gap-2 pt-1">
          <button
            onClick={() => onRegenerate(task.clip_idx)}
            disabled={isProcessing}
            className="inline-flex items-center gap-1 rounded-lg bg-white/[0.06] px-2.5 py-1.5 text-xs font-medium text-gray-300 hover:bg-white/[0.1] hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <RefreshCw className={`h-3 w-3 ${isProcessing ? "animate-spin" : ""}`} />
            重新生成
          </button>
          {task.video_url && (
            <button
              onClick={() => onPreview(task.clip_idx)}
              className="inline-flex items-center gap-1 rounded-lg bg-white/[0.06] px-2.5 py-1.5 text-xs font-medium text-gray-300 hover:bg-white/[0.1] hover:text-white transition-colors"
            >
              <Play className="h-3 w-3" />
              预览
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main component ──

export default function ClipManager() {
  const { tasks, taskSummary, phase, regenerateVideo, renderFinal, finalVideoUrl } =
    useProject();

  const [previewClip, setPreviewClip] = useState<{ idx: number; url: string } | null>(null);

  const progressPercent =
    taskSummary.total > 0
      ? Math.round((taskSummary.succeeded / taskSummary.total) * 100)
      : 0;

  const isRendering = phase === "rendering";
  const isStitching = phase === "stitching";
  const allClipsDone = taskSummary.allDone && taskSummary.total > 0;

  const handleRegenerate = useCallback(
    (clipIdx: number) => {
      regenerateVideo(clipIdx);
    },
    [regenerateVideo],
  );

  const handlePreview = useCallback(
    (clipIdx: number) => {
      const task = tasks.find((t) => t.clip_idx === clipIdx);
      if (task?.video_url) {
        setPreviewClip({ idx: clipIdx, url: task.video_url });
      }
    },
    [tasks],
  );

  const handleRender = useCallback(() => {
    renderFinal();
  }, [renderFinal]);

  if (tasks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-20 text-gray-500">
        <Film className="h-12 w-12 text-gray-700" />
        <p className="text-sm">暂无视频片段</p>
      </div>
    );
  }

  const sortedTasks = [...tasks].sort((a, b) => a.clip_idx - b.clip_idx);

  return (
    <div className="flex flex-col gap-6">
      {/* ── Top summary area ── */}
      <div className="rounded-xl bg-gray-900/60 ring-1 ring-white/[0.06] p-4 space-y-3">
        {/* Status text */}
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-200 flex items-center gap-2">
            <Film className="h-4 w-4 text-[#E11D48]" />
            视频片段
          </h3>
          <span className="text-xs text-gray-400">
            {isStitching ? (
              <span className="flex items-center gap-1 text-amber-400">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                正在合成完整视频...
              </span>
            ) : allClipsDone ? (
              <span className="flex items-center gap-1 text-green-400">
                <CheckCircle className="h-3.5 w-3.5" />
                全部完成
              </span>
            ) : (
              `分段生成中 ${taskSummary.succeeded}/${taskSummary.total}`
            )}
          </span>
        </div>

        {/* Progress bar */}
        <div className="h-2 w-full rounded-full bg-gray-800 overflow-hidden">
          <div
            className="h-full rounded-full bg-[#E11D48] transition-all duration-500 ease-out"
            style={{ width: `${progressPercent}%` }}
          />
        </div>

        {/* Task breakdown */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
          <span>总计 {taskSummary.total}</span>
          <span className="text-green-400/80">成功 {taskSummary.succeeded}</span>
          <span className="text-yellow-400/80">
            处理中 {taskSummary.total - taskSummary.succeeded - taskSummary.failed - taskSummary.pending > 0
              ? taskSummary.total - taskSummary.succeeded - taskSummary.failed - taskSummary.pending
              : 0}
          </span>
          <span className="text-gray-500">等待 {taskSummary.pending}</span>
          {taskSummary.failed > 0 && (
            <span className="text-red-400/80">失败 {taskSummary.failed}</span>
          )}
        </div>
      </div>

      {/* ── Clip grid ── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {sortedTasks.map((task) => (
          <ClipCard
            key={task.id ?? `clip-${task.clip_idx}`}
            task={task}
            onRegenerate={handleRegenerate}
            onPreview={handlePreview}
          />
        ))}
      </div>

      {/* ── Bottom action bar ── */}
      <div className="flex flex-wrap items-center justify-end gap-3 rounded-xl bg-gray-900/60 ring-1 ring-white/[0.06] px-4 py-3">
        {/* Stitching progress indicator (digital human multi-segment auto-stitch) */}
        {isStitching && (
          <span className="text-xs text-amber-400 flex items-center gap-1.5">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            所有分段已完成，正在自动合成完整视频…
          </span>
        )}

        {/* Render button — only show when not auto-stitching */}
        {allClipsDone && !finalVideoUrl && !isStitching && (
          <button
            onClick={handleRender}
            disabled={isRendering}
            className="inline-flex items-center gap-2 rounded-lg bg-[#E11D48] px-4 py-2 text-sm font-medium text-white hover:bg-[#BE123C] disabled:opacity-60 disabled:cursor-not-allowed transition-all duration-200 shadow-[0_0_20px_rgba(225,29,72,0.2)]"
          >
            {isRendering ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                合成中…
              </>
            ) : (
              <>
                <Film className="h-4 w-4" />
                合成视频
              </>
            )}
          </button>
        )}

        {/* Rendering progress indicator */}
        {isRendering && (
          <span className="text-xs text-yellow-400 flex items-center gap-1.5">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            正在合成最终视频，请稍候…
          </span>
        )}

        {/* Download button */}
        {finalVideoUrl && (
          <a
            href={finalVideoUrl}
            target="_blank"
            rel="noopener noreferrer"
            download
            className="inline-flex items-center gap-2 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-500 transition-colors"
          >
            <Download className="h-4 w-4" />
            下载
          </a>
        )}
      </div>

      {/* ── Preview modal ── */}
      {previewClip && (
        <PreviewModal
          url={previewClip.url}
          clipIdx={previewClip.idx}
          onClose={() => setPreviewClip(null)}
        />
      )}
    </div>
  );
}
