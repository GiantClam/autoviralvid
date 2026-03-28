"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  Loader2,
  CheckCircle2,
  XCircle,
  Download,
  RefreshCw,
  Video,
} from "lucide-react";

interface RenderProgressProps {
  jobId: string;
  pollInterval?: number;
  onComplete?: (outputUrl: string) => void;
  onError?: (error: string) => void;
}

type StatusData = {
  job_id: string;
  status: string;
  progress?: number;
  lambda_job_id?: string;
  output_url?: string;
  error?: string;
};

export default function RenderProgress({
  jobId,
  pollInterval = 3000,
  onComplete,
  onError,
}: RenderProgressProps) {
  const [status, setStatus] = useState<StatusData | null>(null);
  const [isPolling, setIsPolling] = useState(true);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`/api/ppt/render/${jobId}`);
      const json = await res.json();

      if (json.success && json.data) {
        const data = json.data as StatusData;
        setStatus(data);

        if (data.status === "done" || data.status === "completed") {
          setIsPolling(false);
          if (data.output_url) onComplete?.(data.output_url);
        }

        if (data.status === "failed") {
          setIsPolling(false);
          onError?.(data.error || "Render failed");
        }
      }
    } catch {
      // ignore temporary polling errors
    }
  }, [jobId, onComplete, onError]);

  useEffect(() => {
    const bootstrapTimer = setTimeout(() => {
      void fetchStatus();
    }, 0);

    if (!isPolling) {
      return () => clearTimeout(bootstrapTimer);
    }

    const timer = setInterval(() => {
      void fetchStatus();
    }, pollInterval);

    return () => {
      clearTimeout(bootstrapTimer);
      clearInterval(timer);
    };
  }, [fetchStatus, isPolling, pollInterval]);

  const progress = status?.progress ?? 0;
  const statusLabel = getStatusLabel(status?.status);
  const isRunning =
    status?.status === "pending" ||
    status?.status === "rendering" ||
    status?.status === "queued";
  const isDone = status?.status === "done" || status?.status === "completed";
  const isFailed = status?.status === "failed";

  return (
    <div className="mx-auto flex max-w-xl flex-col gap-4 p-4 text-gray-200">
      <div className="flex items-center gap-3">
        <Video className="h-5 w-5 text-[#E11D48]" />
        <h3 className="text-lg font-semibold text-gray-100">Video Render Progress</h3>
      </div>

      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-5">
        <div className="mb-4 flex items-center gap-3">
          {isRunning && <Loader2 className="h-5 w-5 animate-spin text-[#E11D48]" />}
          {isDone && <CheckCircle2 className="h-5 w-5 text-emerald-400" />}
          {isFailed && <XCircle className="h-5 w-5 text-red-400" />}
          <span
            className={`text-sm font-medium ${
              isFailed
                ? "text-red-300"
                : isDone
                  ? "text-emerald-300"
                  : "text-[#E11D48]"
            }`}
          >
            {statusLabel}
          </span>
        </div>

        {isRunning && (
          <div className="mb-3">
            <div className="mb-1 flex justify-between text-xs text-gray-500">
              <span>Rendering...</span>
              <span>{Math.round(progress * 100)}%</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-white/[0.08]">
              <div
                className="h-full rounded-full bg-gradient-to-r from-[#E11D48] to-[#9333EA] transition-all duration-500"
                style={{ width: `${Math.max(progress * 100, 2)}%` }}
              />
            </div>
          </div>
        )}

        <div className="space-y-1 text-xs text-gray-500">
          <p>Job ID: {status?.job_id || jobId}</p>
          {status?.lambda_job_id && <p>Lambda ID: {status.lambda_job_id}</p>}
        </div>

        {isFailed && status?.error && (
          <div className="mt-3 rounded-lg border border-red-500/20 bg-red-500/[0.08] p-3 text-sm text-red-300">
            {status.error}
          </div>
        )}

        {isDone && status?.output_url && (
          <div className="mt-4">
            <a
              href={status.output_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-[#E11D48] to-[#9333EA] px-4 py-2 text-sm font-medium text-white transition hover:from-[#F43F5E] hover:to-[#A855F7]"
            >
              <Download className="h-4 w-4" />
              Download Video
            </a>
          </div>
        )}

        {isFailed && (
          <div className="mt-4">
            <button
              onClick={() => void fetchStatus()}
              className="inline-flex items-center gap-2 rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-gray-200 transition hover:bg-white/[0.08]"
            >
              <RefreshCw className="h-4 w-4" />
              Retry Poll
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function getStatusLabel(status?: string): string {
  switch (status) {
    case "pending":
      return "Pending";
    case "queued":
      return "Queued";
    case "rendering":
      return "Rendering";
    case "done":
    case "completed":
      return "Completed";
    case "failed":
      return "Failed";
    default:
      return "Unknown";
  }
}
