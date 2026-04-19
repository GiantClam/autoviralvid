"use client";
/* eslint-disable @next/next/no-img-element */

import Link from "next/link";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  Clapperboard,
  Download,
  FileText,
  Hash,
  Loader2,
  RefreshCw,
  SlidersHorizontal,
  Type,
} from "lucide-react";

const API_BASE = "/api/ppt";
const DIRECT_PPT_API_BASE = (() => {
  const raw = (process.env.NEXT_PUBLIC_AGENT_URL || process.env.NEXT_PUBLIC_API_BASE || "").trim();
  if (!raw) return "";
  return `${raw.replace(/\/+$/, "")}/api/v1/ppt`;
})();
const DIRECT_API_ORIGIN = (() => {
  if (!DIRECT_PPT_API_BASE) return "";
  try {
    return new URL(DIRECT_PPT_API_BASE).origin;
  } catch {
    return "";
  }
})();
const HISTORY_KEY = "autoviralvid-ppt-prompt-history";
let cachedApiToken: string | null = null;

type DeckStyle = "professional" | "creative" | "academic" | "minimal";
type Phase = "idle" | "loading_templates" | "loading_preview" | "generating" | "done" | "error";

type ApiEnvelope<T> = {
  success: boolean;
  data?: T;
  error?: string | Record<string, unknown>;
};

type TemplateItem = {
  name: string;
  path?: string;
  description?: string;
};

type TemplatesResponse = {
  templates: TemplateItem[];
};

type AIPromptPptResult = {
  success: boolean;
  project_name: string;
  project_path: string;
  total_slides: number;
  generated_content: {
    source_md?: string;
    design_spec?: string;
  };
  design_spec?: Record<string, unknown>;
  svg_files?: string[];
  output_pptx?: string | null;
  artifacts?: Record<string, string>;
  generation_time_seconds: number;
};

type PromptJobStart = {
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  project_name: string;
  project_path: string;
  poll_url: string;
  created_at: string;
};

type PromptJobProgress = {
  stage: string;
  detail: string;
  percent: number;
  current_page: number;
  total_pages: number;
  generated_slides: number;
};

type PromptJobStatus = {
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  project_name: string;
  project_path: string;
  created_at?: string;
  started_at?: string | null;
  updated_at?: string;
  finished_at?: string | null;
  progress?: PromptJobProgress;
  result?: AIPromptPptResult;
  error?: string;
};

type ProjectPreview = {
  project_name: string;
  project_path: string;
  output_pptx?: string | null;
  source_excerpt: string;
  design_excerpt: string;
  notes_excerpt: string;
  preview_image_urls: string[];
  svg_count: number;
};

type PptHistoryItem = {
  id: string;
  createdAt: string;
  projectName: string;
  prompt: string;
  slides: number;
  status: "success" | "failed";
  downloadUrl?: string;
  error?: string;
};

type PPTPromptWorkspaceProps = {
  embedded?: boolean;
};

type FieldLabelProps = {
  icon: React.ElementType;
  children: React.ReactNode;
};

function FieldLabel({ icon: Icon, children }: FieldLabelProps) {
  return (
    <div className="mb-2 flex items-center gap-2">
      <div className="flex h-5 w-5 items-center justify-center rounded-md bg-gradient-to-br from-[#E11D48]/20 to-purple-500/10">
        <Icon className="h-3 w-3 text-[#E11D48]" />
      </div>
      <span className="text-xs font-semibold text-gray-300">{children}</span>
    </div>
  );
}

function FieldDivider() {
  return <div className="my-4 border-t border-white/[0.04]" />;
}

function readEnvelopeError(error: string | Record<string, unknown> | undefined): string {
  if (typeof error === "string" && error.trim()) {
    return error;
  }
  if (error && typeof error === "object") {
    const msg = String((error as { message?: string }).message || "").trim();
    if (msg) {
      return msg;
    }
  }
  return "API error";
}

function loadHistory(): PptHistoryItem[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as PptHistoryItem[]) : [];
  } catch {
    return [];
  }
}

function persistHistory(next: PptHistoryItem[]): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(HISTORY_KEY, JSON.stringify(next.slice(0, 20)));
  } catch {
    // Ignore write failures (private mode / quota issues)
  }
}

async function apiGet<T>(path: string): Promise<T> {
  const json = await apiRequest<T>("GET", path);
  if (!json.success) {
    throw new Error(readEnvelopeError(json.error));
  }
  if (json.data === undefined) {
    throw new Error("API returned success without data");
  }
  return json.data;
}

