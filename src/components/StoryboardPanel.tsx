"use client";

import React, { useState, useCallback } from "react";
import {
  Image,
  RefreshCw,
  Edit3,
  Sparkles,
  Play,
  Loader2,
  Trash2,
  Check,
  X,
} from "lucide-react";
import { useProject } from "@/contexts/ProjectContext";

// ── Scene Card ──

interface SceneCardProps {
  scene: {
    idx: number;
    desc: string;
    narration?: string;
    prompt?: string;
    image_url?: string;
  };
  index: number;
  isGeneratingImages: boolean;
  onUpdate: (idx: number, data: { description?: string; narration?: string }) => Promise<void>;
  onRegenerateImage: (idx: number) => Promise<void>;
}

function SceneCard({
  scene,
  index,
  isGeneratingImages,
  onUpdate,
  onRegenerateImage,
}: SceneCardProps) {
  const [editing, setEditing] = useState(false);
  const [desc, setDesc] = useState(scene.desc);
  const [narration, setNarration] = useState(scene.narration || "");
  const [saving, setSaving] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      await onUpdate(scene.idx, {
        description: desc,
        narration: narration || undefined,
      });
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }, [desc, narration, onUpdate, scene.idx]);

  const handleCancel = useCallback(() => {
    setDesc(scene.desc);
    setNarration(scene.narration || "");
    setEditing(false);
  }, [scene.desc, scene.narration]);

  const handleRegenerate = useCallback(async () => {
    setRegenerating(true);
    try {
      await onRegenerateImage(scene.idx);
    } finally {
      setRegenerating(false);
    }
  }, [onRegenerateImage, scene.idx]);

  const imageLoading = isGeneratingImages && !scene.image_url;

  return (
    <div className="group relative flex flex-col rounded-2xl border border-white/[0.06] bg-gradient-to-br from-white/[0.02] to-transparent backdrop-blur-sm overflow-hidden transition-all duration-300 hover:border-white/[0.12] hover:shadow-xl hover:shadow-black/20 card-hover-lift">
      <div className="absolute top-3 left-3 z-10 flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-[#E11D48] to-[#9333EA] text-xs font-bold text-white shadow-lg shadow-[#E11D48]/30">
        {index + 1}
      </div>

      <div className="relative aspect-video w-full bg-[#0a0a12] overflow-hidden">
        {scene.image_url ? (
          <img
            src={scene.image_url}
            alt={`Scene ${index + 1}`}
            className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-3 text-gray-600">
            {imageLoading ? (
              <>
                <div className="relative">
                  <div className="absolute inset-0 rounded-full bg-[#E11D48]/20 blur-xl animate-pulse" />
                  <Loader2 className="relative h-10 w-10 animate-spin text-[#E11D48]" />
                </div>
                <span className="text-xs text-gray-500">生成图片中...</span>
              </>
            ) : (
              <>
                <div className="w-16 h-16 rounded-2xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center">
                  <Image className="h-8 w-8 text-gray-600" />
                </div>
                <span className="text-xs text-gray-500">暂无图片</span>
              </>
            )}
          </div>
        )}

        {scene.image_url && (
          <div className="absolute inset-0 flex items-center justify-center gap-3 bg-black/60 opacity-0 transition-opacity duration-300 group-hover:opacity-100 backdrop-blur-sm">
            <button
              onClick={handleRegenerate}
              disabled={regenerating}
              className="flex items-center gap-2 rounded-xl bg-white/10 px-4 py-2 text-xs font-semibold text-white backdrop-blur-md border border-white/10 transition-all hover:bg-white/20 hover:border-white/20 disabled:opacity-50"
            >
              {regenerating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              重新生成
            </button>
          </div>
        )}

        {imageLoading && scene.image_url && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/70 backdrop-blur-sm">
            <div className="relative">
              <div className="absolute inset-0 rounded-full bg-[#E11D48]/30 blur-xl animate-pulse" />
              <Loader2 className="relative h-10 w-10 animate-spin text-[#E11D48]" />
            </div>
          </div>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-4 p-5">
        <div className="space-y-2">
          <label className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
            场景描述
          </label>
          {editing ? (
            <textarea
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              rows={3}
              className="w-full resize-none rounded-xl border border-white/[0.06] bg-white/[0.03] px-4 py-3 text-sm text-gray-200 outline-none transition-all focus:border-[#E11D48]/50 focus:ring-2 focus:ring-[#E11D48]/10"
            />
          ) : (
            <p
              className="cursor-pointer rounded-xl border border-transparent px-4 py-3 text-sm leading-relaxed text-gray-300 transition-all hover:border-white/[0.06] hover:bg-white/[0.02]"
              onClick={() => setEditing(true)}
              title="点击编辑"
            >
              {scene.desc || "—"}
            </p>
          )}
        </div>

        <div className="space-y-2">
          <label className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
            旁白文案
          </label>
          {editing ? (
            <textarea
              value={narration}
              onChange={(e) => setNarration(e.target.value)}
              rows={2}
              className="w-full resize-none rounded-xl border border-white/[0.06] bg-white/[0.03] px-4 py-3 text-sm text-gray-200 outline-none transition-all focus:border-[#E11D48]/50 focus:ring-2 focus:ring-[#E11D48]/10"
            />
          ) : (
            <p
              className="cursor-pointer rounded-xl border border-transparent px-4 py-3 text-sm leading-relaxed text-gray-400 italic transition-all hover:border-white/[0.06] hover:bg-white/[0.02]"
              onClick={() => setEditing(true)}
              title="点击编辑"
            >
              {scene.narration || "暂无旁白"}
            </p>
          )}
        </div>

        <div className="mt-auto flex items-center gap-3 pt-3">
          {editing ? (
            <>
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-[#E11D48] to-[#BE123C] px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-[#E11D48]/20 transition-all hover:shadow-[#E11D48]/40 disabled:opacity-50"
              >
                {saving ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Check className="h-4 w-4" />
                )}
                保存
              </button>
              <button
                onClick={handleCancel}
                disabled={saving}
                className="flex items-center gap-2 rounded-xl bg-white/[0.03] border border-white/[0.06] px-4 py-2 text-xs font-semibold text-gray-400 transition-all hover:bg-white/[0.06] hover:text-white disabled:opacity-50"
              >
                <X className="h-4 w-4" />
                取消
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setEditing(true)}
                className="flex items-center gap-2 rounded-xl bg-white/[0.03] border border-white/[0.06] px-4 py-2 text-xs font-semibold text-gray-400 transition-all hover:bg-white/[0.06] hover:text-white hover:border-white/[0.12]"
              >
                <Edit3 className="h-4 w-4" />
                编辑
              </button>
              {!scene.image_url && !isGeneratingImages && (
                <button
                  onClick={handleRegenerate}
                  disabled={regenerating}
                  className="flex items-center gap-2 rounded-xl bg-white/[0.03] border border-white/[0.06] px-4 py-2 text-xs font-semibold text-gray-400 transition-all hover:bg-white/[0.06] hover:text-white hover:border-white/[0.12] disabled:opacity-50"
                >
                  {regenerating ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className="h-4 w-4" />
                  )}
                  生成图片
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Loading Skeleton ──

function SceneSkeleton() {
  return (
    <div className="flex flex-col rounded-2xl border border-white/[0.06] bg-gradient-to-br from-white/[0.02] to-transparent overflow-hidden">
      <div className="aspect-video w-full bg-white/[0.03] skeleton" />
      <div className="flex flex-col gap-4 p-5">
        <div className="space-y-2">
          <div className="h-2 w-16 rounded bg-white/[0.05] skeleton" />
          <div className="h-4 w-full rounded bg-white/[0.05] skeleton" />
          <div className="h-4 w-3/4 rounded bg-white/[0.05] skeleton" />
        </div>
        <div className="space-y-2">
          <div className="h-2 w-12 rounded bg-white/[0.05] skeleton" />
          <div className="h-4 w-full rounded bg-white/[0.05] skeleton" />
        </div>
        <div className="flex gap-3 pt-2">
          <div className="h-8 w-20 rounded-xl bg-white/[0.05] skeleton" />
          <div className="h-8 w-28 rounded-xl bg-white/[0.05] skeleton" />
        </div>
      </div>
    </div>
  );
}

// ── Main Panel ──

export default function StoryboardPanel() {
  const {
    scenes,
    phase,
    generateImages,
    updateScene,
    regenerateImage,
    submitVideos,
    isLoading,
    taskSummary,
  } = useProject();

  const isGeneratingStoryboard = phase === "generating_storyboard";
  const isGeneratingImages = phase === "generating_images";
  const isStoryboardReady = phase === "storyboard_ready";
  const isImagesReady = phase === "images_ready";
  const isGeneratingVideos = phase === "generating_videos";

  // Count scenes with images for progress
  const imagesReady = scenes.filter((s) => s.image_url).length;
  const totalScenes = scenes.length;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-white/[0.06] px-6 py-4 bg-gradient-to-r from-[#E11D48]/5 to-transparent">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#E11D48] to-[#9333EA] flex items-center justify-center shadow-lg shadow-[#E11D48]/20">
            <Sparkles className="h-4 w-4 text-white" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-white">分镜脚本</h2>
            {totalScenes > 0 && (
              <span className="text-xs text-gray-500">{totalScenes} 场景</span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs text-gray-400">
          {isGeneratingStoryboard && (
            <span className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#E11D48]/10 border border-[#E11D48]/20">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-[#E11D48]" />
              生成分镜中...
            </span>
          )}
          {isGeneratingImages && (
            <span className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#E11D48]/10 border border-[#E11D48]/20">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-[#E11D48]" />
              生成图片 {imagesReady}/{totalScenes}
            </span>
          )}
          {isGeneratingVideos && (
            <span className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-purple-500/10 border border-purple-500/20">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-purple-400" />
              生成视频 {taskSummary.succeeded}/{taskSummary.total}
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {isGeneratingStoryboard && totalScenes === 0 ? (
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <SceneSkeleton key={i} />
            ))}
          </div>
        ) : totalScenes === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-gray-600">
            <div className="w-20 h-20 rounded-2xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center">
              <Sparkles className="h-10 w-10 text-gray-600" />
            </div>
            <div className="text-center">
              <p className="text-sm font-medium text-gray-400">尚未生成分镜脚本</p>
              <p className="text-xs text-gray-600 mt-1">请先配置项目并生成分镜</p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            {scenes.map((scene, idx) => (
              <SceneCard
                key={scene.idx ?? idx}
                scene={scene}
                index={idx}
                isGeneratingImages={isGeneratingImages}
                onUpdate={updateScene}
                onRegenerateImage={regenerateImage}
              />
            ))}
          </div>
        )}
      </div>

      {isGeneratingImages && totalScenes > 0 && (
        <div className="px-6 pb-2">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.04]">
            <div
              className="h-full rounded-full bg-gradient-to-r from-[#E11D48] to-[#9333EA] transition-all duration-700"
              style={{
                width: `${totalScenes > 0 ? (imagesReady / totalScenes) * 100 : 0}%`,
              }}
            />
          </div>
        </div>
      )}

      {totalScenes > 0 && (
        <div className="flex items-center justify-between border-t border-white/[0.06] px-6 py-4 bg-[#0a0a12]/50 backdrop-blur-sm">
          <div className="text-xs text-gray-500">
            {isStoryboardReady && "分镜就绪，可以生成图片"}
            {isImagesReady && `${imagesReady} 张图片就绪，可以生成视频`}
            {isGeneratingImages && `正在生成图片 (${imagesReady}/${totalScenes})`}
            {isGeneratingVideos &&
              `正在生成视频 (${taskSummary.succeeded}/${taskSummary.total})`}
          </div>

          <div className="flex items-center gap-3">
            {isStoryboardReady && (
              <button
                onClick={generateImages}
                disabled={isLoading}
                className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-[#E11D48] to-[#BE123C] px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-[#E11D48]/25 transition-all hover:shadow-[#E11D48]/40 hover:scale-[1.02] disabled:opacity-50 disabled:hover:scale-100"
              >
                {isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Image className="h-4 w-4" />
                )}
                生成图片
              </button>
            )}

            {isImagesReady && (
              <button
                onClick={submitVideos}
                disabled={isLoading}
                className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-[#E11D48] to-[#9333EA] px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-[#E11D48]/25 transition-all hover:shadow-[#E11D48]/40 hover:scale-[1.02] disabled:opacity-50 disabled:hover:scale-100"
              >
                {isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Play className="h-4 w-4" />
                )}
                生成视频
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
