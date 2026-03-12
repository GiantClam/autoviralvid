"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { SessionProvider, useSession } from "next-auth/react";
import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle2,
  ChevronRight,
  Clock3,
  ExternalLink,
  Film,
  Loader2,
  PlayCircle,
  RefreshCw,
  AlertCircle,
} from "lucide-react";
import { useT } from "@/lib/i18n";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import {
  projectApi,
  type Project,
  type ProjectStatus,
  type VideoTask,
} from "@/lib/project-client";

function parseProjectTheme(project: Project) {
  if (typeof project.theme === "string" && project.theme.trim()) {
    return project.theme;
  }
  if (typeof project.slogan === "string" && project.slogan.trim()) {
    return project.slogan;
  }
  const rawStoryboards = project.storyboards as unknown;
  if (typeof rawStoryboards === "string" && rawStoryboards.trim()) {
    try {
      const parsed = JSON.parse(rawStoryboards);
      const metaTheme = parsed?._meta?.theme;
      if (typeof metaTheme === "string" && metaTheme.trim()) {
        return metaTheme;
      }
    } catch {
      // ignore invalid historical payloads
    }
  }
  return project.run_id;
}

function formatDate(value?: string) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function statusTone(project: Project, status?: ProjectStatus | null) {
  const summary = status?.summary || project.task_summary;
  const videoUrl = project.video_url || project.result_video_url || project.final_video_url;

  if (videoUrl) {
    return {
      label: "Ready",
      className: "border-emerald-500/20 bg-emerald-500/10 text-emerald-300",
      icon: CheckCircle2,
    };
  }

  if ((summary?.failed || 0) > 0) {
    return {
      label: "Failed",
      className: "border-red-500/20 bg-red-500/10 text-red-300",
      icon: AlertCircle,
    };
  }

  if ((summary?.processing || 0) + (summary?.submitted || 0) + (summary?.queued || 0) > 0) {
    return {
      label: "Running",
      className: "border-amber-500/20 bg-amber-500/10 text-amber-300",
      icon: Loader2,
    };
  }

  return {
    label: project.status || "Pending",
    className: "border-white/[0.08] bg-white/[0.04] text-gray-300",
    icon: Clock3,
  };
}

