"use client";

import React, { useCallback, useState } from "react";
import {
  GripVertical,
  Plus,
  Trash2,
  ChevronDown,
  ChevronUp,
  Clock,
  ListChecks,
} from "lucide-react";
import type { SlideOutline, PresentationOutline } from "@/lib/types/ppt";

interface OutlineEditorProps {
  outline: PresentationOutline;
  onChange: (outline: PresentationOutline) => void;
  onConfirm: () => void;
  onBack?: () => void;
}

export default function OutlineEditor({
  outline,
  onChange,
  onConfirm,
  onBack,
}: OutlineEditorProps) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(0);

  const updateSlide = useCallback(
    (idx: number, updates: Partial<SlideOutline>) => {
      const slides = [...outline.slides];
      slides[idx] = { ...slides[idx], ...updates };
      onChange({
        ...outline,
        slides,
        totalDuration: slides.reduce((sum, s) => sum + s.estimatedDuration, 0),
      });
    },
    [outline, onChange],
  );

  const addSlide = useCallback(() => {
    const newSlide: SlideOutline = {
      id: `new-${Date.now()}`,
      order: outline.slides.length + 1,
      title: "New Slide",
      description: "",
      keyPoints: [],
      suggestedElements: ["text"],
      estimatedDuration: 120,
    };
    const slides = [...outline.slides, newSlide];
    onChange({
      ...outline,
      slides,
      totalDuration: slides.reduce((sum, s) => sum + s.estimatedDuration, 0),
    });
    setExpandedIdx(slides.length - 1);
  }, [outline, onChange]);

  const removeSlide = useCallback(
    (idx: number) => {
      const slides = outline.slides
        .filter((_, i) => i !== idx)
        .map((s, i) => ({ ...s, order: i + 1 }));

      onChange({
        ...outline,
        slides,
        totalDuration: slides.reduce((sum, s) => sum + s.estimatedDuration, 0),
      });

      if (expandedIdx === idx) setExpandedIdx(null);
    },
    [expandedIdx, onChange, outline],
  );

  const updateKeyPoints = useCallback(
    (idx: number, text: string) => {
      const points = text
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean);
      updateSlide(idx, { keyPoints: points });
    },
    [updateSlide],
  );

  const totalMinutes = Math.round(outline.totalDuration / 60);

  const inputClass =
    "mt-1 w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-sm text-gray-200 outline-none transition-colors focus:border-[#E11D48]/50";

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 p-4 text-gray-200">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-100">Outline Review</h2>
          <p className="mt-1 text-sm text-gray-500">
            {outline.slides.length} slides · {totalMinutes} min · {outline.style}
          </p>
        </div>
        <div className="flex gap-2">
          {onBack && (
            <button
              onClick={onBack}
              className="rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-gray-200 transition hover:bg-white/[0.08]"
            >
              Back
            </button>
          )}
          <button
            onClick={onConfirm}
            className="rounded-xl bg-gradient-to-r from-[#E11D48] to-[#9333EA] px-4 py-2 text-sm font-medium text-white transition hover:from-[#F43F5E] hover:to-[#A855F7]"
          >
            Confirm & Generate
          </button>
        </div>
      </div>

      <div>
        <label className="text-sm font-medium text-gray-300">Deck Title</label>
        <input
          type="text"
          value={outline.title}
          onChange={(e) => onChange({ ...outline, title: e.target.value })}
          className="mt-1 w-full rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-gray-200 outline-none transition-colors focus:border-[#E11D48]/50"
        />
      </div>

      <div className="flex flex-col gap-2">
        {outline.slides.map((slide, idx) => (
          <div
            key={slide.id}
            className="overflow-hidden rounded-xl border border-white/[0.06] bg-white/[0.02]"
          >
            <button
              onClick={() => setExpandedIdx(expandedIdx === idx ? null : idx)}
              className="flex w-full items-center gap-3 px-4 py-3 transition hover:bg-white/[0.05]"
            >
              <GripVertical className="h-4 w-4 shrink-0 text-gray-500" />
              <span className="w-6 shrink-0 text-xs font-mono text-gray-500">
                {String(slide.order).padStart(2, "0")}
              </span>
              <span className="flex-1 truncate text-left text-sm font-medium text-gray-100">
                {slide.title}
              </span>
              <span className="flex shrink-0 items-center gap-1 text-xs text-gray-500">
                <Clock className="h-3 w-3" />
                {Math.round(slide.estimatedDuration / 60)}m
              </span>
              {expandedIdx === idx ? (
                <ChevronUp className="h-4 w-4 shrink-0 text-gray-500" />
              ) : (
                <ChevronDown className="h-4 w-4 shrink-0 text-gray-500" />
              )}
            </button>

            {expandedIdx === idx && (
              <div className="flex flex-col gap-3 border-t border-white/[0.06] px-4 pb-4 pt-3">
                <div>
                  <label className="text-xs font-medium text-gray-500">Title</label>
                  <input
                    type="text"
                    value={slide.title}
                    onChange={(e) => updateSlide(idx, { title: e.target.value })}
                    className={inputClass}
                  />
                </div>

                <div>
                  <label className="text-xs font-medium text-gray-500">Description</label>
                  <textarea
                    value={slide.description}
                    onChange={(e) => updateSlide(idx, { description: e.target.value })}
                    rows={2}
                    className={`${inputClass} resize-none`}
                  />
                </div>

                <div>
                  <label className="flex items-center gap-1 text-xs font-medium text-gray-500">
                    <ListChecks className="h-3 w-3" /> Key Points (one per line)
                  </label>
                  <textarea
                    value={slide.keyPoints.join("\n")}
                    onChange={(e) => updateKeyPoints(idx, e.target.value)}
                    rows={3}
                    className={`${inputClass} resize-none`}
                  />
                </div>

                <div className="flex items-center gap-4">
                  <div>
                    <label className="text-xs font-medium text-gray-500">Duration (s)</label>
                    <input
                      type="number"
                      value={slide.estimatedDuration}
                      onChange={(e) =>
                        updateSlide(idx, {
                          estimatedDuration: parseInt(e.target.value, 10) || 120,
                        })
                      }
                      min={30}
                      max={600}
                      className="mt-1 w-24 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-sm text-gray-200 outline-none transition-colors focus:border-[#E11D48]/50"
                    />
                  </div>
                  <button
                    onClick={() => removeSlide(idx)}
                    className="mt-5 rounded-md p-1.5 text-red-300 transition hover:bg-red-500/[0.15]"
                    title="Delete slide"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      <button
        onClick={addSlide}
        className="flex items-center justify-center gap-2 rounded-xl border-2 border-dashed border-white/[0.12] py-2.5 text-sm text-gray-400 transition hover:border-[#E11D48]/50 hover:text-[#E11D48]"
      >
        <Plus className="h-4 w-4" />
        Add Slide
      </button>
    </div>
  );
}
