"use client";

import React, { useCallback, useEffect, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_AGENT_URL ||
  process.env.NEXT_PUBLIC_API_BASE ||
  "http://127.0.0.1:8124";

type Language = "zh-CN" | "en-US";
type DeckStyle = "professional" | "creative" | "academic" | "minimal";
type Phase = "idle" | "loading_templates" | "generating" | "done" | "error";

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
    "生成一份关于人工智能在制造业应用的演示文稿，包含行业背景、落地案例、ROI 对比与实施建议。",
  );
  const [language, setLanguage] = useState<Language>("zh-CN");
  const [style, setStyle] = useState<DeckStyle>("professional");
  const [totalPages, setTotalPages] = useState(10);
  const [colorScheme, setColorScheme] = useState("");
  const [includeImages, setIncludeImages] = useState(false);
  const [templateFamily, setTemplateFamily] = useState("auto");

  const [templates, setTemplates] = useState<TemplateItem[]>([]);
  const [result, setResult] = useState<AIPromptPptResult | null>(null);
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

  const isBusy = phase === "loading_templates" || phase === "generating";

  const addLog = useCallback((msg: string) => {
    setLog((prev) => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`]);
  }, []);

  const loadTemplates = useCallback(async (withLoadingState: boolean) => {
    if (withLoadingState) {
      setPhase("loading_templates");
    }
    setError(null);
    addLog("加载模板列表...");
    try {
      const data = await apiGet<TemplatesResponse>("/api/v1/ppt/templates");
      const templateRows = Array.isArray(data.templates) ? data.templates : [];
      setTemplates(templateRows);
      addLog(`模板加载完成: ${templateRows.length} 个`);
      if (withLoadingState) {
        setPhase("idle");
      }
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unknown error";
      setError(message);
      setPhase("error");
      addLog(`模板加载失败: ${message}`);
    }
  }, [addLog]);

  useEffect(() => {
    const run = async () => {
      await loadTemplates(false);
    };
    void run();
  }, [loadTemplates]);

  const handleGenerate = useCallback(async () => {
    setPhase("generating");
    setError(null);
    setResult(null);
    addLog(`开始生成 PPT（${totalPages} 页, style=${style}, template=${templateFamily}）...`);

    try {
      const data = await apiPost<AIPromptPptResult>("/api/v1/ppt/generate-from-prompt", {
        prompt,
        total_pages: totalPages,
        style,
        color_scheme: colorScheme.trim() || null,
        language,
        include_images: includeImages,
        template_family: templateFamily === "auto" ? null : templateFamily,
      });
      setResult(data);
      setPhase("done");
      addLog(
        `生成完成: slides=${data.total_slides}, time=${data.generation_time_seconds.toFixed(1)}s`,
      );
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unknown error";
      setError(message);
      setPhase("error");
      addLog(`生成失败: ${message}`);
    }
  }, [addLog, colorScheme, includeImages, language, prompt, style, templateFamily, totalPages]);

  const pptxPath = String(result?.output_pptx || "").trim();
  const hasHttpPptx = pptxPath.startsWith("http://") || pptxPath.startsWith("https://");

  return (
    <div className="min-h-screen bg-[#050508] text-gray-100">
      <div className="mx-auto max-w-6xl p-6">
        <div className="mb-6">
          <h1 className="text-2xl font-bold tracking-tight" data-testid="ppt-page-title">
            <span className="bg-gradient-to-r from-white to-gray-300 bg-clip-text text-transparent">
              Prompt to PPT Studio
            </span>
          </h1>
          <p className="mt-1 text-sm text-gray-500">主流程：Prompt 直出 PPT（ppt-master）</p>
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
              <h2 className="mb-3 text-sm font-semibold">Prompt 输入</h2>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={6}
                placeholder="描述你想要的 PPT 内容..."
                className={`${inputClass} resize-none`}
                disabled={isBusy}
              />

              <div className="mt-3 grid grid-cols-2 gap-2">
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value as Language)}
                  className={selectClass}
                  disabled={isBusy}
                >
                  <option value="zh-CN">中文</option>
                  <option value="en-US">English</option>
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
                  placeholder="color_scheme (可选)"
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
                  <option value="auto">auto (不指定模板)</option>
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
                  图片
                </label>
              </div>

              <button
                onClick={handleGenerate}
                disabled={isBusy || !prompt.trim()}
                className={`mt-3 ${primaryBtnClass}`}
                data-testid="btn-generate-from-prompt"
              >
                生成 PPT
              </button>
              <button
                onClick={() => void loadTemplates(true)}
                disabled={isBusy}
                className={`mt-2 ${softBtnClass}`}
                data-testid="btn-refresh-templates"
              >
                刷新模板列表
              </button>
            </div>

            <div className={panelClass}>
              <h2 className="mb-3 text-sm font-semibold">模板列表</h2>
              <div className="max-h-80 space-y-2 overflow-y-auto text-xs">
                {templates.length === 0 ? (
                  <p className="text-gray-500">暂无模板数据</p>
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
            <div className={`${panelClass} min-h-[520px]`}>
              <h2 className="mb-3 text-sm font-semibold">生成结果</h2>
              {!result ? (
                <p className="py-20 text-center text-sm text-gray-500">完成生成后在这里显示结果。</p>
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
                      <div className="text-gray-400">耗时</div>
                      <div className="mt-1 text-lg font-semibold text-gray-100">
                        {result.generation_time_seconds.toFixed(1)}s
                      </div>
                    </div>
                  </div>

                  <div className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-3">
                    <div className="text-gray-400">PPTX 输出</div>
                    {pptxPath ? (
                      hasHttpPptx ? (
                        <a href={pptxPath} target="_blank" rel="noreferrer" className="mt-1 block text-[#E11D48] hover:underline">
                          打开下载链接
                        </a>
                      ) : (
                        <div className="mt-1 break-all font-mono text-xs text-gray-200">{pptxPath}</div>
                      )
                    ) : (
                      <div className="mt-1 text-xs text-gray-500">未返回可下载 URL，已返回本地产物路径。</div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="lg:col-span-1">
            <div className={panelClass}>
              <h2 className="mb-3 text-sm font-semibold">Operation Logs</h2>
              <div className="h-[520px] space-y-1 overflow-y-auto font-mono text-xs" data-testid="log-panel">
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
