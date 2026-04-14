"use client";

import React, { useMemo, useState } from 'react';
import { Player } from '@remotion/player';
import { Maximize2, Minimize2, Volume2, VolumeX, Download, Play } from 'lucide-react';
import { useProject } from '@/contexts/ProjectContext';
import { useT } from '@/lib/i18n';
import VideoTemplate, {
  type VideoTemplateProps,
  type ClipData,
  type SubtitleData,
} from '@/remotion/compositions/VideoTemplate';
import Tutorial, {
  type TutorialTemplateProps,
  type TutorialStep,
} from '@/remotion/compositions/templates/Tutorial';

// Template IDs that use the dedicated Tutorial composition
const TUTORIAL_TEMPLATE_IDS = new Set(['tutorial', 'tutorial-soft', 'tutorial-know', 'tutorial-prod']);

// Map template_id to transition type
const TEMPLATE_TRANSITIONS: Record<string, 'fade' | 'slide' | 'none'> = {
  'product-ad': 'slide',
  'beauty-review': 'fade',
  'fashion-style': 'slide',
  'food-showcase': 'fade',
  'tech-unbox': 'slide',
  'home-living': 'fade',
  'brand-story': 'fade',
  'knowledge-edu': 'fade',
  'funny-skit': 'slide',
  'travel-vlog': 'fade',
  'tutorial': 'slide',
};

// Map template_id to style overrides
const TEMPLATE_STYLES: Record<string, VideoTemplateProps['style']> = {
  'product-ad': { primaryColor: '#FF6B35', titleFontSize: 56 },
  'beauty-review': { primaryColor: '#FFB5C2', subtitleFontSize: 24, overlayOpacity: 0.4 },
  'fashion-style': { primaryColor: '#C084FC', titleFontSize: 48 },
  'food-showcase': { primaryColor: '#FFD700', secondaryColor: '#FF8C00', overlayOpacity: 0.5 },
  'tech-unbox': { primaryColor: '#00D4FF', secondaryColor: '#7B2FFF', titleFontSize: 52 },
  'home-living': { primaryColor: '#34D399', overlayOpacity: 0.5 },
  'brand-story': { primaryColor: '#E8D5B5', overlayOpacity: 0.7, subtitleFontSize: 32 },
  'knowledge-edu': { primaryColor: '#4ECDC4', titleFontSize: 48, subtitleFontSize: 26 },
  'funny-skit': { primaryColor: '#84CC16', titleFontSize: 52 },
  'travel-vlog': { primaryColor: '#FB923C', overlayOpacity: 0.5 },
  'tutorial': { primaryColor: '#3B82F6', secondaryColor: '#10B981', titleFontSize: 44, subtitleFontSize: 22 },
};

const FPS = 30;

