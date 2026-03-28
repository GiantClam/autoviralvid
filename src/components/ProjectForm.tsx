"use client";

import React, { useState, useCallback, useEffect, useRef } from "react";
import { useProject } from "@/contexts/ProjectContext";
import { useT } from "@/lib/i18n";
import type { TranslationKey } from "@/lib/i18n/context";
import {
  Clapperboard,
  Sparkles,
  ImagePlus,
  Palette,
  Clock,
  Monitor,
  Play,
  ChevronDown,
  Loader2,
  Music,
  Mic2,
  PersonStanding,
  Type,
  Upload,
  CheckCircle2,
  X,
} from "lucide-react";

// 鈹€鈹€ Upload limits & allowed types 鈹€鈹€

const UPLOAD_LIMITS = {
  image: {
    maxSizeMB: 20,
    allowedTypes: ["image/png", "image/jpeg", "image/jpg", "image/webp"],
    labelKey: "form.imageFileLabel" as const,
  },
  audio: {
    maxSizeMB: 500,
    allowedTypes: [
      "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav",
      "audio/ogg", "audio/aac", "audio/m4a", "audio/x-m4a",
    ],
    labelKey: "form.audioFileLabel" as const,
  },
} as const;

function validateUploadFile(file: File, kind: keyof typeof UPLOAD_LIMITS, label: string) {
  const limit = UPLOAD_LIMITS[kind];
  const maxBytes = limit.maxSizeMB * 1024 * 1024;

  if (file.size > maxBytes) {
    throw new Error(`${label} ${limit.maxSizeMB}MB (${(file.size / 1024 / 1024).toFixed(1)}MB)`);
  }

  // Allow empty type (some browsers don't set it) but reject known-bad types
  if (file.type && !(limit.allowedTypes as readonly string[]).includes(file.type)) {
    throw new Error(
      `${label}: "${file.type}" - ${limit.allowedTypes.join(", ")}`,
    );
  }
}

// 鈹€鈹€ File upload helper 鈹€鈹€

async function uploadFileToR2(
  file: File,
  onProgress?: (pct: number) => void,
): Promise<string> {
  // 1. Get presigned URL from backend
  const presignRes = await fetch("/api/upload/presign", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename: file.name,
      content_type: file.type || "application/octet-stream",
    }),
  });
  if (!presignRes.ok) {
    throw new Error(`鑾峰彇涓婁紶閾炬帴澶辫触: ${presignRes.status}`);
  }
  const { upload_url, public_url } = await presignRes.json();

  // 2. Upload file directly to R2 via presigned PUT
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", upload_url);
    xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
      };
    }
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`涓婁紶澶辫触: ${xhr.status}`)));
    xhr.onerror = () => reject(new Error("涓婁紶缃戠粶閿欒"));
    xhr.send(file);
  });

  return public_url;
}

type V7GenerateResponse = {
  title: string;
  design_system: string;
  slides: Array<Record<string, unknown>>;
};

export type V7ExportResponse = {
  run_id: string;
  pptx_url: string;
  slide_image_urls: string[];
  slide_count: number;
  skill?: string;
  video_mode?: string;
  video_slide_count?: number;
  video_slides?: Array<Record<string, unknown>>;
  generator_meta?: Record<string, unknown>;
};

export type PptV7Step = "idle" | "generating" | "tts" | "exporting" | "done";

export interface PptV7PanelState {
  enabled: boolean;
  busy: boolean;
  step: PptV7Step;
  error: string;
  result: V7ExportResponse | null;
  requirement: string;
  slideCount: number;
}

