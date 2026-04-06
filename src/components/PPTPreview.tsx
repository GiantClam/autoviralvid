"use client";
/* eslint-disable @next/next/no-img-element */

import React from "react";
import {
  ChevronLeft,
  ChevronRight,
  FileText,
  Image as ImageIcon,
  BarChart3,
  Table,
} from "lucide-react";
import type { SlideContent, SlideElement } from "@/lib/types/ppt";

function sanitizeHtml(raw: string): string {
  if (!raw) return "";
  return raw
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/on\w+\s*=\s*"[^"]*"/gi, "")
    .replace(/on\w+\s*=\s*'[^']*'/gi, "")
    .replace(/on\w+\s*=[^\s>]+/gi, "")
    .replace(/javascript:/gi, "")
    .replace(/data:/gi, "");
}

interface PPTPreviewProps {
  slides: SlideContent[];
  currentIndex?: number;
  onIndexChange?: (index: number) => void;
}

function styleNumber(value: unknown, fallback: number): number {
  return typeof value === "number" ? value : fallback;
}

function styleString(value: unknown, fallback: string): string {
  return typeof value === "string" ? value : fallback;
}

function styleBoolean(value: unknown): boolean {
  return value === true;
}

function styleObjectFit(value: unknown): React.CSSProperties["objectFit"] {
  return value === "contain" || value === "cover" || value === "fill" || value === "none" || value === "scale-down"
    ? value
    : "cover";
}

export default function PPTPreview({
  slides,
  currentIndex: controlledIndex,
  onIndexChange,
}: PPTPreviewProps) {
  const [internalIndex, setInternalIndex] = React.useState(0);
  const currentIndex = controlledIndex ?? internalIndex;
  const setCurrentIndex = onIndexChange ?? setInternalIndex;

  const slide = slides[currentIndex];
  if (!slide) return null;

  const totalMinutes = Math.round(
    slides.reduce((sum, s) => sum + s.duration, 0) / 60,
  );

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-3 p-4 text-gray-200">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-500">
          PPT Preview · {slides.length} slides · {totalMinutes} min
        </h3>
      </div>

      <div className="relative overflow-hidden rounded-2xl border border-white/[0.06] bg-white/[0.02] shadow-sm">
        <div
          className="relative w-full"
          style={{
            paddingBottom: "56.25%",
            backgroundColor: slide.background?.color || "#ffffff",
          }}
        >
          {slide.background?.type === "image" && slide.background.imageUrl && (
            <img
              src={slide.background.imageUrl}
              className="absolute inset-0 h-full w-full object-cover opacity-30"
              alt=""
            />
          )}

          {slide.title && (
            <div
              className="absolute left-[5%] right-[5%] top-[5%] font-bold text-gray-900"
              style={{ fontSize: "clamp(14px, 2.5vw, 28px)" }}
            >
              {slide.title}
            </div>
          )}

          {slide.elements.map((el) => (
            <PreviewElement key={el.id} element={el} />
          ))}

          <div className="absolute bottom-3 right-4 text-xs text-gray-500">
            {currentIndex + 1} / {slides.length}
          </div>
        </div>

        <div className="flex items-center justify-between border-t border-white/[0.06] bg-white/[0.02] px-4 py-2">
          <button
            onClick={() => setCurrentIndex(Math.max(0, currentIndex - 1))}
            disabled={currentIndex === 0}
            className="rounded-md p-1.5 text-gray-300 transition hover:bg-white/[0.08] disabled:opacity-30"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>

          <span className="text-xs text-gray-500">
            Slide {currentIndex + 1} · {slide.duration}s
          </span>

          <button
            onClick={() => setCurrentIndex(Math.min(slides.length - 1, currentIndex + 1))}
            disabled={currentIndex === slides.length - 1}
            className="rounded-md p-1.5 text-gray-300 transition hover:bg-white/[0.08] disabled:opacity-30"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {slides.map((s, idx) => (
          <button
            key={s.id}
            onClick={() => setCurrentIndex(idx)}
            className={`h-12 w-20 shrink-0 rounded-md border-2 text-xs font-mono transition ${
              idx === currentIndex
                ? "border-[#E11D48]/60 bg-[#E11D48]/15 text-[#E11D48]"
                : "border-white/[0.12] bg-white/[0.03] text-gray-400 hover:border-white/[0.2]"
            }`}
          >
            {idx + 1}
          </button>
        ))}
      </div>

      {slide.narration && (
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
          <div className="mb-1.5 flex items-center gap-1.5">
            <FileText className="h-3.5 w-3.5 text-gray-500" />
            <span className="text-xs font-medium text-gray-500">Narration</span>
          </div>
          <p className="text-sm leading-relaxed text-gray-300">{slide.narration}</p>
        </div>
      )}
    </div>
  );
}

function PreviewElement({ element }: { element: SlideElement }) {
  const baseStyle: React.CSSProperties = {
    position: "absolute",
    left: `${(element.left / 1920) * 100}%`,
    top: `${(element.top / 1080) * 100}%`,
    width: `${(element.width / 1920) * 100}%`,
    height: `${(element.height / 1080) * 100}%`,
    overflow: "hidden",
  };

  switch (element.type) {
    case "text":
      {
        const fontSize = styleNumber(element.style?.fontSize, 18);
        const fontFamily = styleString(element.style?.fontFamily, "sans-serif");
        const color = styleString(element.style?.color, "#333");
        const isBold = styleBoolean(element.style?.bold);
      return (
        <div
          style={{
            ...baseStyle,
            fontSize: `clamp(8px, ${(fontSize / 1920) * 100}vw, ${fontSize}px)`,
            fontFamily,
            color,
            fontWeight: isBold ? "bold" : "normal",
            lineHeight: 1.5,
          }}
          dangerouslySetInnerHTML={{ __html: sanitizeHtml(element.content || "") }}
        />
      );
      }

    case "image":
      if (!element.src) {
        return (
          <div style={baseStyle} className="flex items-center justify-center bg-gray-100">
            <ImageIcon className="h-6 w-6 text-gray-300" />
          </div>
        );
      }

      return (
        <img
          src={element.src}
          style={{ ...baseStyle, objectFit: styleObjectFit(element.style?.objectFit) }}
          alt=""
        />
      );

    case "chart":
      return (
        <div style={baseStyle} className="flex items-center justify-center rounded bg-gray-50">
          <div className="flex items-center gap-1 text-gray-500">
            <BarChart3 className="h-5 w-5" />
            <span className="text-xs">Chart</span>
          </div>
        </div>
      );

    case "table":
      return (
        <div style={baseStyle} className="flex items-center justify-center rounded bg-gray-50">
          <div className="flex items-center gap-1 text-gray-500">
            <Table className="h-5 w-5" />
            <span className="text-xs">Table {element.tableRows?.length || 0}</span>
          </div>
        </div>
      );

    default:
      return null;
  }
}

