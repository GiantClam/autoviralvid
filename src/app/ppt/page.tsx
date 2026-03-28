"use client";
/* eslint-disable @next/next/no-img-element */

import React, { useCallback, useState } from "react";
import type { PresentationOutline, SlideContent } from "@/lib/types/ppt";

const API_BASE =
  process.env.NEXT_PUBLIC_AGENT_URL ||
  process.env.NEXT_PUBLIC_API_BASE ||
  "http://127.0.0.1:8124";

type Language = "zh-CN" | "en-US";
type DeckStyle = "professional" | "education" | "creative";
type MinimaxStyleVariant = "auto" | "sharp" | "soft" | "rounded" | "pill";
type RemotionRenderableSlide = SlideContent | Record<string, unknown>;

type ExportPptxResponse = {
  url: string;
  skill?: string;
  video_mode?: string;
  video_slide_count?: number;
  video_slides?: Record<string, unknown>[];
  generator_meta?: Record<string, unknown>;
};

const MINIMAX_PALETTES = [
  { key: "auto", label: "Auto" },
  { key: "modern_wellness", label: "Modern & Wellness" },
  { key: "business_authority", label: "Business & Authority" },
  { key: "nature_outdoors", label: "Nature & Outdoors" },
  { key: "vintage_academic", label: "Vintage & Academic" },
  { key: "soft_creative", label: "Soft & Creative" },
  { key: "bohemian", label: "Bohemian" },
  { key: "vibrant_tech", label: "Vibrant & Tech" },
  { key: "craft_artisan", label: "Craft & Artisan" },
  { key: "tech_night", label: "Tech & Night" },
  { key: "education_charts", label: "Education & Charts" },
  { key: "forest_eco", label: "Forest & Eco" },
  { key: "elegant_fashion", label: "Elegant & Fashion" },
  { key: "art_food", label: "Art & Food" },
  { key: "luxury_mysterious", label: "Luxury & Mysterious" },
  { key: "pure_tech_blue", label: "Pure Tech Blue" },
  { key: "coastal_coral", label: "Coastal Coral" },
  { key: "vibrant_orange_mint", label: "Vibrant Orange Mint" },
  { key: "platinum_white_gold", label: "Platinum White Gold" },
];

type Phase =
  | "idle"
  | "generating_outline"
  | "editing_outline"
  | "generating_content"
  | "preview"
  | "exporting"
  | "parsing"
  | "enhancing"
  | "rendering"
  | "done"
  | "error";

type ApiEnvelope<T> = {
  success: boolean;
  data?: T;
  error?: string | Record<string, unknown>;
};

async function apiPost<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const json = (await res.json()) as ApiEnvelope<T>;
  if (!json.success) {
    const dataObj = (json.data && typeof json.data === "object")
      ? (json.data as Record<string, unknown>)
      : null;
    const failure = (dataObj?.failure && typeof dataObj.failure === "object")
      ? (dataObj.failure as Record<string, unknown>)
      : null;
    if (failure) {
      const code = String(failure.failure_code || "unknown");
      const detail = String(failure.failure_detail || failure.message || "").trim();
      const attempts = failure.max_attempts ? ` (max_attempts=${failure.max_attempts})` : "";
      throw new Error(`Export failed [${code}]${attempts}${detail ? `: ${detail}` : ""}`);
    }

    if (typeof json.error === "string" && json.error.trim().startsWith("{")) {
      try {
        const parsed = JSON.parse(json.error) as Record<string, unknown>;
        const code = String(parsed.failure_code || "unknown");
        const detail = String(parsed.failure_detail || parsed.message || "").trim();
        throw new Error(`Export failed [${code}]${detail ? `: ${detail}` : ""}`);
      } catch {
        // Ignore parse failures and use fallback below.
      }
    }

    if (typeof json.error === "string") {
      throw new Error(json.error || "API error");
    }
    throw new Error("API error");
  }
  if (json.data === undefined) {
    throw new Error("API returned success without data");
  }
  return json.data;
}