function HistoryContent() {
  const { status } = useSession();
  const t = useT();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [selectedStatus, setSelectedStatus] = useState<ProjectStatus | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadProjects = useCallback(async () => {
    setLoadingList(true);
    setError(null);
    try {
      const data = await projectApi.list(50);
      setProjects(data.projects || []);
      setSelectedRunId((current) => current || data.projects?.[0]?.run_id || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load project history");
    } finally {
      setLoadingList(false);
    }
  }, []);

  const loadRun = useCallback(async (runId: string) => {
    setLoadingDetail(true);
    setError(null);
    try {
      const [project, statusPayload] = await Promise.all([
        projectApi.get(runId),
        projectApi.getStatus(runId),
      ]);
      setSelectedProject(project);
      setSelectedStatus(statusPayload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load project details");
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    if (status === "authenticated") {
      void loadProjects();
    }
  }, [loadProjects, status]);

  useEffect(() => {
    if (status !== "authenticated" || !selectedRunId) {
      return;
    }
    void loadRun(selectedRunId);
  }, [loadRun, selectedRunId, status]);

  useEffect(() => {
    if (status !== "authenticated") {
      return;
    }
    const intervalId = setInterval(() => {
      void loadProjects();
      if (selectedRunId) {
        void loadRun(selectedRunId);
      }
    }, 15_000);
    return () => clearInterval(intervalId);
  }, [loadProjects, loadRun, selectedRunId, status]);

  const selectedVideoUrl = useMemo(
    () =>
      selectedProject?.video_url ||
      selectedProject?.result_video_url ||
      selectedProject?.final_video_url ||
      selectedStatus?.video_url ||
      null,
    [selectedProject, selectedStatus],
  );

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#050508]">
        <Loader2 className="h-8 w-8 animate-spin text-[#E11D48]" />
      </div>
    );
  }

  if (status === "unauthenticated") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#050508] px-4 text-white">
        <div className="space-y-4 text-center">
          <p className="text-gray-400">{t("settings.loginRequired")}</p>
          <Link href="/" className="text-sm text-[#E11D48] hover:underline">
            {t("settings.backToHome")}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#050508] text-white">
      <div className="border-b border-white/[0.08] bg-black/40 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-4 md:px-8">
          <Link href="/" className="rounded-xl p-2 text-gray-400 transition-colors hover:bg-white/[0.04] hover:text-white">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div className="flex-1">
            <h1 className="text-lg font-semibold">{t("historyPage.title")}</h1>
            <p className="text-sm text-gray-500">{t("historyPage.subtitle")}</p>
          </div>
          <button
            type="button"
            onClick={() => void loadProjects()}
            className="inline-flex items-center gap-2 rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-300 transition-colors hover:bg-white/[0.06]"
          >
            <RefreshCw className="h-4 w-4" />
            {t("historyPage.refresh")}
          </button>
          <LanguageSwitcher />
        </div>
      </div>

      <div className="mx-auto grid max-w-7xl gap-6 px-4 py-6 md:grid-cols-[340px_minmax(0,1fr)] md:px-8">
        <section className="rounded-[28px] border border-white/[0.08] bg-[radial-gradient(circle_at_top,#151522_0%,#0a0a12_55%,#07070b_100%)] p-4">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-gray-500">{t("sidebar.historyProjects")}</p>
              <p className="mt-1 text-sm text-gray-400">{projects.length} runs</p>
            </div>
          </div>

          <div className="space-y-3">
            {loadingList ? (
              <div className="flex items-center justify-center py-10 text-gray-500">
                <Loader2 className="h-5 w-5 animate-spin" />
              </div>
            ) : projects.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-white/[0.08] px-4 py-10 text-center text-sm text-gray-500">
                {t("historyPage.empty")}
              </div>
            ) : (
              projects.map((project) => {
                const tone = statusTone(project, selectedRunId === project.run_id ? selectedStatus : null);
                const ToneIcon = tone.icon;
                return (
                  <button
                    key={project.run_id}
                    type="button"
                    onClick={() => setSelectedRunId(project.run_id)}
                    className={`w-full rounded-2xl border p-4 text-left transition-all ${
                      selectedRunId === project.run_id
                        ? "border-[#E11D48]/40 bg-[#E11D48]/10 shadow-[0_0_0_1px_rgba(225,29,72,0.15)]"
                        : "border-white/[0.06] bg-white/[0.03] hover:border-white/[0.12] hover:bg-white/[0.05]"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-gray-100">
                          {parseProjectTheme(project)}
                        </p>
                        <p className="mt-1 text-xs text-gray-500">{project.run_id}</p>
                      </div>
                      <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[11px] ${tone.className}`}>
                        <ToneIcon className={`h-3 w-3 ${ToneIcon === Loader2 ? "animate-spin" : ""}`} />
                        {tone.label}
                      </span>
                    </div>
                    <div className="mt-3 flex items-center justify-between text-xs text-gray-500">
                      <span>
                        {(project.task_summary?.succeeded || 0)}/{project.task_summary?.total || 0} {t("historyPage.tasks")}
                      </span>
                      <span>{formatDate(project.updated_at)}</span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </section>

        <section className="rounded-[32px] border border-white/[0.08] bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02))] p-5">
          {!selectedRunId ? (
            <div className="flex min-h-[420px] items-center justify-center text-gray-500">
              {t("historyPage.empty")}
            </div>
          ) : loadingDetail && !selectedProject ? (
            <div className="flex min-h-[420px] items-center justify-center text-gray-500">
              <Loader2 className="h-6 w-6 animate-spin" />
            </div>
          ) : (
            <div className="space-y-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-[0.24em] text-gray-500">{t("historyPage.detail")}</p>
                  <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white">
                    {selectedProject ? parseProjectTheme(selectedProject) : selectedRunId}
                  </h2>
                  <p className="mt-2 text-sm text-gray-500">{selectedRunId}</p>
                </div>
                <div className="flex flex-wrap gap-3">
                  <Link
                    href={selectedRunId ? `/?runId=${encodeURIComponent(selectedRunId)}` : "/"}
                    className="inline-flex items-center gap-2 rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-gray-200 transition-colors hover:bg-white/[0.06]"
                  >
                    <ChevronRight className="h-4 w-4" />
                    {t("historyPage.continueProject")}
                  </Link>
                  {selectedVideoUrl ? (
                    <a
                      href={selectedVideoUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 rounded-xl bg-[#E11D48] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#BE123C]"
                    >
                      <PlayCircle className="h-4 w-4" />
                      {t("historyPage.openVideo")}
                    </a>
                  ) : null}
                </div>
              </div>

              {error ? (
                <div className="rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                  {error}
                </div>
              ) : null}

              <div className="grid gap-4 md:grid-cols-4">
                <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-gray-500">{t("historyPage.status")}</p>
                  <p className="mt-3 text-lg font-medium text-white">
                    {selectedProject?.status || selectedStatus?.project_status || "-"}
                  </p>
                </div>
                <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-gray-500">{t("historyPage.tasks")}</p>
                  <p className="mt-3 text-lg font-medium text-white">
                    {(selectedStatus?.summary?.succeeded || selectedProject?.task_summary?.succeeded || 0)}/
                    {(selectedStatus?.summary?.total || selectedProject?.task_summary?.total || 0)}
                  </p>
                </div>
                <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-gray-500">{t("historyPage.createdAt")}</p>
                  <p className="mt-3 text-sm font-medium text-white">{formatDate(selectedProject?.created_at)}</p>
                </div>
                <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-gray-500">{t("historyPage.sessionStatus")}</p>
                  <p className="mt-3 text-sm font-medium text-white">
                    {typeof selectedProject?.session_status === "string"
                      ? selectedProject.session_status
                      : typeof selectedProject?.session?.status === "string"
                        ? selectedProject.session.status
                        : "-"}
                  </p>
                </div>
              </div>

              <div className="grid gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
                <div className="rounded-[28px] border border-white/[0.08] bg-black/30 p-5">
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <p className="text-xs uppercase tracking-[0.2em] text-gray-500">{t("historyPage.taskBreakdown")}</p>
                      <p className="mt-1 text-sm text-gray-400">{t("historyPage.asyncStatusHint")}</p>
                    </div>
                    {loadingDetail ? <Loader2 className="h-4 w-4 animate-spin text-gray-500" /> : null}
                  </div>
                  <div className="space-y-3">
                    {(selectedProject?.video_tasks || []).map((task: VideoTask) => (
                      <div
                        key={task.id || `${task.run_id}-${task.clip_idx}`}
                        className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="text-sm font-medium text-white">
                              Segment {task.clip_idx + 1}
                            </p>
                            <p className="mt-1 text-xs text-gray-500">{task.duration || "-"}s</p>
                          </div>
                          <span className="rounded-full border border-white/[0.08] bg-white/[0.04] px-2.5 py-1 text-[11px] text-gray-300">
                            {task.status}
                          </span>
                        </div>
                        {task.video_url ? (
                          <a
                            href={task.video_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="mt-3 inline-flex items-center gap-2 text-xs text-[#E11D48] hover:text-[#FB7185]"
                          >
                            <ExternalLink className="h-3.5 w-3.5" />
                            Provider clip
                          </a>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-[28px] border border-white/[0.08] bg-[radial-gradient(circle_at_top,rgba(225,29,72,0.16),rgba(12,12,18,0.92)_62%)] p-5">
                  <div className="flex items-center gap-3">
                    <div className="rounded-2xl bg-white/[0.06] p-3">
                      <Film className="h-5 w-5 text-[#FB7185]" />
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-[0.2em] text-gray-400">{t("historyPage.finalVideo")}</p>
                      <p className="mt-1 text-sm text-gray-500">{t("historyPage.finalVideoHint")}</p>
                    </div>
                  </div>

                  <div className="mt-5 overflow-hidden rounded-[24px] border border-white/[0.08] bg-black/40">
                    {selectedVideoUrl ? (
                      <video
                        src={selectedVideoUrl}
                        controls
                        className="aspect-[9/16] w-full bg-black object-contain"
                      />
                    ) : (
                      <div className="flex aspect-[9/16] items-center justify-center px-6 text-center text-sm text-gray-500">
                        {t("historyPage.noVideoYet")}
                      </div>
                    )}
                  </div>

                  {selectedVideoUrl ? (
                    <div className="mt-4 space-y-2">
                      <a
                        href={selectedVideoUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-2 text-sm text-white hover:text-[#FB7185]"
                      >
                        <PlayCircle className="h-4 w-4" />
                        {t("historyPage.openVideo")}
                      </a>
                      <p className="break-all text-xs text-gray-500">{selectedVideoUrl}</p>
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

export default function ProjectsPage() {
  return (
    <SessionProvider>
      <HistoryContent />
    </SessionProvider>
  );
}
