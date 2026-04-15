"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";

const API_BASE = "/api/ppt";

type Language = "zh-CN" | "en-US";
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

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  const json = (await res.json()) as ApiEnvelope<T>;
  if (!json.success) {
    throw new Error(readEnvelopeError(json.error));
  }
  if (json.data === undefined) {
    throw new Error("API returned success without data");
  }
  return json.data;
}

async function apiPost<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = (await res.json()) as ApiEnvelope<T>;
  if (!json.success) {
    throw new Error(readEnvelopeError(json.error));
  }
  if (json.data === undefined) {
    throw new Error("API returned success without data");
  }
  return json.data;
}

export default function PPTPromptPage() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [prompt, setPrompt] = useState(
    "Create a university classroom presentation on the Strait of Hormuz crisis and its impact on international relations.",
  );
  const [structureHint, setStructureHint] = useState(
    [
      "1) Course objective and scope",
      "2) Strategic geography of the Strait of Hormuz",
      "3) Historical timeline and escalation points",
      "4) Legal and maritime security perspectives",
      "5) Major state and non-state actors",
      "6) International relations and energy market impact",
      "7) Scenarios, policy options, and class discussion",
    ].join("\n"),
  );
  const [language, setLanguage] = useState<Language>("zh-CN");
  const [style, setStyle] = useState<DeckStyle>("professional");
  const [totalPages, setTotalPages] = useState(10);
  const [colorScheme, setColorScheme] = useState("");
  const [includeImages, setIncludeImages] = useState(false);
  const [templateFamily, setTemplateFamily] = useState("auto");

  const [confirmContent, setConfirmContent] = useState(false);
  const [confirmStructure, setConfirmStructure] = useState(false);
  const [confirmTemplate, setConfirmTemplate] = useState(false);

  const [templates, setTemplates] = useState<TemplateItem[]>([]);
  const [result, setResult] = useState<AIPromptPptResult | null>(null);
  const [preview, setPreview] = useState<ProjectPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [log, setLog] = useState<string[]>([]);

  const panelClass =
    "rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4 backdrop-blur-sm";
  const inputClass =
    "w-full rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-200 outline-none placeholder:text-gray-600 transition-colors focus:border-[#E11D48]/50";
  const selectClass =
    "rounded-xl border border-white/[0.08] bg-white/[0.03] px-2 py-1.5 text-sm text-gray-200 outline-none transition-colors focus:border-[#E11D48]/50";
  const primaryBtnClass =
    "w-full rounded-xl bg-gradient-to-r from-[#E11D48] to-[#9333EA] py-2 text-sm font-medium text-white transition hover:from-[#F43F5E] hover:to-[#A855F7] disabled:opacity-50";
  const softBtnClass =
    "w-full rounded-xl border border-white/[0.08] bg-white/[0.04] py-2 text-sm text-gray-200 transition hover:bg-white/[0.08] disabled:opacity-50";

  const isBusy = phase === "loading_templates" || phase === "loading_preview" || phase === "generating";
  const confirmationsReady = confirmContent && confirmStructure && confirmTemplate;

  const selectedTemplate = useMemo(
    () => templates.find((item) => item.name === templateFamily),
    [templateFamily, templates],
  );

  const addLog = useCallback((msg: string) => {
    setLog((prev) => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`]);
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

  useEffect(() => {
    const timer = setTimeout(() => {
      void loadTemplates(false);
    }, 0);
    return () => clearTimeout(timer);
  }, [loadTemplates]);

  const handleGenerate = useCallback(async () => {
    const promptText = prompt.trim();
    if (!promptText) {
      setError("Prompt is required");
      return;
    }
    if (!confirmationsReady) {
      const msg = "Please confirm content, structure, and template before generation.";
      setError(msg);
      addLog(msg);
      return;
    }

    setPhase("generating");
    setError(null);
    setResult(null);
    setPreview(null);

    const mergedPrompt = structureHint.trim()
      ? `${promptText}\n\nPreferred slide structure:\n${structureHint.trim()}`
      : promptText;

    addLog(`Starting generation (pages=${totalPages}, style=${style}, template=${templateFamily})...`);

    try {
      const data = await apiPost<AIPromptPptResult>("/generate-from-prompt", {
        prompt: mergedPrompt,
        total_pages: totalPages,
        style,
        color_scheme: colorScheme.trim() || null,
        language,
        include_images: includeImages,
        template_family: templateFamily === "auto" ? null : templateFamily,
      });
      setResult(data);
      addLog(`Generation done: slides=${data.total_slides}, time=${data.generation_time_seconds.toFixed(1)}s`);
      await loadPreview(data.project_name);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unknown error";
      setError(message);
      setPhase("error");
      addLog(`Generation failed: ${message}`);
    }
  }, [
    addLog,
    colorScheme,
    confirmationsReady,
    includeImages,
    language,
    loadPreview,
    prompt,
    structureHint,
    style,
    templateFamily,
    totalPages,
  ]);

  const pptxPath = String(result?.output_pptx || preview?.output_pptx || "").trim();
  const hasHttpPptx = pptxPath.startsWith("http://") || pptxPath.startsWith("https://");
  const apiDownloadUrl = result
    ? `${API_BASE}/download-output/${encodeURIComponent(result.project_name)}`
    : "";

  return (
    <div className="min-h-screen bg-[#050508] text-gray-100">
      <div className="mx-auto max-w-7xl p-6">
        <div className="mb-6">
          <h1 className="text-2xl font-bold tracking-tight" data-testid="ppt-page-title">
            <span className="bg-gradient-to-r from-white to-gray-300 bg-clip-text text-transparent">
              Prompt to PPT Studio
            </span>
          </h1>
          <p className="mt-1 text-sm text-gray-500">Main flow: Prompt direct output with ppt-master</p>
        </div>

        {error && (
          <div className="mb-4 rounded-xl border border-red-500/20 bg-red-500/[0.08] px-3 py-2 text-sm text-red-300">
            {error}
          </div>
        )}

        <div className="mb-4 rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-sm text-gray-400">
          Current phase: <strong className="text-gray-200">{phase}</strong>
          {isBusy && <span className="ml-2 animate-pulse text-[#E11D48]">processing...</span>}
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="flex flex-col gap-4 lg:col-span-1">
            <div className={panelClass}>
              <h2 className="mb-3 text-sm font-semibold">Prompt and Parameters</h2>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={5}
                placeholder="Describe the presentation goal and audience..."
                className={`${inputClass} resize-none`}
                disabled={isBusy}
              />

              <textarea
                value={structureHint}
                onChange={(e) => setStructureHint(e.target.value)}
                rows={6}
                placeholder="Optional: one structure hint per line"
                className={`${inputClass} mt-2 resize-none`}
                disabled={isBusy}
              />

              <div className="mt-3 grid grid-cols-2 gap-2">
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value as Language)}
                  className={selectClass}
                  disabled={isBusy}
                >
                  <option value="zh-CN">zh-CN</option>
                  <option value="en-US">en-US</option>
                </select>
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
              </div>

              <div className="mt-2 grid grid-cols-2 gap-2">
                <input
                  type="number"
                  min={3}
                  max={50}
                  value={totalPages}
                  onChange={(e) => setTotalPages(Math.min(50, Math.max(3, parseInt(e.target.value || "10", 10))))}
                  className={inputClass}
                  disabled={isBusy}
                />
                <input
                  value={colorScheme}
                  onChange={(e) => setColorScheme(e.target.value)}
                  placeholder="color_scheme (optional)"
                  className={inputClass}
                  disabled={isBusy}
                />
              </div>

              <div className="mt-2 grid grid-cols-[1fr_auto] gap-2">
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
                <label className="flex items-center gap-2 rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-sm text-gray-300">
                  <input
                    type="checkbox"
                    checked={includeImages}
                    onChange={(e) => setIncludeImages(e.target.checked)}
                    disabled={isBusy}
                  />
                  images
                </label>
              </div>
            </div>

            <div className={panelClass}>
              <h2 className="mb-3 text-sm font-semibold">Confirmation Gate</h2>
              <p className="mb-3 text-xs text-gray-500">
                Confirm content intent, page structure, and template choice before generation.
              </p>

              <div className="space-y-2 text-sm text-gray-300">
                <label className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    checked={confirmContent}
                    onChange={(e) => setConfirmContent(e.target.checked)}
                    disabled={isBusy}
                  />
                  <span>I confirm the content objective and audience are correct.</span>
                </label>
                <label className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    checked={confirmStructure}
                    onChange={(e) => setConfirmStructure(e.target.checked)}
                    disabled={isBusy}
                  />
                  <span>I confirm the page structure hints are ready.</span>
                </label>
                <label className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    checked={confirmTemplate}
                    onChange={(e) => setConfirmTemplate(e.target.checked)}
                    disabled={isBusy}
                  />
                  <span>
                    I confirm template selection: <strong>{templateFamily}</strong>
                    {selectedTemplate?.description ? ` (${selectedTemplate.description})` : ""}
                  </span>
                </label>
              </div>

              <button
                onClick={handleGenerate}
                disabled={isBusy || !prompt.trim() || !confirmationsReady}
                className={`mt-3 ${primaryBtnClass}`}
                data-testid="btn-generate-from-prompt"
              >
                Generate PPT
              </button>
              <button
                onClick={() => void loadTemplates(true)}
                disabled={isBusy}
                className={`mt-2 ${softBtnClass}`}
                data-testid="btn-refresh-templates"
              >
                Refresh template list
              </button>
            </div>

            <div className={panelClass}>
              <h2 className="mb-3 text-sm font-semibold">Template Catalog</h2>
              <div className="max-h-80 space-y-2 overflow-y-auto text-xs">
                {templates.length === 0 ? (
                  <p className="text-gray-500">No template data</p>
                ) : (
                  templates.map((row) => (
                    <div key={row.name} className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-2">
                      <div className="font-medium text-gray-200">{row.name}</div>
                      {row.description ? <div className="mt-1 text-gray-500">{row.description}</div> : null}
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>

          <div className="lg:col-span-1">
            <div className={`${panelClass} min-h-[780px]`}>
              <div className="mb-3 flex items-center justify-between gap-2">
                <h2 className="text-sm font-semibold">Result Preview</h2>
                {result?.project_name ? (
                  <button
                    type="button"
                    className="rounded-lg border border-white/[0.08] bg-white/[0.03] px-2 py-1 text-xs text-gray-200 hover:bg-white/[0.08]"
                    onClick={() => void loadPreview(result.project_name)}
                    disabled={isBusy}
                  >
                    Refresh preview
                  </button>
                ) : null}
              </div>

              {!result ? (
                <p className="py-20 text-center text-sm text-gray-500">Generate first to view project preview and download.</p>
              ) : (
                <div className="space-y-3 text-sm">
                  <div className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-3">
                    <div className="text-gray-400">Project</div>
                    <div className="mt-1 font-mono text-xs text-gray-200">{result.project_name}</div>
                  </div>
                  <div className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-3">
                    <div className="text-gray-400">Project Path</div>
                    <div className="mt-1 break-all font-mono text-xs text-gray-200">{result.project_path}</div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-3">
                      <div className="text-gray-400">Slides</div>
                      <div className="mt-1 text-lg font-semibold text-gray-100">{result.total_slides}</div>
                    </div>
                    <div className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-3">
                      <div className="text-gray-400">Time</div>
                      <div className="mt-1 text-lg font-semibold text-gray-100">
                        {result.generation_time_seconds.toFixed(1)}s
                      </div>
                    </div>
                  </div>

                  <div className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-3">
                    <div className="text-gray-400">Download</div>
                    <div className="mt-1 flex flex-wrap gap-2">
                      {apiDownloadUrl ? (
                        <a
                          href={apiDownloadUrl}
                          className="rounded-lg border border-[#E11D48]/40 bg-[#E11D48]/15 px-2 py-1 text-xs text-[#F9A8D4] hover:bg-[#E11D48]/25"
                        >
                          Download via API
                        </a>
                      ) : null}
                      {hasHttpPptx ? (
                        <a
                          href={pptxPath}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-lg border border-white/[0.15] bg-white/[0.05] px-2 py-1 text-xs text-gray-200 hover:bg-white/[0.09]"
                        >
                          Open output URL
                        </a>
                      ) : null}
                    </div>
                    {!hasHttpPptx && pptxPath ? (
                      <div className="mt-2 break-all font-mono text-xs text-gray-400">{pptxPath}</div>
                    ) : null}
                  </div>

                  <div className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-3">
                    <div className="mb-2 text-gray-400">Page Preview</div>
                    {preview?.preview_image_urls?.length ? (
                      <div className="grid grid-cols-2 gap-2">
                        {preview.preview_image_urls.slice(0, 8).map((url, idx) => (
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

                  <div className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-3">
                    <div className="mb-1 text-gray-400">Content/Structure Preview (excerpt)</div>
                    <pre className="max-h-44 overflow-auto whitespace-pre-wrap text-xs text-gray-300">
                      {preview?.source_excerpt || "No source excerpt available."}
                    </pre>
                  </div>

                  <div className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-3">
                    <div className="mb-1 text-gray-400">Template/Design Preview (excerpt)</div>
                    <pre className="max-h-44 overflow-auto whitespace-pre-wrap text-xs text-gray-300">
                      {preview?.design_excerpt || "No design spec excerpt available."}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="lg:col-span-1">
            <div className={panelClass}>
              <h2 className="mb-3 text-sm font-semibold">Operation Logs</h2>
              <div className="h-[780px] space-y-1 overflow-y-auto font-mono text-xs" data-testid="log-panel">
                {log.length === 0 ? (
                  <p className="text-gray-500">Waiting for actions...</p>
                ) : (
                  log.map((line, i) => (
                    <div key={i} className="text-gray-400">
                      {line}
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