async function apiPost<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const json = await apiRequest<T>("POST", path, body);
  if (!json.success) {
    throw new Error(readEnvelopeError(json.error));
  }
  if (json.data === undefined) {
    throw new Error("API returned success without data");
  }
  return json.data;
}

async function getApiToken(): Promise<string | null> {
  if (cachedApiToken) {
    return cachedApiToken;
  }
  try {
    const res = await fetch("/api/auth/api-token", { method: "POST" });
    if (!res.ok) {
      return null;
    }
    const payload = (await res.json()) as { token?: string };
    const token = String(payload?.token || "").trim();
    if (!token) {
      return null;
    }
    cachedApiToken = token;
    return token;
  } catch {
    return null;
  }
}

function envelopeFromUnknown<T>(status: number, payload: unknown, fallbackText: string): ApiEnvelope<T> {
  if (payload && typeof payload === "object") {
    const asObj = payload as Record<string, unknown>;
    if ("success" in asObj) {
      return asObj as ApiEnvelope<T>;
    }
    const detail =
      typeof asObj.error === "string"
        ? asObj.error
        : typeof asObj.detail === "string"
          ? asObj.detail
          : fallbackText;
    return { success: false, error: detail || `HTTP ${status}` };
  }
  if (status >= 200 && status < 300 && payload !== undefined) {
    return { success: true, data: payload as T };
  }
  return { success: false, error: fallbackText || `HTTP ${status}` };
}

function withTokenQuery(url: string, token: string | null): string {
  if (!token) return url;
  try {
    const parsed = new URL(url);
    parsed.searchParams.set("token", token);
    return parsed.toString();
  } catch {
    return url.includes("?") ? `${url}&token=${encodeURIComponent(token)}` : `${url}?token=${encodeURIComponent(token)}`;
  }
}

function resolvePptAssetUrl(url: string, token: string | null): string {
  const raw = String(url || "").trim();
  if (!raw) return raw;
  if (raw.startsWith("http://") || raw.startsWith("https://")) {
    return withTokenQuery(raw, token);
  }
  if (DIRECT_API_ORIGIN && (raw.startsWith("/api/v1/ppt/") || raw.startsWith("/api/ppt/"))) {
    return withTokenQuery(`${DIRECT_API_ORIGIN}${raw}`, token);
  }
  return raw;
}

async function decodeEnvelope<T>(res: Response): Promise<ApiEnvelope<T>> {
  const contentType = String(res.headers.get("content-type") || "").toLowerCase();
  let payload: unknown = null;
  let fallbackText = "";

  if (contentType.includes("application/json")) {
    try {
      payload = await res.json();
    } catch {
      payload = null;
    }
  } else {
    try {
      fallbackText = (await res.text()).slice(0, 300);
    } catch {
      fallbackText = "";
    }
  }

  if (!res.ok && !fallbackText && payload && typeof payload === "object") {
    const asObj = payload as Record<string, unknown>;
    fallbackText = String(asObj.error || asObj.detail || "").trim();
  }
  return envelopeFromUnknown<T>(res.status, payload, fallbackText);
}

