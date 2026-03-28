import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Easing,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {TransitionSeries, springTiming} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {slide} from '@remotion/transitions/slide';
import {wipe} from '@remotion/transitions/wipe';

import {MarpSlide} from '../components/MarpSlide';

export type V7SlideType =
  | 'cover'
  | 'toc'
  | 'grid_2'
  | 'grid_3'
  | 'quote_stat'
  | 'timeline'
  | 'divider'
  | 'summary';

export interface V7DialogueLine {
  role: 'host' | 'student';
  text: string;
}

export type V7Action =
  | {type: 'highlight'; keyword: string; startFrame?: number}
  | {type: 'circle'; x: number; y: number; r: number; startFrame?: number}
  | {type: 'appear_items'; items: string[]; startFrame?: number}
  | {type: 'zoom_in'; region: string; startFrame?: number};

export interface V7Slide {
  page_number: number;
  slide_type: V7SlideType;
  markdown?: string;
  script: V7DialogueLine[];
  actions?: V7Action[];
  narration_audio_url?: string;
  duration?: number;
}

export interface MarpPresentationProps {
  slides: V7Slide[];
}

const transitionTiming = springTiming({
  durationInFrames: 18,
  config: {damping: 200},
});

const getTransition = (from: V7SlideType, to: V7SlideType): any => {
  if (to === 'divider') return fade();
  if (to === 'quote_stat') return wipe({direction: 'from-left'});
  if (from === 'cover') return slide({direction: 'from-right'});
  if (to === 'summary') return slide({direction: 'from-bottom'});
  return slide({direction: 'from-bottom'});
};

const KeywordPulse: React.FC<{keyword: string; startFrame: number}> = ({keyword, startFrame}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame - startFrame, [0, 8, 16, 24], [0, 1, 0.6, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const scale = interpolate(frame - startFrame, [0, 10], [0.82, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return (
    <div
      style={{
        position: 'absolute',
        bottom: 64,
        left: '50%',
        transform: `translateX(-50%) scale(${scale})`,
        background: '#ef4444',
        color: '#ffffff',
        padding: '10px 24px',
        borderRadius: 10,
        fontSize: 30,
        fontWeight: 900,
        opacity,
      }}
    >
      {keyword}
    </div>
  );
};

const DrawCircle: React.FC<{x: number; y: number; r: number; startFrame: number}> = ({
  x,
  y,
  r,
  startFrame,
}) => {
  const frame = useCurrentFrame();
  const progress = interpolate(frame - startFrame, [0, 20], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });
  const dashLen = 2 * Math.PI * r;
  return (
    <svg
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
      }}
    >
      <circle
        cx={x}
        cy={y}
        r={r}
        fill="none"
        stroke="#ef4444"
        strokeWidth={4}
        strokeDasharray={dashLen}
        strokeDashoffset={dashLen * (1 - progress)}
        strokeLinecap="round"
        transform={`rotate(-90 ${x} ${y})`}
      />
    </svg>
  );
};

const AppearSequentially: React.FC<{items: string[]; startFrame: number}> = ({items, startFrame}) => {
  const frame = useCurrentFrame();
  return (
    <div style={{position: 'absolute', bottom: 80, left: 60, right: 60}}>
      {items.slice(0, 5).map((item, i) => {
        const itemStart = startFrame + i * 18;
        const opacity = interpolate(frame, [itemStart, itemStart + 10], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
        const y = interpolate(frame, [itemStart, itemStart + 10], [20, 0], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
        return (
          <div
            key={`${item}-${i}`}
            style={{
              opacity,
              transform: `translateY(${y}px)`,
              fontSize: 28,
              marginBottom: 12,
              color: '#1e293b',
              fontWeight: 600,
            }}
          >
            ▸ {item}
          </div>
        );
      })}
    </div>
  );
};

const ZoomInMask: React.FC<{region: string; startFrame: number}> = ({region, startFrame}) => {
  const frame = useCurrentFrame();
  const scale = interpolate(frame - startFrame, [0, 16], [1, 1.08], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const regionMap: Record<string, string> = {
    left: '15%',
    center: '50%',
    right: '85%',
  };
  return (
    <div
      style={{
        position: 'absolute',
        left: regionMap[region] || regionMap.center,
        top: '50%',
        width: 520,
        height: 300,
        border: '3px solid rgba(239,68,68,0.9)',
        transform: `translate(-50%, -50%) scale(${scale})`,
        borderRadius: 16,
      }}
    />
  );
};

const ActionOverlay: React.FC<{actions: V7Action[]}> = ({actions}) => {
  if (!actions.length) return null;
  return (
    <>
      {actions.map((action, idx) => {
        const startFrame = Math.max(0, Number(action.startFrame ?? 18));
        if (action.type === 'highlight') {
          return <KeywordPulse key={idx} keyword={action.keyword} startFrame={startFrame} />;
        }
        if (action.type === 'circle') {
          return (
            <DrawCircle
              key={idx}
              x={action.x}
              y={action.y}
              r={action.r}
              startFrame={startFrame}
            />
          );
        }
        if (action.type === 'appear_items') {
          return <AppearSequentially key={idx} items={action.items || []} startFrame={startFrame} />;
        }
        if (action.type === 'zoom_in') {
          return <ZoomInMask key={idx} region={action.region} startFrame={startFrame} />;
        }
        return null;
      })}
    </>
  );
};

const getDurationFrames = (slide: V7Slide, fps: number) => {
  const sec = slide.duration && slide.duration > 0 ? slide.duration : 6;
  return Math.max(Math.round(sec * fps), fps * 2);
};

const normalizeMarkdown = (slide: V7Slide): string => {
  const md = typeof slide.markdown === 'string' ? slide.markdown.trim() : '';
  if (md) return md;

  // Fallback to avoid rendering literal "undefined" when upstream payload is malformed.
  const title = `Slide ${slide.page_number}`;
  return `# ${title}\n<mark>Content unavailable</mark>`;
};

const MarpPresentation: React.FC<MarpPresentationProps> = ({slides}) => {
  const {fps} = useVideoConfig();
  if (!slides.length) {
    return <AbsoluteFill style={{backgroundColor: '#000'}} />;
  }

  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      <TransitionSeries>
        {slides.map((slide, i) => {
          const dur = getDurationFrames(slide, fps);
          return (
            <React.Fragment key={`${slide.page_number}-${i}`}>
              <TransitionSeries.Sequence durationInFrames={dur}>
                <AbsoluteFill>
                  <MarpSlide markdown={normalizeMarkdown(slide)} theme="modern-tailwind" />
                  {slide.narration_audio_url ? <Audio src={slide.narration_audio_url} /> : null}
                  <ActionOverlay actions={slide.actions || []} />
                </AbsoluteFill>
              </TransitionSeries.Sequence>
              {i < slides.length - 1 ? (
                <TransitionSeries.Transition
                  presentation={getTransition(slide.slide_type, slides[i + 1].slide_type)}
                  timing={transitionTiming}
                />
              ) : null}
            </React.Fragment>
          );
        })}
      </TransitionSeries>
    </AbsoluteFill>
  );
};

export default MarpPresentation;