export default function PPTTestPage() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [requirement, setRequirement] = useState(
    "做一个Python入门PPT，包含变量、函数、类三个核心概念，适合初学者。",
  );
  const [language, setLanguage] = useState<Language>("zh-CN");
  const [numSlides, setNumSlides] = useState(5);
  const [style, setStyle] = useState<DeckStyle>("education");

  const [outline, setOutline] = useState<PresentationOutline | null>(null);
  const [slides, setSlides] = useState<SlideContent[]>([]);
  const [currentSlideIdx, setCurrentSlideIdx] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [exportUrl, setExportUrl] = useState<string | null>(null);
  const [renderJobId, setRenderJobId] = useState<string | null>(null);
  const [minimaxStyleVariant, setMinimaxStyleVariant] = useState<MinimaxStyleVariant>("auto");
  const [minimaxPaletteKey, setMinimaxPaletteKey] = useState<string>("auto");
  const [videoSlidesOverride, setVideoSlidesOverride] = useState<Record<string, unknown>[] | null>(null);

  const [fileUrl, setFileUrl] = useState("");
  const [fileType, setFileType] = useState<"pptx" | "pdf">("pptx");

  const addLog = useCallback((msg: string) => {
    setLog((prev) => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`]);
  }, []);

  const handleGenerateOutline = useCallback(async () => {
    setPhase("generating_outline");
    setError(null);
    addLog("开始生成大纲...");

    try {
      const data = await apiPost<PresentationOutline>("/api/v1/ppt/outline", {
        requirement,
        language,
        num_slides: numSlides,
        style,
        purpose: "教育培训",
      });
      setOutline(data);
      setPhase("editing_outline");
      addLog(`大纲生成完成: ${data.slides.length} 页`);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unknown error";
      setError(message);
      setPhase("error");
      addLog(`大纲生成失败: ${message}`);
    }
  }, [addLog, language, numSlides, requirement, style]);

  const handleGenerateContent = useCallback(async () => {
    if (!outline) return;

    setPhase("generating_content");
    setError(null);
    addLog("开始生成内容...");

    try {
      const data = await apiPost<SlideContent[]>("/api/v1/ppt/content", {
        outline,
        language,
      });
      setSlides(data);
      setVideoSlidesOverride(null);
      setCurrentSlideIdx(0);
      setPhase("preview");
      addLog(`内容生成完成: ${data.length} 页`);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unknown error";
      setError(message);
      setPhase("error");
      addLog(`内容生成失败: ${message}`);
    }
  }, [addLog, language, outline]);

  const handleExportPPTX = useCallback(async () => {
    if (slides.length === 0) return;

    setPhase("exporting");
    setError(null);
    addLog(
      `开始导出PPTX... skill=minimax_pptx_generator, style=${minimaxStyleVariant}, palette=${minimaxPaletteKey}`,
    );

    try {
      const data = await apiPost<ExportPptxResponse>("/api/v1/ppt/export", {
        slides,
        title: outline?.title || "PPT",
        author: "AutoViralVid",
        pptx_skill: "minimax_pptx_generator",
        minimax_style_variant: minimaxStyleVariant,
        minimax_palette_key: minimaxPaletteKey,
        verbatim_content: false,
        original_style: true,
        disable_local_style_rewrite: true,
      });
      setExportUrl(data.url);
      if (Array.isArray(data.video_slides) && data.video_slides.length > 0) {
        setVideoSlidesOverride(data.video_slides);
        addLog(
          `导出附带统一视频源: ${data.video_slides.length} 页 (${data.video_mode || "unknown"})`,
        );
      } else {
        setVideoSlidesOverride(null);
      }
      setPhase("preview");
      addLog(`PPTX导出完成 (minimax_pptx_generator): ${data.url}`);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unknown error";
      setError(message);
      setPhase("error");
      addLog(`PPTX导出失败: ${message}`);
    }
  }, [addLog, minimaxPaletteKey, minimaxStyleVariant, outline, slides]);

  const handleEnhance = useCallback(async () => {
    if (slides.length === 0) return;

    setPhase("enhancing");
    setError(null);
    addLog("开始增强讲解并生成TTS...");

    try {
      const data = await apiPost<SlideContent[]>("/api/v1/ppt/enhance", {
        slides,
        language,
        enhance_narration: true,
        generate_tts: true,
        voice_style: "zh-CN-female",
      });
      setSlides(data);
      setVideoSlidesOverride(null);
      setPhase("preview");
      const ttsCount = data.filter((s) => s.narrationAudioUrl).length;
      addLog(`增强完成: ${ttsCount}/${data.length} 页生成TTS`);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unknown error";
      setError(message);
      setPhase("error");
      addLog(`增强失败: ${message}`);
    }
  }, [addLog, language, slides]);

  const handleRenderVideo = useCallback(async () => {
    if (slides.length === 0) return;

    setPhase("rendering");
    setError(null);
    const renderSlides: RemotionRenderableSlide[] =
      videoSlidesOverride && videoSlidesOverride.length > 0 ? videoSlidesOverride : slides;
    addLog(
      videoSlidesOverride && videoSlidesOverride.length > 0
        ? `开始渲染视频... 使用导出后的统一视频源 (${videoSlidesOverride.length} 页)`
        : "开始渲染视频... 使用当前编辑区 slides",
    );

    try {
      const data = await apiPost<{ id: string; status: string }>("/api/v1/ppt/render", {
        slides: renderSlides,
        config: {
          width: 1920,
          height: 1080,
          fps: 30,
          transition: "fade",
          include_narration: true,
        },
        idempotency_key: `ppt-${Date.now()}`,
      });
      setRenderJobId(data.id);
      setPhase("done");
      addLog(`渲染任务已创建: ${data.id} (${data.status})`);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unknown error";
      setError(message);
      setPhase("error");
      addLog(`渲染失败: ${message}`);
    }
  }, [addLog, slides, videoSlidesOverride]);

  const handleParseDocument = useCallback(async () => {
    if (!fileUrl.trim()) return;

    setPhase("parsing");
    setError(null);
    addLog(`开始解析 ${fileType.toUpperCase()} 文档...`);

    try {
      const data = await apiPost<{ slides: SlideContent[]; total_pages?: number }>("/api/v1/ppt/parse", {
        file_url: fileUrl,
        file_type: fileType,
      });
      setSlides(data.slides || []);
      setVideoSlidesOverride(null);
      setCurrentSlideIdx(0);
      setPhase("preview");
      addLog(`解析完成: ${data.total_pages || data.slides?.length || 0} 页`);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unknown error";
      setError(message);
      setPhase("error");
      addLog(`解析失败: ${message}`);
    }
  }, [addLog, fileType, fileUrl]);

  const isBusy = [
    "generating_outline",
    "generating_content",
    "exporting",
    "enhancing",
    "rendering",
    "parsing",
  ].includes(phase);

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

  return (
    <div className="min-h-screen bg-[#050508] text-gray-100">
      <div className="mx-auto max-w-6xl p-6">
        <div className="mb-6">
          <h1 className="text-2xl font-bold tracking-tight" data-testid="ppt-page-title">
            <span className="bg-gradient-to-r from-white to-gray-300 bg-clip-text text-transparent">
              PPT / Video Studio
            </span>
          </h1>
          <p className="mt-1 text-sm text-gray-500">UI aligned with main site visual style</p>
        </div>

        {error && (
          <div
            className="mb-4 rounded-xl border border-red-500/20 bg-red-500/[0.08] px-3 py-2 text-sm text-red-300"
            data-testid="error-banner"
          >
            {error}
          </div>
        )}

        <div
          className="mb-4 rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-sm text-gray-400"
          data-testid="phase-indicator"
        >
          Current phase: <strong className="text-gray-200">{phase}</strong>
          {isBusy && <span className="ml-2 animate-pulse text-[#E11D48]">processing...</span>}
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="flex flex-col gap-4 lg:col-span-1">
            <div className={panelClass}>
              <h2 className="mb-3 text-sm font-semibold">Generate PPT</h2>
              <textarea
                data-testid="requirement-input"
                value={requirement}
                onChange={(e) => setRequirement(e.target.value)}
                rows={3}
                placeholder="Describe your PPT requirement"
                className={`${inputClass} resize-none`}
                disabled={isBusy}
              />

              <div className="mt-2 grid grid-cols-[1fr_auto_1fr] gap-2">
                <select
                  data-testid="language-select"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value as Language)}
                  className={selectClass}
                  disabled={isBusy}
                >
                  <option value="zh-CN">中文</option>
                  <option value="en-US">English</option>
                </select>
                <input
                  data-testid="num-slides-input"
                  type="number"
                  value={numSlides}
                  onChange={(e) => setNumSlides(parseInt(e.target.value, 10) || 5)}
                  min={1}
                  max={50}
                  className={`w-16 ${selectClass}`}
                  disabled={isBusy}
                />
                <select
                  data-testid="style-select"
                  value={style}
                  onChange={(e) => setStyle(e.target.value as DeckStyle)}
                  className={selectClass}
                  disabled={isBusy}
                >
                  <option value="professional">Professional</option>
                  <option value="education">Education</option>
                  <option value="creative">Creative</option>
                </select>
              </div>

              <button
                data-testid="btn-generate-outline"
                onClick={handleGenerateOutline}
                disabled={isBusy || !requirement.trim()}
                className={`mt-3 ${primaryBtnClass}`}
              >
                Generate Outline
              </button>
            </div>

            {outline && phase === "editing_outline" && (
              <div className={panelClass}>
                <h2 className="mb-2 text-sm font-semibold">Outline Review</h2>
                <p className="mb-2 text-xs text-gray-500" data-testid="outline-summary">
                  {outline.title} · {outline.slides.length} slides · {Math.round(outline.totalDuration / 60)} min
                </p>
                <div className="mb-3 max-h-48 space-y-1 overflow-y-auto">
                  {outline.slides.map((s, i) => (
                    <div
                      key={s.id}
                      data-testid={`outline-slide-${i}`}
                      className="flex gap-2 rounded-lg border border-white/[0.06] bg-white/[0.03] p-2 text-xs"
                    >
                      <span className="w-5 shrink-0 text-gray-400">{String(i + 1).padStart(2, "0")}</span>
                      <div className="flex-1">
                        <div className="font-medium text-gray-200">{s.title}</div>
                        <div className="text-gray-500">{s.keyPoints?.join(", ")}</div>
                      </div>
                    </div>
                  ))}
                </div>
                <button
                  data-testid="btn-generate-content"
                  onClick={handleGenerateContent}
                  disabled={isBusy}
                  className={primaryBtnClass}
                >
                  Confirm & Generate Content
                </button>
              </div>
            )}

            <div className={panelClass}>
              <h2 className="mb-3 text-sm font-semibold">Parse Document (PPT/PDF)</h2>
              <input
                data-testid="file-url-input"
                value={fileUrl}
                onChange={(e) => setFileUrl(e.target.value)}
                placeholder="Input PPT/PDF URL"
                className={inputClass}
                disabled={isBusy}
              />
              <div className="mt-2 flex gap-2">
                <select
                  data-testid="file-type-select"
                  value={fileType}
                  onChange={(e) => setFileType(e.target.value as "pptx" | "pdf")}
                  className={selectClass}
                  disabled={isBusy}
                >
                  <option value="pptx">PPTX</option>
                  <option value="pdf">PDF</option>
                </select>
                <button
                  data-testid="btn-parse-document"
                  onClick={handleParseDocument}
                  disabled={isBusy || !fileUrl.trim()}
                  className="flex-1 rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-1.5 text-sm text-gray-200 transition hover:bg-white/[0.08] disabled:opacity-50"
                >
                  Parse
                </button>
              </div>
            </div>

            {slides.length > 0 && (
              <div className={panelClass}>
                <h2 className="mb-3 text-sm font-semibold">Actions</h2>
                <div className="mb-2">
                  <label className="mb-1 block text-xs text-gray-500">PPTX Skill</label>
                  <div
                    className="w-full rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-gray-200"
                    data-testid="pptx-skill-select"
                  >
                    minimax_pptx_generator
                  </div>
                </div>
                <div className="mb-2 grid grid-cols-2 gap-2">
                  <div>
                    <label className="mb-1 block text-xs text-gray-500">Minimax Style</label>
                    <select
                      value={minimaxStyleVariant}
                      onChange={(e) => setMinimaxStyleVariant(e.target.value as MinimaxStyleVariant)}
                      className={`w-full ${selectClass}`}
                      disabled={isBusy}
                      data-testid="minimax-style-select"
                    >
                      <option value="auto">auto</option>
                      <option value="sharp">sharp</option>
                      <option value="soft">soft</option>
                      <option value="rounded">rounded</option>
                      <option value="pill">pill</option>
                    </select>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs text-gray-500">Minimax Palette</label>
                    <select
                      value={minimaxPaletteKey}
                      onChange={(e) => setMinimaxPaletteKey(e.target.value)}
                      className={`w-full ${selectClass}`}
                      disabled={isBusy}
                      data-testid="minimax-palette-select"
                    >
                      {MINIMAX_PALETTES.map((p) => (
                        <option key={p.key} value={p.key}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="flex flex-col gap-2">
                  <button
                    data-testid="btn-export-pptx"
                    onClick={handleExportPPTX}
                    disabled={isBusy}
                    className={primaryBtnClass}
                  >
                    Export PPTX
                  </button>
                  <button
                    data-testid="btn-enhance"
                    onClick={handleEnhance}
                    disabled={isBusy}
                    className={softBtnClass}
                  >
                    Enhance + TTS
                  </button>
                  <button
                    data-testid="btn-render-video"
                    onClick={handleRenderVideo}
                    disabled={isBusy}
                    className="w-full rounded-xl border border-red-500/30 bg-red-500/[0.16] py-2 text-sm text-red-200 transition hover:bg-red-500/[0.24] disabled:opacity-50"
                  >
                    Render Video
                  </button>
                </div>

                {exportUrl && (
                  <a
                    href={exportUrl}
                    target="_blank"
                    rel="noreferrer"
                    data-testid="export-download-link"
                    className="mt-2 block text-xs text-[#E11D48] hover:underline"
                  >
                    Download PPTX
                  </a>
                )}
                {renderJobId && (
                  <p className="mt-2 text-xs text-gray-500" data-testid="render-job-id">
                    Render job: {renderJobId}
                  </p>
                )}
              </div>
            )}
          </div>

          <div className="lg:col-span-1">
            <div className={`${panelClass} min-h-[400px]`}>
              <h2 className="mb-3 text-sm font-semibold">PPT Preview</h2>
              {slides.length > 0 ? (
                <div data-testid="ppt-preview">
                  <div
                    className="relative w-full overflow-hidden rounded-xl border border-white/[0.08] bg-white"
                    style={{
                      paddingBottom: "56.25%",
                      backgroundColor: slides[currentSlideIdx]?.background?.color || "#fff",
                    }}
                  >
                    {slides[currentSlideIdx]?.title && (
                      <div
                        className="absolute left-[5%] right-[5%] top-[5%] font-bold text-gray-900"
                        style={{ fontSize: "clamp(10px, 2vw, 20px)" }}
                        data-testid="preview-slide-title"
                      >
                        {slides[currentSlideIdx].title}
                      </div>
                    )}

                    {slides[currentSlideIdx]?.elements?.map((el) => (
                      <div
                        key={el.id}
                        data-testid={`preview-element-${el.type}`}
                        className="absolute overflow-hidden"
                        style={{
                          left: `${(el.left / 1920) * 100}%`,
                          top: `${(el.top / 1080) * 100}%`,
                          width: `${(el.width / 1920) * 100}%`,
                          height: `${(el.height / 1080) * 100}%`,
                          fontSize: `${Math.max(6, ((el.style?.fontSize || 18) / 1920) * 100)}vw`,
                          fontFamily: el.style?.fontFamily || "sans-serif",
                          color: el.style?.color || "#333",
                          fontWeight: el.style?.bold ? "bold" : "normal",
                        }}
                      >
                        {el.type === "text" && (
                          <div
                            dangerouslySetInnerHTML={{
                              __html: (el.content || "")
                                .replace(/<script[\s\S]*?<\/script>/gi, "")
                                .replace(/on\w+=/gi, ""),
                            }}
                          />
                        )}
                        {el.type === "image" && el.src && (
                          <img src={el.src} className="h-full w-full object-cover" alt="" />
                        )}
                        {el.type === "chart" && (
                          <div className="flex h-full items-center justify-center text-xs text-gray-500">
                            Chart
                          </div>
                        )}
                        {el.type === "table" && (
                          <div className="flex h-full items-center justify-center text-xs text-gray-500">
                            Table
                          </div>
                        )}
                      </div>
                    ))}

                    <div className="absolute bottom-2 right-3 text-xs text-gray-500">
                      {currentSlideIdx + 1}/{slides.length}
                    </div>
                  </div>

                  <div className="mt-2 flex items-center justify-between">
                    <button
                      data-testid="btn-prev-slide"
                      onClick={() => setCurrentSlideIdx(Math.max(0, currentSlideIdx - 1))}
                      disabled={currentSlideIdx === 0}
                      className="rounded-lg border border-white/[0.1] bg-white/[0.03] px-3 py-1 text-xs text-gray-200 hover:bg-white/[0.08] disabled:opacity-30"
                    >
                      Prev
                    </button>
                    <span className="text-xs text-gray-500" data-testid="slide-counter">
                      {currentSlideIdx + 1} / {slides.length}
                    </span>
                    <button
                      data-testid="btn-next-slide"
                      onClick={() => setCurrentSlideIdx(Math.min(slides.length - 1, currentSlideIdx + 1))}
                      disabled={currentSlideIdx === slides.length - 1}
                      className="rounded-lg border border-white/[0.1] bg-white/[0.03] px-3 py-1 text-xs text-gray-200 hover:bg-white/[0.08] disabled:opacity-30"
                    >
                      Next
                    </button>
                  </div>

                  <div className="mt-3 flex gap-1 overflow-x-auto" data-testid="thumbnail-strip">
                    {slides.map((s, i) => (
                      <button
                        key={s.id}
                        data-testid={`thumbnail-${i}`}
                        onClick={() => setCurrentSlideIdx(i)}
                        className={`h-6 w-10 shrink-0 rounded border text-[8px] font-mono ${
                          i === currentSlideIdx
                            ? "border-[#E11D48]/60 bg-[#E11D48]/15 text-[#E11D48]"
                            : "border-white/[0.12] bg-white/[0.03] text-gray-300"
                        }`}
                      >
                        {i + 1}
                      </button>
                    ))}
                  </div>

                  {slides[currentSlideIdx]?.narration && (
                    <div className="mt-3 rounded-lg border border-white/[0.08] bg-white/[0.03] p-2">
                      <div className="mb-1 text-[10px] font-medium text-gray-500">Narration</div>
                      <p className="text-xs text-gray-300" data-testid="narration-text">
                        {slides[currentSlideIdx].narration}
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                <p className="py-20 text-center text-sm text-gray-500">Preview will appear here after generation.</p>
              )}
            </div>
          </div>

          <div className="lg:col-span-1">
            <div className={panelClass}>
              <h2 className="mb-3 text-sm font-semibold">Operation Logs</h2>
              <div className="h-[500px] space-y-1 overflow-y-auto font-mono text-xs" data-testid="log-panel">
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