async function apiRequest<T>(
  method: "GET" | "POST",
  path: string,
  body?: Record<string, unknown>,
): Promise<ApiEnvelope<T>> {
  const primaryResponse = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (primaryResponse.status !== 404 || !DIRECT_PPT_API_BASE) {
    return decodeEnvelope<T>(primaryResponse);
  }

  const token = await getApiToken();
  if (!token) {
    return decodeEnvelope<T>(primaryResponse);
  }

  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
  };
  if (body) {
    headers["Content-Type"] = "application/json";
  }

  const fallbackResponse = await fetch(`${DIRECT_PPT_API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  return decodeEnvelope<T>(fallbackResponse);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export default function PPTPromptWorkspace({ embedded = false }: PPTPromptWorkspaceProps) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [prompt, setPrompt] = useState("");
  const [style, setStyle] = useState<DeckStyle>("professional");
  const [totalPages, setTotalPages] = useState(10);
  const [templateFamily, setTemplateFamily] = useState("auto");

  const [templates, setTemplates] = useState<TemplateItem[]>([]);
  const [result, setResult] = useState<AIPromptPptResult | null>(null);
  const [preview, setPreview] = useState<ProjectPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [history, setHistory] = useState<PptHistoryItem[]>(() => loadHistory());
  const [assetToken, setAssetToken] = useState<string | null>(null);

  const isBusy = phase === "loading_templates" || phase === "loading_preview" || phase === "generating";

  const selectedTemplate = useMemo(
    () => templates.find((item) => item.name === templateFamily),
    [templateFamily, templates],
  );
  const previewImageUrls = useMemo(
    () =>
      Array.isArray(preview?.preview_image_urls)
        ? preview.preview_image_urls.map((url) => resolvePptAssetUrl(url, assetToken))
        : [],
    [assetToken, preview?.preview_image_urls],
  );

  const pptxPath = String(result?.output_pptx || preview?.output_pptx || "").trim();
  const hasHttpPptx = pptxPath.startsWith("http://") || pptxPath.startsWith("https://");
  const apiDownloadUrl = result
    ? resolvePptAssetUrl(`${API_BASE}/download-output/${encodeURIComponent(result.project_name)}`, assetToken)
    : "";

  const addLog = useCallback((msg: string) => {
    setLog((prev) => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`]);
  }, []);

  const pushHistory = useCallback((item: PptHistoryItem) => {
    setHistory((prev) => {
      const next = [item, ...prev].slice(0, 20);
      persistHistory(next);
      return next;
    });
  }, []);

  const loadTemplates = useCallback(async (withLoadingState: boolean) => {
    if (withLoadingState) {
      setPhase("loading_templates");
    }
    setError(null);
    addLog("Loading template catalog...");
    try {
      const data = await apiGet<TemplatesResponse>("/templates");
      const templateRows = Array.isArray(data.templates) ? data.templates : [];
      setTemplates(templateRows);
      addLog(`Template catalog loaded: ${templateRows.length}`);
      if (withLoadingState) {
        setPhase("idle");
      }
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unknown error";
      setError(message);
      setPhase("error");
      addLog(`Template catalog failed: ${message}`);
    }
  }, [addLog]);

  const loadPreview = useCallback(async (projectName: string) => {
    setPhase("loading_preview");
    addLog(`Loading preview for ${projectName}...`);
    try {
      const token = await getApiToken();
      if (token) {
        setAssetToken(token);
      }
      const data = await apiGet<ProjectPreview>(`/preview/${encodeURIComponent(projectName)}`);
      setPreview(data);
      setPhase("done");
      addLog("Preview loaded");
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unknown error";
      setPhase("error");
      addLog(`Preview load failed: ${message}`);
    }
  }, [addLog]);

  const pollPromptJob = useCallback(async (jobId: string): Promise<AIPromptPptResult> => {
    const startedAt = Date.now();
    const timeoutMs = 45 * 60 * 1000;
    let lastMarker = "";

    while (Date.now() - startedAt < timeoutMs) {
      const job = await apiGet<PromptJobStatus>(`/jobs/${encodeURIComponent(jobId)}`);
      const progress = job.progress;
      const marker = [
        job.status,
        progress?.stage || "",
        progress?.current_page || 0,
        progress?.generated_slides || 0,
      ].join("|");

      if (marker !== lastMarker) {
        lastMarker = marker;
        if (progress) {
          addLog(
            `Job ${job.job_id}: ${progress.stage} - ${progress.detail} (${progress.current_page}/${progress.total_pages}, ${progress.percent.toFixed(1)}%)`,
          );
        } else {
          addLog(`Job ${job.job_id}: status=${job.status}`);
        }
      }

      if (job.status === "succeeded" && job.result) {
        return job.result;
      }
      if (job.status === "failed") {
        throw new Error(job.error || "Generation failed");
      }

      await delay(3000);
    }

    throw new Error("Generation polling timed out");
  }, [addLog]);

  useEffect(() => {
    const timer = setTimeout(() => {
      void loadTemplates(false);
    }, 0);
    return () => clearTimeout(timer);
  }, [loadTemplates]);

  useEffect(() => {
    let cancelled = false;
    void getApiToken().then((token) => {
      if (!cancelled && token) {
        setAssetToken(token);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleGenerate = useCallback(async () => {
    const promptText = prompt.trim();
    if (!promptText) {
      setError("Prompt is required");
      return;
    }

    setPhase("generating");
    setError(null);
    setResult(null);
    setPreview(null);

    addLog(`Starting generation (pages=${totalPages}, style=${style}, template=${templateFamily})...`);

    try {
      const kickoff = await apiPost<PromptJobStart>("/generate-from-prompt", {
        prompt: promptText,
        total_pages: totalPages,
        style,
        color_scheme: null,
        language: "zh-CN",
        include_images: false,
        template_family: templateFamily === "auto" ? null : templateFamily,
      });
      addLog(`Job created: ${kickoff.job_id}. Waiting for completion...`);
      const data = await pollPromptJob(kickoff.job_id);
      setResult(data);
      pushHistory({
        id: `${Date.now()}-${data.project_name}`,
        createdAt: new Date().toISOString(),
        projectName: data.project_name,
        prompt: promptText,
        slides: data.total_slides,
        status: "success",
        downloadUrl: `${API_BASE}/download-output/${encodeURIComponent(data.project_name)}`,
      });
      addLog(`Generation done: slides=${data.total_slides}, time=${data.generation_time_seconds.toFixed(1)}s`);
      await loadPreview(data.project_name);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unknown error";
      setError(message);
      setPhase("error");
      pushHistory({
        id: `${Date.now()}-failed`,
        createdAt: new Date().toISOString(),
        projectName: "-",
        prompt: promptText,
        slides: totalPages,
        status: "failed",
        error: message,
      });
      addLog(`Generation failed: ${message}`);
    }
  }, [
    addLog,
    loadPreview,
    pollPromptJob,
    prompt,
    pushHistory,
    style,
    templateFamily,
    totalPages,
  ]);

  const inputClass =
    "w-full rounded-xl bg-white/[0.03] border border-white/[0.06] text-gray-200 text-[13px] px-3.5 py-2.5 outline-none transition-all duration-300 placeholder:text-gray-600 focus:border-[#E11D48]/50 focus:ring-2 focus:ring-[#E11D48]/10 focus:bg-white/[0.05] hover:border-white/[0.12] hover:bg-white/[0.04]";
  const selectClass =
    "avv-select w-full appearance-none rounded-xl bg-white/[0.03] border border-white/[0.06] text-gray-200 text-[13px] px-3.5 py-2.5 pr-9 outline-none transition-all duration-300 focus:border-[#E11D48]/50 focus:ring-2 focus:ring-[#E11D48]/10 focus:bg-white/[0.05] hover:border-white/[0.12] hover:bg-white/[0.04] cursor-pointer";
  const containerClass = embedded
    ? "flex min-h-0 flex-1 flex-col bg-[#050508] text-gray-100"
    : "flex h-screen flex-col bg-[#050508] text-gray-100";

  return (
    <div className={containerClass}>
      {!embedded ? (
        <div className="h-16 shrink-0 border-b border-white/[0.06] bg-black/40 px-4 backdrop-blur-xl md:px-8">
          <div className="mx-auto flex h-full max-w-7xl items-center justify-between">
            <div className="flex items-center gap-3">
              <Link
                href="/"
                className="inline-flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2.5 py-1.5 text-xs text-gray-300 transition hover:bg-white/[0.08]"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Back
              </Link>
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-[#E11D48] to-[#9333EA]">
                  <Clapperboard className="h-4 w-4 text-white" />
                </div>
                <div>
                  <h1 className="text-sm font-semibold text-white" data-testid="ppt-page-title">PPT Generator Workspace</h1>
                  <p className="text-[11px] text-gray-500">Same workflow shell as template pages</p>
                </div>
              </div>
            </div>
            <div className="rounded-full border border-white/[0.12] bg-white/[0.03] px-3 py-1 text-xs text-gray-400">
              Phase: <span className="font-medium text-gray-200">{phase}</span>
              {isBusy ? <Loader2 className="ml-2 inline h-3.5 w-3.5 animate-spin text-[#E11D48]" /> : null}
            </div>
          </div>
        </div>
      ) : null}

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <aside className="flex h-full w-full shrink-0 flex-col overflow-hidden border-r border-white/[0.06] bg-[#0a0a12]/80 backdrop-blur-xl md:w-[380px]">
          <div className="border-b border-white/[0.06] bg-gradient-to-r from-[#E11D48]/5 to-transparent px-5 py-4">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-[#E11D48] to-[#9333EA] shadow-lg shadow-[#E11D48]/20">
                <Clapperboard className="h-4 w-4 text-white" />
              </div>
              <div className="flex-1">
                <h2 className="text-sm font-bold tracking-tight text-white">PPT Config</h2>
                <span className="text-[10px] text-gray-500">Prompt to PPT</span>
              </div>
            </div>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
            <section>
              <FieldLabel icon={Type}>Prompt</FieldLabel>
              <div className="mb-2 flex items-center gap-1.5 text-[11px] text-gray-500">
                <Type className="h-3.5 w-3.5 text-[#E11D48]/80" />
                <span>Describe topic, audience, and expected output in one paragraph.</span>
              </div>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={6}
                placeholder="Describe the presentation topic, audience, and expected outcome..."
                className={`${inputClass} resize-none`}
                disabled={isBusy}
              />
              <p className="mt-2 text-xs text-gray-500">
                Only three parameters are required: total pages, style, and template.
              </p>
            </section>

            <FieldDivider />

            <section>
              <FieldLabel icon={SlidersHorizontal}>Parameters</FieldLabel>
              <div className="space-y-2.5">
                <div>
                  <p className="mb-1 text-[11px] text-gray-500">Total Pages</p>
                  <div className="mb-1 flex items-center gap-1.5 text-[11px] text-gray-500">
                    <Hash className="h-3.5 w-3.5 text-[#E11D48]/80" />
                    <span>Recommended range: 8-12 pages for best structure quality.</span>
                  </div>
                  <input
                    type="number"
                    min={3}
                    max={50}
                    value={totalPages}
                    onChange={(e) => setTotalPages(Math.min(50, Math.max(3, parseInt(e.target.value || "10", 10))))}
                    className={inputClass}
                    disabled={isBusy}
                  />
                </div>
                <div>
                  <p className="mb-1 text-[11px] text-gray-500">Style</p>
                  <div className="relative">
                    <select
                      value={style}
                      onChange={(e) => setStyle(e.target.value as DeckStyle)}
                      className={selectClass}
                      disabled={isBusy}
                    >
                      <option value="professional">professional</option>
                      <option value="creative">creative</option>
                      <option value="academic">academic</option>
                      <option value="minimal">minimal</option>
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-500" />
                  </div>
                </div>
                <div>
                  <p className="mb-1 text-[11px] text-gray-500">Template</p>
                  <div className="relative">
                    <select
                      value={templateFamily}
                      onChange={(e) => setTemplateFamily(e.target.value)}
                      className={selectClass}
                      disabled={isBusy}
                    >
                      <option value="auto">auto</option>
                      {templates.map((row) => (
                        <option key={row.name} value={row.name}>
                          {row.name}
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-500" />
                  </div>
                </div>
                {selectedTemplate?.description ? (
                  <p className="text-xs text-gray-500">{selectedTemplate.description}</p>
                ) : null}
              </div>
            </section>

            <section>
              <button
                onClick={handleGenerate}
                disabled={isBusy || !prompt.trim()}
                className="mt-3 w-full rounded-xl bg-gradient-to-r from-[#E11D48] to-[#9333EA] py-2.5 text-sm font-semibold text-white shadow-lg shadow-[#E11D48]/20 transition hover:from-[#F43F5E] hover:to-[#A855F7] disabled:opacity-50"
                data-testid="btn-generate-from-prompt"
              >
                {isBusy ? "Generating..." : "Generate PPT"}
              </button>
            </section>
          </div>
        </aside>

        <main className="min-h-0 flex-1 overflow-y-auto p-5">
          <div className="mx-auto grid max-w-6xl grid-cols-1 gap-5 xl:grid-cols-3">
            <section className="xl:col-span-2 space-y-5">
              {error ? (
                <div className="rounded-xl border border-red-500/20 bg-red-500/[0.08] px-3 py-2 text-sm text-red-300">
                  {error}
                </div>
              ) : null}

              <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
                <div className="mb-3 flex items-center justify-between">
                  <h2 className="text-sm font-semibold">Result Preview</h2>
                  {result?.project_name ? (
                    <button
                      type="button"
                      className="inline-flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1 text-xs text-gray-200 hover:bg-white/[0.08]"
                      onClick={() => void loadPreview(result.project_name)}
                      disabled={isBusy}
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      Refresh
                    </button>
                  ) : null}
                </div>

                {!result ? (
                  <p className="py-16 text-center text-sm text-gray-500">Generate first to view project preview and download.</p>
                ) : (
                  <div className="space-y-3 text-sm">
                    <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                      <div className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-3">
                        <div className="text-gray-400">Project</div>
                        <div className="mt-1 break-all font-mono text-xs text-gray-200">{result.project_name}</div>
                      </div>
                      <div className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-3">
                        <div className="text-gray-400">Project Path</div>
                        <div className="mt-1 break-all font-mono text-xs text-gray-200">{result.project_path}</div>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                      <div className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-3">
                        <div className="text-gray-400">Slides</div>
                        <div className="mt-1 text-lg font-semibold text-gray-100">{result.total_slides}</div>
                      </div>
                      <div className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-3">
                        <div className="text-gray-400">Time</div>
                        <div className="mt-1 text-lg font-semibold text-gray-100">{result.generation_time_seconds.toFixed(1)}s</div>
                      </div>
                    </div>

                    <div className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-3">
                      <div className="text-gray-400">Download</div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {apiDownloadUrl ? (
                          <a
                            href={apiDownloadUrl}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-[#E11D48]/40 bg-[#E11D48]/15 px-2.5 py-1 text-xs text-[#F9A8D4] hover:bg-[#E11D48]/25"
                          >
                            <Download className="h-3.5 w-3.5" />
                            Download via API
                          </a>
                        ) : null}
                        {hasHttpPptx ? (
                          <a
                            href={pptxPath}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1.5 rounded-lg border border-white/[0.15] bg-white/[0.05] px-2.5 py-1 text-xs text-gray-200 hover:bg-white/[0.09]"
                          >
                            <FileText className="h-3.5 w-3.5" />
                            Open output URL
                          </a>
                        ) : null}
                      </div>
                    </div>

                    <div className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-3">
                      <div className="mb-2 text-gray-400">Page Preview</div>
                      {previewImageUrls.length ? (
                        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                          {previewImageUrls.map((url, idx) => (
                            <img
                              key={`${url}-${idx}`}
                              src={url}
                              alt={`slide-preview-${idx + 1}`}
                              className="h-24 w-full rounded-md border border-white/[0.1] object-cover"
                            />
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-gray-500">No image preview URLs returned by runtime.</p>
                      )}
                      <div className="mt-2 text-xs text-gray-500">SVG count detected: {preview?.svg_count ?? 0}</div>
                    </div>
                  </div>
                )}
              </div>

              <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
                <h3 className="mb-2 text-sm font-semibold">Content Excerpts</h3>
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-3">
                    <div className="mb-1 text-xs text-gray-400">Source</div>
                    <pre className="max-h-40 overflow-auto whitespace-pre-wrap text-xs text-gray-300">
                      {preview?.source_excerpt || "No source excerpt available."}
                    </pre>
                  </div>
                  <div className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-3">
                    <div className="mb-1 text-xs text-gray-400">Design</div>
                    <pre className="max-h-40 overflow-auto whitespace-pre-wrap text-xs text-gray-300">
                      {preview?.design_excerpt || "No design spec excerpt available."}
                    </pre>
                  </div>
                </div>
              </div>
            </section>

            <section className="space-y-5">
              <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
                <h3 className="mb-2 text-sm font-semibold">Operation Logs</h3>
                <div className="h-72 space-y-1 overflow-y-auto font-mono text-xs" data-testid="log-panel">
                  {log.length === 0 ? (
                    <p className="text-gray-500">Waiting for actions...</p>
                  ) : (
                    log.map((line, i) => (
                      <div key={`${line}-${i}`} className="text-gray-400">
                        {line}
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
                <h3 className="mb-2 text-sm font-semibold">Recent Runs</h3>
                <div className="max-h-80 space-y-2 overflow-y-auto text-xs">
                  {history.length === 0 ? (
                    <p className="text-gray-500">No generation history yet.</p>
                  ) : (
                    history.map((item) => (
                      <div key={item.id} className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-2.5">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0 flex-1">
                            <div className="truncate font-medium text-gray-200">{item.projectName}</div>
                            <div className="truncate text-gray-500">{item.prompt}</div>
                            <div className="mt-1 text-[11px] text-gray-500">
                              {item.slides} slides · {new Date(item.createdAt).toLocaleString()}
                            </div>
                            {item.error ? (
                              <div className="mt-1 truncate text-[11px] text-red-300">{item.error}</div>
                            ) : null}
                          </div>
                          <div className="flex shrink-0 items-center gap-2">
                            {item.status === "success" ? (
                              <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-300">
                                <CheckCircle2 className="h-3 w-3" />
                                success
                              </span>
                            ) : (
                              <span className="rounded-full border border-red-500/25 bg-red-500/10 px-2 py-0.5 text-[10px] text-red-300">
                                failed
                              </span>
                            )}
                            {item.downloadUrl ? (
                              <a
                                href={item.downloadUrl}
                                className="rounded-md border border-white/[0.12] bg-white/[0.03] px-2 py-0.5 text-[10px] text-gray-300 hover:bg-white/[0.07]"
                              >
                                download
                              </a>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </section>
          </div>
        </main>
      </div>
    </div>
  );
}