export default function RemotionPreview() {
  const t = useT();
  const { project, tasks, scenes, finalVideoUrl } = useProject();
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isMuted, setIsMuted] = useState(false);

  // Build clips from completed video tasks
  const clips: ClipData[] = useMemo(() => {
    return tasks
      .filter(t => t.status === 'succeeded' && t.video_url)
      .sort((a, b) => a.clip_idx - b.clip_idx)
      .map(t => ({
        url: t.video_url!,
        duration: t.duration || 5,
        type: 'video' as const,
      }));
  }, [tasks]);

  // Build subtitles from scenes
  const subtitles: SubtitleData[] = useMemo(() => {
    if (!scenes.length || !clips.length) return [];
    let currentFrame = 0;
    return scenes.slice(0, clips.length).map((scene, idx) => {
      const duration = clips[idx]?.duration || 5;
      const durationInFrames = Math.round(duration * FPS);
      const sub: SubtitleData = {
        text: scene.narration || scene.desc || '',
        startFrame: currentFrame,
        endFrame: currentFrame + durationInFrames,
      };
      currentFrame += durationInFrames;
      return sub;
    }).filter(s => s.text);
  }, [scenes, clips]);

  // Compute composition dimensions based on project orientation
  const orientation = ((project as Record<string, unknown>)?.orientation as string) || 'vertical';
  const { width, height } = useMemo(() => {
    switch (orientation) {
      case 'horizontal':
      case '横屏':
        return { width: 1280, height: 720 };
      case 'square':
      case '正方形':
        return { width: 720, height: 720 };
      default: return { width: 720, height: 1280 };
    }
  }, [orientation]);

  const templateId = project?.template_id || 'product-ad';
  const isTutorial = TUTORIAL_TEMPLATE_IDS.has(templateId);
  const transition = TEMPLATE_TRANSITIONS[templateId] || 'fade';
  const style = TEMPLATE_STYLES[templateId] || {};

  const totalDurationInFrames = useMemo(() => {
    const totalSeconds = clips.reduce((acc, c) => acc + c.duration, 0);
    // Tutorial adds 1s step-transition per clip + optional intro/outro
    const extraSeconds = isTutorial ? clips.length * 1 : 0;
    return Math.max(Math.round((totalSeconds + extraSeconds) * FPS), FPS);
  }, [clips, isTutorial]);

  // Build tutorial step metadata from scenes
  const tutorialSteps: TutorialStep[] = useMemo(() => {
    if (!isTutorial) return [];
    return scenes.map((scene, idx) => ({
      stepNumber: idx + 1,
      stepTitle: (scene as unknown as Record<string, unknown>).step_title as string || scene.narration || scene.desc || `Step ${idx + 1}`,
      annotations: ((scene as unknown as Record<string, unknown>).annotations as TutorialStep['annotations']) || [],
    }));
  }, [scenes, isTutorial]);

  // Choose composition component and props based on template type
  const compositionComponent = isTutorial ? Tutorial : VideoTemplate;
  const inputProps = isTutorial
    ? ({
        clips,
        subtitles,
        steps: tutorialSteps,
        totalSteps: tutorialSteps.length || clips.length,
        style,
        introText: project?.theme as string || undefined,
      } satisfies TutorialTemplateProps)
    : ({
        clips,
        subtitles,
        transition,
        style,
        introText: project?.theme as string || undefined,
      } satisfies VideoTemplateProps);

  if (clips.length === 0) {
    return (
      <div className="flex items-center justify-center h-full bg-black/50 rounded-xl border border-gray-800">
        <div className="text-center text-gray-600 space-y-2">
          <Play className="w-12 h-12 mx-auto text-gray-700" />
          <p className="text-sm">{t("preview.waitingClips")}</p>
          <p className="text-xs text-gray-700">{t("preview.waitingClipsHint")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`relative bg-black rounded-xl overflow-hidden border border-gray-800 ${isFullscreen ? 'fixed inset-0 z-50 rounded-none' : ''}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900/80 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-green-500" />
          <span className="text-xs text-gray-400">
            {t("preview.summary", {
              clipCount: clips.length,
              duration: (totalDurationInFrames / FPS).toFixed(1),
            })}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setIsMuted(!isMuted)}
            className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-gray-300 transition"
          >
            {isMuted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
          </button>
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-gray-300 transition"
          >
            {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
          {finalVideoUrl && (
            <a
              href={finalVideoUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 rounded-lg hover:bg-gray-800 text-green-500 hover:text-green-400 transition"
            >
              <Download className="w-4 h-4" />
            </a>
          )}
        </div>
      </div>

      {/* Player */}
      <div className="flex items-center justify-center p-4 bg-black" style={{ minHeight: isFullscreen ? 'calc(100vh - 48px)' : '400px' }}>
        <div style={{ width: '100%', maxWidth: isFullscreen ? '90vh' : '100%', aspectRatio: `${width}/${height}` }}>
          <Player
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            component={compositionComponent as any}
            inputProps={inputProps as unknown as Record<string, unknown>}
            durationInFrames={totalDurationInFrames}
            compositionWidth={width}
            compositionHeight={height}
            fps={FPS}
            style={{ width: '100%', height: '100%' }}
            controls
            autoPlay={false}
            loop
          />
        </div>
      </div>
    </div>
  );
}