async function callV7Api<T>(path: "generate" | "tts" | "export", body: Record<string, unknown>): Promise<T> {
  const res = await fetch(`/api/projects/v7/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const raw = await res.text();
  let json: {
    success?: boolean;
    data?: T;
    error?: string;
    detail?: string;
  } | null = null;
  try {
    json = raw ? JSON.parse(raw) : null;
  } catch {
    throw new Error(`V7 鎺ュ彛杩斿洖闈?JSON: ${raw.slice(0, 200)}`);
  }

  if (!res.ok) {
    throw new Error(json?.error || json?.detail || `V7 鎺ュ彛澶辫触: ${res.status}`);
  }
  if (!json?.success) {
    throw new Error(json?.error || "V7 鎺ュ彛杩斿洖澶辫触");
  }
  return json.data as T;
}

// 鈹€鈹€ Template options (keys for i18n) 鈹€鈹€

type TemplateOption = {
  id: string;
  labelKey?: TranslationKey;
  label?: string;
};

const TEMPLATE_IDS: ReadonlyArray<TemplateOption> = [
  { id: "product-ad", labelKey: "gallery.tplProductAd" },
  { id: "beauty-review", labelKey: "gallery.tplBeautyReview" },
  { id: "fashion-style", labelKey: "gallery.tplFashionStyle" },
  { id: "food-showcase", labelKey: "gallery.tplFoodShowcase" },
  { id: "tech-unbox", labelKey: "gallery.tplTechUnbox" },
  { id: "home-living", labelKey: "gallery.tplHomeLiving" },
  { id: "brand-story", labelKey: "gallery.tplBrandStory" },
  { id: "digital-human", labelKey: "gallery.tplDigitalHuman" },
  { id: "knowledge-edu", labelKey: "gallery.tplKnowledgeEdu" },
  { id: "funny-skit", labelKey: "gallery.tplFunnySkit" },
  { id: "travel-vlog", labelKey: "gallery.tplTravelVlog" },
  { id: "ppt-v7", label: "PPT & Video V7" },
];

const STYLE_KEYS = [
  { value: "modern-minimal", labelKey: "form.styleModernMinimal" },
  { value: "chinese", labelKey: "form.styleChinese" },
  { value: "japanese", labelKey: "form.styleJapanese" },
  { value: "western", labelKey: "form.styleWestern" },
  { value: "cyberpunk", labelKey: "form.styleCyberpunk" },
  { value: "retro", labelKey: "form.styleRetro" },
  { value: "premium", labelKey: "form.stylePremium" },
  { value: "natural", labelKey: "form.styleNatural" },
] as const satisfies ReadonlyArray<{ value: string; labelKey: TranslationKey }>;

const ORIENTATION_KEYS = [
  { value: "vertical", labelKey: "form.vertical", ratio: "9:16" },
  { value: "horizontal", labelKey: "form.horizontal", ratio: "16:9" },
  { value: "square", labelKey: "form.square", ratio: "1:1" },
] as const satisfies ReadonlyArray<{ value: string; labelKey: TranslationKey; ratio: string }>;

// 鈹€鈹€ Props 鈹€鈹€

interface ProjectFormProps {
  onTemplateChange?: (templateId: string) => void;
  initialTemplateId?: string;
  onPptV7StateChange?: (state: PptV7PanelState) => void;
  pptV7RetryToken?: number;
}

// 鈹€鈹€ Component 鈹€鈹€

export default function ProjectForm({ onTemplateChange, initialTemplateId, onPptV7StateChange, pptV7RetryToken }: ProjectFormProps) {
  const t = useT();
  const { createProject, generateStoryboard, submitDigitalHuman, isLoading, phase, error, project } =
    useProject();

  const [templateId, setTemplateId] = useState<string>(initialTemplateId || TEMPLATE_IDS[0].id);
  const [theme, setTheme] = useState("");
  const [productImageUrl, setProductImageUrl] = useState("");
  const [style, setStyle] = useState<string>(STYLE_KEYS[0].value);
  const [duration, setDuration] = useState(30);
  const [orientation, setOrientation] = useState<string>("vertical");

  const [audioUrl, setAudioUrl] = useState("");
  const [voiceMode, setVoiceMode] = useState(0);
  const [voiceText, setVoiceText] = useState("");
  const [motionPrompt, setMotionPrompt] = useState("妯＄壒姝ｅ湪鍋氫骇鍝佸睍绀猴紝杩涜鐢靛晢鐩存挱甯﹁揣");

  // File upload state
  const [imageUploading, setImageUploading] = useState(false);
  const [imageUploadPct, setImageUploadPct] = useState(0);
  const [imageFileName, setImageFileName] = useState("");
  const [audioUploading, setAudioUploading] = useState(false);
  const [audioUploadPct, setAudioUploadPct] = useState(0);
  const [audioFileName, setAudioFileName] = useState("");
  const [pptSlideCount, setPptSlideCount] = useState(10);
  const [pptV7Busy, setPptV7Busy] = useState(false);
  const [pptV7Step, setPptV7Step] = useState<PptV7Step>("idle");
  const [pptV7Error, setPptV7Error] = useState<string>("");
  const [pptV7Result, setPptV7Result] = useState<V7ExportResponse | null>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const audioInputRef = useRef<HTMLInputElement>(null);
  const lastRetryTokenRef = useRef<number>(pptV7RetryToken ?? 0);

  const isDigitalHuman = templateId === "digital-human";
  const isPptV7 = templateId === "ppt-v7";
  const aspectRatio = ORIENTATION_KEYS.find((o) => o.value === orientation)?.ratio ?? "9:16";

  useEffect(() => {
    onPptV7StateChange?.({
      enabled: isPptV7,
      busy: pptV7Busy,
      step: pptV7Step,
      error: pptV7Error,
      result: pptV7Result,
      requirement: theme.trim(),
      slideCount: pptSlideCount,
    });
  }, [isPptV7, onPptV7StateChange, pptSlideCount, pptV7Busy, pptV7Error, pptV7Result, pptV7Step, theme]);

  useEffect(() => {
    if (!project?.run_id) {
      return;
    }

    if (typeof project.template_id === "string" && project.template_id) {
      setTemplateId(project.template_id);
      onTemplateChange?.(project.template_id);
    }
    setTheme(typeof project.theme === "string" ? project.theme : "");
    setProductImageUrl(typeof project.product_image_url === "string" ? project.product_image_url : "");
    setStyle(typeof project.style === "string" && project.style ? project.style : STYLE_KEYS[0].value);
    setDuration(typeof project.duration === "number" ? project.duration : 30);
    setOrientation(
      typeof project.orientation === "string" && ["vertical", "horizontal", "square"].includes(project.orientation)
        ? project.orientation
        : "vertical",
    );
    setAudioUrl(typeof project.audio_url === "string" ? project.audio_url : "");
    setVoiceMode(typeof project.voice_mode === "number" ? project.voice_mode : 0);
    setVoiceText(typeof project.voice_text === "string" ? project.voice_text : "");
    setMotionPrompt(
      typeof project.motion_prompt === "string" && project.motion_prompt
        ? project.motion_prompt
        : "妯＄壒姝ｅ湪鍋氫骇鍝佸睍绀猴紝杩涜鐢靛晢鐩存挱甯﹁揣",
    );
    setImageFileName("");
    setAudioFileName("");
  }, [onTemplateChange, project]);

  // 鈹€鈹€ File upload handlers 鈹€鈹€
  const handleImageFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      validateUploadFile(file, "image", t("form.imageFileLabel"));
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
      if (imageInputRef.current) imageInputRef.current.value = "";
      return;
    }
    setImageUploading(true);
    setImageUploadPct(0);
    setImageFileName(file.name);
    try {
      const url = await uploadFileToR2(file, setImageUploadPct);
      setProductImageUrl(url);
    } catch (err) {
      alert(`${t("form.imageUploadFailed")}: ${err instanceof Error ? err.message : err}`);
      setImageFileName("");
    } finally {
      setImageUploading(false);
      if (imageInputRef.current) imageInputRef.current.value = "";
    }
  }, [t]);

  const handleAudioFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      validateUploadFile(file, "audio", t("form.audioFileLabel"));
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
      if (audioInputRef.current) audioInputRef.current.value = "";
      return;
    }
    setAudioUploading(true);
    setAudioUploadPct(0);
    setAudioFileName(file.name);
    try {
      const url = await uploadFileToR2(file, setAudioUploadPct);
      setAudioUrl(url);
    } catch (err) {
      alert(`${t("form.audioUploadFailed")}: ${err instanceof Error ? err.message : err}`);
      setAudioFileName("");
    } finally {
      setAudioUploading(false);
      if (audioInputRef.current) audioInputRef.current.value = "";
    }
  }, [t]);

  const handleTemplateChange = useCallback(
    (id: string) => {
      setTemplateId(id);
      if (id !== "ppt-v7") {
        setPptV7Error("");
        setPptV7Result(null);
        setPptV7Step("idle");
      }
      onTemplateChange?.(id);
    },
    [onTemplateChange],
  );

  const runPptV7 = useCallback(async () => {
    const requirement = theme.trim();
    if (!requirement) return;

    setPptV7Busy(true);
    setPptV7Error("");
    setPptV7Result(null);

    try {
      setPptV7Step("generating");
      const generated = await callV7Api<V7GenerateResponse>("generate", {
        requirement,
        num_slides: Math.max(3, Math.min(30, pptSlideCount)),
        language: "zh-CN",
      });

      setPptV7Step("tts");
      const ttsData = await callV7Api<{ slides: Array<Record<string, unknown>> }>("tts", {
        slides: generated.slides,
        voice_style: "zh-CN-female",
      });

      setPptV7Step("exporting");
      const exported = await callV7Api<V7ExportResponse>("export", {
        slides: ttsData.slides,
      });

      setPptV7Result(exported);
      setPptV7Step("done");
    } catch (err) {
      setPptV7Error(err instanceof Error ? err.message : "V7 鐢熸垚澶辫触");
      setPptV7Step("idle");
    } finally {
      setPptV7Busy(false);
    }
  }, [theme, pptSlideCount]);

  useEffect(() => {
    const token = pptV7RetryToken ?? 0;
    if (token === 0 || token === lastRetryTokenRef.current) {
      return;
    }
    lastRetryTokenRef.current = token;
    if (!isPptV7 || pptV7Busy || !theme.trim()) {
      return;
    }
    void runPptV7();
  }, [isPptV7, pptV7Busy, pptV7RetryToken, runPptV7, theme]);

  const handleSubmit = useCallback(async () => {
    if (!theme.trim()) return;
    if (isPptV7) {
      await runPptV7();
      return;
    }

    const params: Record<string, unknown> = {
      template_id: templateId,
      theme: theme.trim(),
      product_image_url: productImageUrl.trim() || undefined,
      style,
      duration,
      orientation,
      aspect_ratio: aspectRatio,
    };

    if (isDigitalHuman) {
      if (!productImageUrl.trim()) {
        alert(t("form.needImageUrl"));
        return;
      }
      if (!audioUrl.trim()) {
        alert(t("form.needAudioUrl"));
        return;
      }
      params.audio_url = audioUrl.trim();
      params.voice_mode = voiceMode;
      if (voiceMode === 1 && voiceText.trim()) {
        params.voice_text = voiceText.trim();
      }
      if (motionPrompt.trim()) {
        params.motion_prompt = motionPrompt.trim();
      }
    }

    await createProject(params as Parameters<typeof createProject>[0]);

    if (isDigitalHuman) {
      await submitDigitalHuman();
    } else {
      await generateStoryboard();
    }
  }, [
    createProject,
    generateStoryboard,
    submitDigitalHuman,
    templateId,
    theme,
    productImageUrl,
    style,
    duration,
    orientation,
    aspectRatio,
    isDigitalHuman,
    isPptV7,
    runPptV7,
    audioUrl,
    voiceMode,
    voiceText,
    motionPrompt,
    t,
  ]);

  const busy = isLoading || phase === "generating_storyboard" || pptV7Busy;

  // 鈹€鈹€ Shared input class 鈹€鈹€
  const inp =
    "w-full rounded-xl bg-white/[0.03] border border-white/[0.06] text-gray-200 text-[13px] " +
    "px-3.5 py-2.5 outline-none transition-all duration-300 placeholder:text-gray-600 " +
    "focus:border-[#E11D48]/50 focus:ring-2 focus:ring-[#E11D48]/10 focus:bg-white/[0.05] " +
    "hover:border-white/[0.12] hover:bg-white/[0.04]";

  // 鈹€鈹€ Label 鈹€鈹€
  const Label = ({ icon: Icon, children }: { icon: React.ElementType; children: React.ReactNode }) => (
    <div className="flex items-center gap-2 mb-2">
      <div className="w-5 h-5 rounded-md bg-gradient-to-br from-[#E11D48]/20 to-purple-500/10 flex items-center justify-center">
        <Icon className="w-3 h-3 text-[#E11D48]" />
      </div>
      <span className="text-xs font-semibold text-gray-300">{children}</span>
    </div>
  );

  const Divider = () => <div className="border-t border-white/[0.04] my-4" />;

  return (
    <aside className="flex flex-col h-full w-full md:max-w-[400px] bg-[#0a0a12]/80 backdrop-blur-xl">
      {/* 鈹€鈹€ Header 鈹€鈹€ */}
      <div className="flex items-center gap-3 px-5 py-4 border-b border-white/[0.06] bg-gradient-to-r from-[#E11D48]/5 to-transparent">
        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#E11D48] to-[#9333EA] flex items-center justify-center shadow-lg shadow-[#E11D48]/20">
          <Clapperboard className="w-4 h-4 text-white" />
        </div>
        <div className="flex-1">
          <h2 className="text-sm font-bold text-white tracking-tight">{isPptV7 ? "PPT V7 閰嶇疆" : t("form.videoConfig")}</h2>
          <span className="text-[10px] text-gray-500">
            {isPptV7 ? "鍙?Agent + MiniMax + Remotion" : isDigitalHuman ? t("form.digitalHumanMode") : t("form.aiGenMode")}
          </span>
        </div>
      </div>

      {/* 鈹€鈹€ Scrollable form 鈹€鈹€ */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">

        {/* 鈹€鈹€ Template + Theme 鈹€鈹€ */}
        <section>
          <Label icon={Clapperboard}>{t("form.template")}</Label>
          <div className="relative">
              <select
                value={templateId}
                onChange={(e) => handleTemplateChange(e.target.value)}
                className={inp + " appearance-none pr-8 cursor-pointer"}
              >
                {TEMPLATE_IDS.map((tpl) => (
                  <option key={tpl.id} value={tpl.id}>
                    {tpl.labelKey ? t(tpl.labelKey) : tpl.label || tpl.id}
                  </option>
                ))}
              </select>
            <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500" />
          </div>
        </section>

        <section>
          <Label icon={Sparkles}>{t("form.themeDesc")}</Label>
          <textarea
            value={theme}
            onChange={(e) => setTheme(e.target.value)}
            placeholder={t("form.themePlaceholder")}
            rows={2}
            className={inp + " resize-none leading-relaxed"}
          />
        </section>

        {isPptV7 && (
          <section className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-3 space-y-3">
            <div className="text-xs font-semibold text-gray-300">PPT V7 鍙傛暟</div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="text-[11px] text-gray-500 mb-1">椤垫暟</div>
                <input
                  type="number"
                  min={3}
                  max={30}
                  value={pptSlideCount}
                  onChange={(e) => setPptSlideCount(Math.max(3, Math.min(30, Number(e.target.value) || 10)))}
                  className={inp}
                />
              </div>
              <div>
                <div className="text-[11px] text-gray-500 mb-1">流程</div>
                <div className="h-[42px] rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 flex items-center text-xs text-gray-400">
                  {pptV7Step === "idle" && "等待开始"}
                  {pptV7Step === "generating" && "生成内容中..."}
                  {pptV7Step === "tts" && "合成旁白中..."}
                  {pptV7Step === "exporting" && "导出 PPTX 中..."}
                  {pptV7Step === "done" && "已完成"}
                </div>
              </div>
            </div>
            {pptV7Error && (
              <div className="rounded-lg bg-red-500/[0.08] border border-red-500/20 px-3 py-2 text-xs text-red-400">
                {pptV7Error}
              </div>
            )}
            {pptV7Result && (
              <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/[0.08] p-3 space-y-2">
                <div className="text-xs text-emerald-300">
                  完成：{pptV7Result.slide_count} 页
                </div>
                <a
                  href={pptV7Result.pptx_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 text-xs font-semibold text-emerald-300 hover:text-emerald-200"
                >
                  下载 PPTX
                </a>
              </div>
            )}
          </section>
        )}

        <Divider />

        {!isPptV7 && (
          <>
        {/* 鈹€鈹€ Assets 鈹€鈹€ */}
        <section>
          <Label icon={ImagePlus}>{isDigitalHuman ? t("form.imageDigitalHumanLabel") : t("form.imageLabel")}</Label>
          {/* Hidden file input */}
          <input
            ref={imageInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={handleImageFileChange}
          />
          <div className="flex gap-2">
            <input
              type="text"
              value={productImageUrl}
              onChange={(e) => { setProductImageUrl(e.target.value); setImageFileName(""); }}
              placeholder={isDigitalHuman ? t("form.imageDigitalHumanPlaceholder") : t("form.imagePlaceholder")}
              className={inp + " flex-1 min-w-0"}
            />
            <button
              type="button"
              onClick={() => imageInputRef.current?.click()}
              disabled={imageUploading}
              className="shrink-0 px-3 py-2.5 rounded-xl border border-white/[0.06] bg-white/[0.03]
                         text-gray-400 hover:text-[#E11D48] hover:bg-[#E11D48]/10 hover:border-[#E11D48]/30
                         transition-all duration-300 disabled:opacity-40 cursor-pointer"
              title={t("form.selectLocalFile")}
            >
              {imageUploading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : imageFileName && productImageUrl ? (
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              ) : (
                <Upload className="w-3.5 h-3.5" />
              )}
            </button>
          </div>
          {imageUploading && (
            <div className="mt-1.5">
              <div className="h-1 rounded-full bg-white/[0.06] overflow-hidden">
                <div className="h-full bg-[#E11D48]/70 rounded-full transition-all duration-300"
                     style={{ width: `${imageUploadPct}%` }} />
              </div>
              <p className="text-[10px] text-gray-500 mt-0.5">{imageFileName} 路 {imageUploadPct}%</p>
            </div>
          )}
          {!imageUploading && imageFileName && productImageUrl && (
            <div className="mt-1 flex items-center gap-1.5 text-[10px] text-emerald-400/80">
              <CheckCircle2 className="w-3 h-3" />
              <span className="truncate">{imageFileName} {t("form.uploaded")}</span>
              <button type="button" onClick={() => { setProductImageUrl(""); setImageFileName(""); }}
                      className="ml-auto text-gray-600 hover:text-gray-400 cursor-pointer">
                <X className="w-3 h-3" />
              </button>
            </div>
          )}
        </section>

        {isDigitalHuman && (
          <>
            <section>
              <Label icon={Music}>{t("form.audioFile")}</Label>
              {/* Hidden file input */}
              <input
                ref={audioInputRef}
                type="file"
                accept="audio/*"
                className="hidden"
                onChange={handleAudioFileChange}
              />
              <div className="flex gap-2">
                <input
                  type="text"
                  value={audioUrl}
                  onChange={(e) => { setAudioUrl(e.target.value); setAudioFileName(""); }}
                  placeholder={t("form.audioPlaceholder")}
                  className={inp + " flex-1 min-w-0"}
                />
                <button
                  type="button"
                  onClick={() => audioInputRef.current?.click()}
                  disabled={audioUploading}
                  className="shrink-0 px-3 py-2.5 rounded-xl border border-white/[0.06] bg-white/[0.03]
                             text-gray-400 hover:text-[#E11D48] hover:bg-[#E11D48]/10 hover:border-[#E11D48]/30
                             transition-all duration-300 disabled:opacity-40 cursor-pointer"
                  title={t("form.selectLocalFile")}
                >
                  {audioUploading ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : audioFileName && audioUrl ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                  ) : (
                    <Upload className="w-3.5 h-3.5" />
                  )}
                </button>
              </div>
              {audioUploading && (
                <div className="mt-1.5">
                  <div className="h-1 rounded-full bg-white/[0.06] overflow-hidden">
                    <div className="h-full bg-[#E11D48]/70 rounded-full transition-all duration-300"
                         style={{ width: `${audioUploadPct}%` }} />
                  </div>
                  <p className="text-[10px] text-gray-500 mt-0.5">{audioFileName} 路 {audioUploadPct}%</p>
                </div>
              )}
              {!audioUploading && audioFileName && audioUrl && (
                <div className="mt-1 flex items-center gap-1.5 text-[10px] text-emerald-400/80">
                  <CheckCircle2 className="w-3 h-3" />
                  <span className="truncate">{audioFileName} {t("form.uploaded")}</span>
                  <button type="button" onClick={() => { setAudioUrl(""); setAudioFileName(""); }}
                          className="ml-auto text-gray-600 hover:text-gray-400 cursor-pointer">
                    <X className="w-3 h-3" />
                  </button>
                </div>
              )}
              <p className="text-[10px] text-gray-600 mt-1 flex items-center gap-1">
                <span className="w-1 h-1 rounded-full bg-[#E11D48]/40 shrink-0" />
                {t("form.audioHint")}
              </p>
            </section>

            <Divider />

            {/* 鈹€鈹€ Voice Mode 鈹€鈹€ */}
            <section>
              <Label icon={Mic2}>{t("form.voiceMode")}</Label>
              <div className="flex rounded-xl border border-white/[0.06] overflow-hidden bg-white/[0.02]">
                {[
                  { value: 0, label: t("form.voiceOriginal") },
                  { value: 1, label: t("form.voiceClone") },
                ].map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setVoiceMode(opt.value)}
                    className={`flex-1 py-2.5 text-xs font-semibold transition-all duration-300 cursor-pointer ${
                      voiceMode === opt.value
                        ? "bg-gradient-to-r from-[#E11D48]/20 to-purple-500/10 text-[#E11D48] border-b-2 border-[#E11D48]"
                        : "text-gray-500 hover:text-gray-300 hover:bg-white/[0.03]"
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </section>

            {voiceMode === 1 && (
              <section>
                <Label icon={Type}>{t("form.synthesisText")}</Label>
                <textarea
                  value={voiceText}
                  onChange={(e) => setVoiceText(e.target.value)}
                  placeholder={t("form.synthesisPlaceholder")}
                  rows={2}
                  className={inp + " resize-none"}
                />
              </section>
            )}

            <section>
              <Label icon={PersonStanding}>{t("form.motionDesc")}</Label>
              <input
                type="text"
                value={motionPrompt}
                onChange={(e) => setMotionPrompt(e.target.value)}
                placeholder={t("form.motionPlaceholder")}
                className={inp}
              />
            </section>
          </>
        )}

        <Divider />

        {/* 鈹€鈹€ Visual params 鈹€鈹€ */}
        <div className="grid grid-cols-2 gap-x-3 gap-y-3">
          {/* Style */}
          <section>
            <Label icon={Palette}>{t("form.style")}</Label>
            <div className="relative">
              <select
                value={style}
                onChange={(e) => setStyle(e.target.value)}
                className={inp + " appearance-none pr-7 cursor-pointer"}
              >
                {STYLE_KEYS.map((s) => (
                  <option key={s.value} value={s.value}>{t(s.labelKey)}</option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500" />
            </div>
          </section>

          {/* Duration */}
          <section>
            <Label icon={Clock}>{t("form.duration")}</Label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={5}
                max={1800}
                step={5}
                value={duration}
                onChange={(e) => setDuration(Math.max(5, Math.min(1800, Number(e.target.value))))}
                className={inp + " text-center tabular-nums"}
              />
              <span className="text-xs text-gray-600 shrink-0">{t("common.seconds")}</span>
            </div>
          </section>
        </div>

        {/* Orientation - inline segmented */}
        <section>
          <Label icon={Monitor}>{t("form.screen")}</Label>
          <div className="flex rounded-xl border border-white/[0.06] overflow-hidden bg-white/[0.02]">
            {ORIENTATION_KEYS.map((o) => {
              const active = orientation === o.value;
              return (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => setOrientation(o.value)}
                  className={`flex-1 flex items-center justify-center gap-2 py-2.5 text-xs transition-all duration-300 cursor-pointer ${
                    active
                      ? "bg-gradient-to-r from-[#E11D48]/20 to-purple-500/10 text-[#E11D48]"
                      : "text-gray-500 hover:text-gray-300 hover:bg-white/[0.03]"
                  }`}
                >
                  <span
                    className={`block rounded-sm transition-all duration-300 ${active ? "border-[#E11D48] shadow-[0_0_8px_rgba(225,29,72,0.3)]" : "border-gray-600"}`}
                    style={{
                      width: o.value === "vertical" ? 8 : o.value === "horizontal" ? 14 : 10,
                      height: o.value === "vertical" ? 14 : o.value === "horizontal" ? 8 : 10,
                      borderWidth: 1.5,
                    }}
                  />
                  <span className="font-semibold">{t(o.labelKey)}</span>
                  <span className="text-[10px] text-gray-600">{o.ratio}</span>
                </button>
              );
            })}
          </div>
        </section>
          </>
        )}

        {/* 鈹€鈹€ Error 鈹€鈹€ */}
        {error && (
          <div className="rounded-lg bg-red-500/[0.08] border border-red-500/20 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
            <span className="w-4 h-4 rounded-full bg-red-500/20 flex items-center justify-center shrink-0 text-[10px]">!</span>
            {error}
          </div>
        )}
      </div>

      {/* 鈹€鈹€ Action button (sticky bottom) 鈹€鈹€ */}
      <div className="px-5 py-4 border-t border-white/[0.06] bg-[#0a0a12]/50 backdrop-blur-sm">
        <button
          type="button"
          onClick={handleSubmit}
          disabled={busy || !theme.trim()}
          className="w-full relative group flex items-center justify-center gap-2.5 rounded-xl
                     bg-gradient-to-r from-[#E11D48] via-[#E11D48] to-[#9333EA] 
                     hover:from-[#F43F5E] hover:via-[#E11D48] hover:to-[#A855F7]
                     active:scale-[0.98]
                     disabled:opacity-40 disabled:pointer-events-none disabled:from-gray-700 disabled:to-gray-800
                     text-white text-sm font-bold px-4 py-3.5
                     transition-all duration-300 cursor-pointer overflow-hidden
                     shadow-[0_4px_24px_rgba(225,29,72,0.3)] hover:shadow-[0_8px_40px_rgba(225,29,72,0.4)]"
        >
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-700" />
          {busy ? (
            <Loader2 className="w-5 h-5 animate-spin relative z-10" />
          ) : (
            <Play className="w-5 h-5 fill-current relative z-10" />
          )}
          <span className="relative z-10">
            {busy
              ? (isPptV7 ? "澶勭悊涓?.." : t("form.generating"))
              : isPptV7
                ? "鐢熸垚 PPT V7"
                : isDigitalHuman
                  ? t("form.generateDigitalHuman")
                  : t("form.startGenerate")}
          </span>
        </button>
      </div>
    </aside>
  );
}

