"use client";

import React, { useState, useCallback } from 'react';
import {
  Upload,
  X,
  Play,
  Loader2,
  CheckCircle,
  AlertCircle,
  Download,
  Layers,
  Image as ImageIcon,
} from 'lucide-react';
import { projectApi } from '@/lib/project-client';

interface BatchProject {
  run_id: string;
  status: 'pending' | 'generating' | 'completed' | 'failed';
  image_url: string;
  progress?: number;
}

interface BatchPanelProps {
  templateId: string;
  theme: string;
  style: string;
  duration: number;
  orientation: string;
  aspectRatio: string;
  onClose: () => void;
}

export default function BatchPanel({
  templateId,
  theme,
  style,
  duration,
  orientation,
  aspectRatio,
  onClose,
}: BatchPanelProps) {
  const [imageUrls, setImageUrls] = useState<string[]>([]);
  const [newUrl, setNewUrl] = useState('');
  const [projects, setProjects] = useState<BatchProject[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const addImage = useCallback(() => {
    const url = newUrl.trim();
    if (url && !imageUrls.includes(url)) {
      setImageUrls(prev => [...prev, url]);
      setNewUrl('');
    }
  }, [newUrl, imageUrls]);

  const removeImage = useCallback((url: string) => {
    setImageUrls(prev => prev.filter(u => u !== url));
  }, []);

  const startBatch = useCallback(async () => {
    if (imageUrls.length === 0) return;
    setIsSubmitting(true);
    setError(null);

    try {
      const result = await projectApi.createBatch({
        template_id: templateId,
        product_images: imageUrls,
        theme,
        style,
        duration,
        orientation,
        aspect_ratio: aspectRatio,
      });

      const runIds = result.run_ids || [];
      setProjects(
        runIds.map((run_id: string, idx: number) => ({
          run_id,
          status: 'pending' as const,
          image_url: imageUrls[idx] || '',
        }))
      );

      // Start generation for each project
      for (const run_id of runIds) {
        try {
          await projectApi.generateStoryboard(run_id);
          setProjects(prev =>
            prev.map(p =>
              p.run_id === run_id ? { ...p, status: 'generating' } : p
            )
          );
        } catch {
          setProjects(prev =>
            prev.map(p =>
              p.run_id === run_id ? { ...p, status: 'failed' } : p
            )
          );
        }
      }

      // Start polling for all projects
      pollBatchStatus(runIds);
    } catch (e) {
      setError(e instanceof Error ? e.message : '批量创建失败');
    } finally {
      setIsSubmitting(false);
    }
  }, [imageUrls, templateId, theme, style, duration, orientation, aspectRatio]);

  const pollBatchStatus = useCallback((runIds: string[]) => {
    const interval = setInterval(async () => {
      let allDone = true;
      for (const run_id of runIds) {
        try {
          const status = await projectApi.getStatus(run_id);
          const proj = await projectApi.get(run_id);
          const isDone = status.summary.all_done || proj.status === 'completed';
          const isFailed = proj.status?.includes('failed');

          setProjects(prev =>
            prev.map(p => {
              if (p.run_id !== run_id) return p;
              return {
                ...p,
                status: isDone ? 'completed' : isFailed ? 'failed' : 'generating',
                progress: status.summary.total > 0
                  ? Math.round((status.summary.succeeded / status.summary.total) * 100)
                  : 0,
              };
            })
          );

          if (!isDone && !isFailed) allDone = false;
        } catch {
          allDone = false;
        }
      }

      if (allDone) clearInterval(interval);
    }, 8000);

    // Cleanup after 30 minutes
    setTimeout(() => clearInterval(interval), 30 * 60 * 1000);
  }, []);

  const completedCount = projects.filter(p => p.status === 'completed').length;
  const totalCount = projects.length;

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-[#0a0a0b] border border-gray-800 rounded-2xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-purple-500/10 border border-purple-500/20">
              <Layers className="w-5 h-5 text-purple-400" />
            </div>
            <div>
              <h2 className="font-semibold text-white">批量生成</h2>
              <p className="text-xs text-gray-500">上传多张产品图，一键批量生成视频</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-gray-800 text-gray-500 transition">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Image upload area */}
          {projects.length === 0 && (
            <div className="space-y-4">
              <label className="text-sm font-medium text-gray-400">产品图片 URL</label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newUrl}
                  onChange={e => setNewUrl(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addImage()}
                  placeholder="粘贴图片 URL..."
                  className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-purple-500 focus:outline-none"
                />
                <button
                  onClick={addImage}
                  disabled={!newUrl.trim()}
                  className="px-4 py-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-sm font-medium transition"
                >
                  添加
                </button>
              </div>

              {/* Image list */}
              {imageUrls.length > 0 && (
                <div className="space-y-2">
                  {imageUrls.map((url, idx) => (
                    <div key={idx} className="flex items-center gap-3 bg-gray-900/50 border border-gray-800 rounded-lg px-3 py-2">
                      <ImageIcon className="w-4 h-4 text-gray-500 shrink-0" />
                      <span className="flex-1 text-sm text-gray-300 truncate">{url}</span>
                      <button
                        onClick={() => removeImage(url)}
                        className="p-1 rounded hover:bg-gray-700 text-gray-500 transition"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <div className="text-xs text-gray-600">
                共享参数：模板 {templateId} · 风格 {style} · 时长 {duration}s · {orientation}
              </div>
            </div>
          )}

          {/* Batch projects list */}
          {projects.length > 0 && (
            <div className="space-y-4">
              {/* Progress summary */}
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400">
                  批量进度：{completedCount}/{totalCount}
                </span>
                {completedCount === totalCount && totalCount > 0 && (
                  <span className="text-green-400 flex items-center gap-1">
                    <CheckCircle className="w-4 h-4" />
                    全部完成
                  </span>
                )}
              </div>

              {/* Progress bar */}
              <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-purple-500 rounded-full transition-all duration-500"
                  style={{ width: `${totalCount > 0 ? (completedCount / totalCount) * 100 : 0}%` }}
                />
              </div>

              {/* Individual project cards */}
              <div className="space-y-3">
                {projects.map((proj, idx) => (
                  <div
                    key={proj.run_id}
                    className="flex items-center gap-4 bg-gray-900/50 border border-gray-800 rounded-xl px-4 py-3"
                  >
                    <div className="w-10 h-10 rounded-lg bg-gray-800 flex items-center justify-center text-sm font-mono text-gray-400">
                      {idx + 1}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-300 truncate">{proj.image_url}</p>
                      <p className="text-xs text-gray-600 mt-0.5">
                        {proj.run_id.slice(0, 8)}...
                        {proj.progress !== undefined && proj.status === 'generating' && (
                          <span className="ml-2 text-yellow-400">{proj.progress}%</span>
                        )}
                      </p>
                    </div>
                    <div>
                      {proj.status === 'pending' && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-gray-700 text-gray-400">等待中</span>
                      )}
                      {proj.status === 'generating' && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-yellow-500/20 text-yellow-400 flex items-center gap-1">
                          <Loader2 className="w-3 h-3 animate-spin" />
                          生成中
                        </span>
                      )}
                      {proj.status === 'completed' && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-green-500/20 text-green-400 flex items-center gap-1">
                          <CheckCircle className="w-3 h-3" />
                          完成
                        </span>
                      )}
                      {proj.status === 'failed' && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/20 text-red-400 flex items-center gap-1">
                          <AlertCircle className="w-3 h-3" />
                          失败
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-800 flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg border border-gray-700 text-gray-400 hover:bg-gray-800 text-sm transition"
          >
            关闭
          </button>
          {projects.length === 0 && (
            <button
              onClick={startBatch}
              disabled={imageUrls.length === 0 || isSubmitting}
              className="px-6 py-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-sm font-medium flex items-center gap-2 transition"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  创建中...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  开始批量生成 ({imageUrls.length} 个)
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
