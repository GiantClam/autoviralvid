"use client";

import React, { useCallback, useState } from "react";
import {
  X,
  Play,
  Loader2,
  CheckCircle,
  AlertCircle,
  Layers,
  Image as ImageIcon,
} from "lucide-react";
import { projectApi } from "@/lib/project-client";

interface BatchProject {
  run_id: string;
  status: "pending" | "generating" | "completed" | "failed";
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
  const [newUrl, setNewUrl] = useState("");
  const [projects, setProjects] = useState<BatchProject[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const addImage = useCallback(() => {
    const url = newUrl.trim();
    if (!url || imageUrls.includes(url)) {
      return;
    }
    setImageUrls((prev) => [...prev, url]);
    setNewUrl("");
  }, [imageUrls, newUrl]);

  const removeImage = useCallback((url: string) => {
    setImageUrls((prev) => prev.filter((item) => item !== url));
  }, []);

  const pollBatchStatus = useCallback((runIds: string[]) => {
    const interval = setInterval(async () => {
      let allDone = true;

      for (const runId of runIds) {
        try {
          const status = await projectApi.getStatus(runId);
          const project = await projectApi.get(runId);
          const isDone = status.summary.all_done || project.status === "completed";
          const isFailed = project.status?.includes("failed");

          setProjects((prev) =>
            prev.map((item) => {
              if (item.run_id !== runId) {
                return item;
              }
              return {
                ...item,
                status: isDone ? "completed" : isFailed ? "failed" : "generating",
                progress:
                  status.summary.total > 0
                    ? Math.round((status.summary.succeeded / status.summary.total) * 100)
                    : 0,
              };
            }),
          );

          if (!isDone && !isFailed) {
            allDone = false;
          }
        } catch {
          allDone = false;
        }
      }

      if (allDone) {
        clearInterval(interval);
      }
    }, 8000);

    setTimeout(() => clearInterval(interval), 30 * 60 * 1000);
  }, []);

  const startBatch = useCallback(async () => {
    if (imageUrls.length === 0) {
      return;
    }

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
        runIds.map((runId: string, index: number) => ({
          run_id: runId,
          status: "pending",
          image_url: imageUrls[index] || "",
        })),
      );

      for (const runId of runIds) {
        try {
          await projectApi.generateStoryboard(runId);
          setProjects((prev) =>
            prev.map((item) =>
              item.run_id === runId ? { ...item, status: "generating" } : item,
            ),
          );
        } catch {
          setProjects((prev) =>
            prev.map((item) =>
              item.run_id === runId ? { ...item, status: "failed" } : item,
            ),
          );
        }
      }

      pollBatchStatus(runIds);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Batch creation failed");
    } finally {
      setIsSubmitting(false);
    }
  }, [aspectRatio, duration, imageUrls, orientation, pollBatchStatus, style, templateId, theme]);

  const completedCount = projects.filter((project) => project.status === "completed").length;
  const totalCount = projects.length;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm">
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-gray-800 bg-[#0a0a0b]">
        <div className="flex items-center justify-between border-b border-gray-800 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="rounded-xl border border-purple-500/20 bg-purple-500/10 p-2">
              <Layers className="h-5 w-5 text-purple-400" />
            </div>
            <div>
              <h2 className="font-semibold text-white">Batch Generate</h2>
              <p className="text-xs text-gray-500">Create multiple projects from product image URLs.</p>
            </div>
          </div>
          <button onClick={onClose} className="rounded-lg p-2 text-gray-500 transition hover:bg-gray-800">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto p-6">
          {projects.length === 0 && (
            <div className="space-y-4">
              <label className="text-sm font-medium text-gray-400">Product image URLs</label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newUrl}
                  onChange={(event) => setNewUrl(event.target.value)}
                  onKeyDown={(event) => event.key === "Enter" && addImage()}
                  placeholder="Paste an image URL..."
                  className="flex-1 rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-purple-500 focus:outline-none"
                />
                <button
                  onClick={addImage}
                  disabled={!newUrl.trim()}
                  className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium transition hover:bg-purple-500 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Add
                </button>
              </div>

              {imageUrls.length > 0 && (
                <div className="space-y-2">
                  {imageUrls.map((url) => (
                    <div
                      key={url}
                      className="flex items-center gap-3 rounded-lg border border-gray-800 bg-gray-900/50 px-3 py-2"
                    >
                      <ImageIcon className="h-4 w-4 shrink-0 text-gray-500" />
                      <span className="flex-1 truncate text-sm text-gray-300">{url}</span>
                      <button
                        onClick={() => removeImage(url)}
                        className="rounded p-1 text-gray-500 transition hover:bg-gray-700"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <div className="text-xs text-gray-600">
                Shared settings: template {templateId} / style {style} / duration {duration}s / {orientation}
              </div>
            </div>
          )}

          {projects.length > 0 && (
            <div className="space-y-4">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400">Progress: {completedCount}/{totalCount}</span>
                {completedCount === totalCount && totalCount > 0 && (
                  <span className="flex items-center gap-1 text-green-400">
                    <CheckCircle className="h-4 w-4" />
                    Complete
                  </span>
                )}
              </div>

              <div className="h-2 overflow-hidden rounded-full bg-gray-800">
                <div
                  className="h-full rounded-full bg-purple-500 transition-all duration-500"
                  style={{ width: `${totalCount > 0 ? (completedCount / totalCount) * 100 : 0}%` }}
                />
              </div>

              <div className="space-y-3">
                {projects.map((project, index) => (
                  <div
                    key={project.run_id}
                    className="flex items-center gap-4 rounded-xl border border-gray-800 bg-gray-900/50 px-4 py-3"
                  >
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-800 text-sm font-mono text-gray-400">
                      {index + 1}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-gray-300">{project.image_url}</p>
                      <p className="mt-0.5 text-xs text-gray-600">
                        {project.run_id.slice(0, 8)}...
                        {project.progress !== undefined && project.status === "generating" && (
                          <span className="ml-2 text-yellow-400">{project.progress}%</span>
                        )}
                      </p>
                    </div>
                    <div>
                      {project.status === "pending" && (
                        <span className="rounded-full bg-gray-700 px-2 py-0.5 text-xs text-gray-400">Queued</span>
                      )}
                      {project.status === "generating" && (
                        <span className="flex items-center gap-1 rounded-full bg-yellow-500/20 px-2 py-0.5 text-xs text-yellow-400">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          Generating
                        </span>
                      )}
                      {project.status === "completed" && (
                        <span className="flex items-center gap-1 rounded-full bg-green-500/20 px-2 py-0.5 text-xs text-green-400">
                          <CheckCircle className="h-3 w-3" />
                          Done
                        </span>
                      )}
                      {project.status === "failed" && (
                        <span className="flex items-center gap-1 rounded-full bg-red-500/20 px-2 py-0.5 text-xs text-red-400">
                          <AlertCircle className="h-3 w-3" />
                          Failed
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {error && (
            <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-gray-800 px-6 py-4">
          <button
            onClick={onClose}
            className="rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-400 transition hover:bg-gray-800"
          >
            Close
          </button>
          {projects.length === 0 && (
            <button
              onClick={startBatch}
              disabled={imageUrls.length === 0 || isSubmitting}
              className="flex items-center gap-2 rounded-lg bg-purple-600 px-6 py-2 text-sm font-medium transition hover:bg-purple-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" />
                  Start batch ({imageUrls.length})
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
