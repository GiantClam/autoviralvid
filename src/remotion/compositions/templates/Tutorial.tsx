import React from 'react';
import {
  AbsoluteFill,
  Sequence,
  Video,
  Img,
  Audio,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  spring,
} from 'remotion';
import type { ClipData, SubtitleData, TemplateStyle } from '../VideoTemplate';

// ── Tutorial-specific types ──

export interface TutorialAnnotation {
  type: 'highlight' | 'arrow' | 'circle';
  /** Normalized coordinates 0-1 */
  x?: number;
  y?: number;
  w?: number;
  h?: number;
  from?: [number, number];
  to?: [number, number];
  label?: string;
}

export interface TutorialStep {
  stepNumber: number;
  stepTitle: string;
  annotations?: TutorialAnnotation[];
  codeSnippet?: string;
}

export interface TutorialTemplateProps {
  clips: ClipData[];
  subtitles?: SubtitleData[];
  steps?: TutorialStep[];
  totalSteps?: number;
  bgmUrl?: string;
  bgmVolume?: number;
  style?: TemplateStyle;
  introText?: string;
  outroText?: string;
}

// ── Sub-components ──

function StepIndicator({
  stepNumber,
  totalSteps,
  stepTitle,
  primaryColor,
}: {
  stepNumber: number;
  totalSteps: number;
  stepTitle: string;
  primaryColor: string;
}) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = spring({ frame, fps, config: { damping: 15, stiffness: 120 } });
  const progress = totalSteps > 0 ? stepNumber / totalSteps : 0;

  return (
    <div
      style={{
        position: 'absolute',
        top: 24,
        left: 24,
        right: 24,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        transform: `scale(${scale})`,
        transformOrigin: 'top left',
        zIndex: 10,
      }}
    >
      {/* Step badge + title */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: 12,
            backgroundColor: primaryColor,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 20,
            fontWeight: 'bold',
            color: '#fff',
            fontFamily: 'sans-serif',
            boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
          }}
        >
          {stepNumber}
        </div>
        <span
          style={{
            fontSize: 22,
            fontWeight: 600,
            color: '#fff',
            fontFamily: 'sans-serif',
            textShadow: '0 1px 6px rgba(0,0,0,0.5)',
          }}
        >
          {stepTitle}
        </span>
        <span
          style={{
            marginLeft: 'auto',
            fontSize: 14,
            color: 'rgba(255,255,255,0.7)',
            fontFamily: 'sans-serif',
          }}
        >
          {stepNumber}/{totalSteps}
        </span>
      </div>

      {/* Progress bar */}
      <div
        style={{
          height: 4,
          borderRadius: 2,
          backgroundColor: 'rgba(255,255,255,0.15)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            height: '100%',
            width: `${progress * 100}%`,
            backgroundColor: primaryColor,
            borderRadius: 2,
            transition: 'width 0.3s ease',
          }}
        />
      </div>
    </div>
  );
}

function AnnotationOverlay({
  annotations,
  primaryColor,
}: {
  annotations: TutorialAnnotation[];
  primaryColor: string;
}) {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  return (
    <AbsoluteFill style={{ zIndex: 5, pointerEvents: 'none' }}>
      {annotations.map((ann, idx) => {
        const delay = idx * 5;
        const opacity = spring({
          frame: Math.max(0, frame - delay),
          fps,
          config: { damping: 20, stiffness: 150 },
        });

        if (ann.type === 'highlight' && ann.x != null && ann.y != null && ann.w != null && ann.h != null) {
          return (
            <div
              key={idx}
              style={{
                position: 'absolute',
                left: ann.x * width,
                top: ann.y * height,
                width: ann.w * width,
                height: ann.h * height,
                border: `3px solid ${primaryColor}`,
                borderRadius: 8,
                opacity,
                boxShadow: `0 0 12px ${primaryColor}40`,
              }}
            >
              {ann.label && (
                <span
                  style={{
                    position: 'absolute',
                    top: -28,
                    left: 0,
                    fontSize: 14,
                    color: '#fff',
                    backgroundColor: primaryColor,
                    padding: '2px 10px',
                    borderRadius: 6,
                    fontFamily: 'sans-serif',
                    fontWeight: 600,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {ann.label}
                </span>
              )}
            </div>
          );
        }

        if (ann.type === 'circle' && ann.x != null && ann.y != null) {
          const r = (ann.w ?? 0.05) * width;
          return (
            <div
              key={idx}
              style={{
                position: 'absolute',
                left: ann.x * width - r,
                top: ann.y * height - r,
                width: r * 2,
                height: r * 2,
                borderRadius: '50%',
                border: `3px solid ${primaryColor}`,
                opacity,
                boxShadow: `0 0 12px ${primaryColor}40`,
              }}
            />
          );
        }

        if (ann.type === 'arrow' && ann.from && ann.to) {
          const x1 = ann.from[0] * width;
          const y1 = ann.from[1] * height;
          const x2 = ann.to[0] * width;
          const y2 = ann.to[1] * height;
          return (
            <svg
              key={idx}
              style={{ position: 'absolute', top: 0, left: 0, width, height, opacity }}
            >
              <defs>
                <marker
                  id={`arrowhead-${idx}`}
                  markerWidth="10"
                  markerHeight="7"
                  refX="10"
                  refY="3.5"
                  orient="auto"
                >
                  <polygon points="0 0, 10 3.5, 0 7" fill={primaryColor} />
                </marker>
              </defs>
              <line
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke={primaryColor}
                strokeWidth={3}
                markerEnd={`url(#arrowhead-${idx})`}
              />
            </svg>
          );
        }

        return null;
      })}
    </AbsoluteFill>
  );
}

function CaptionBar({ text, style }: { text: string; style?: TemplateStyle }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const slideUp = interpolate(frame, [0, Math.floor(fps * 0.3)], [40, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const opacity = interpolate(frame, [0, Math.floor(fps * 0.3)], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <div
      style={{
        position: 'absolute',
        bottom: 0,
        left: 0,
        right: 0,
        padding: '16px 24px',
        background: 'linear-gradient(transparent, rgba(0,0,0,0.85))',
        transform: `translateY(${slideUp}px)`,
        opacity,
        zIndex: 8,
      }}
    >
      <p
        style={{
          color: '#fff',
          fontSize: style?.subtitleFontSize || 24,
          fontFamily: style?.fontFamily || 'sans-serif',
          lineHeight: 1.5,
          margin: 0,
          textShadow: '0 1px 4px rgba(0,0,0,0.6)',
        }}
      >
        {text}
      </p>
    </div>
  );
}

function StepTransition({
  stepNumber,
  stepTitle,
  primaryColor,
}: {
  stepNumber: number;
  stepTitle: string;
  primaryColor: string;
}) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = spring({ frame, fps, config: { damping: 12, stiffness: 100 } });
  const fadeOut = interpolate(frame, [Math.floor(fps * 0.6), Math.floor(fps * 0.8)], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: '#0a0a0a',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexDirection: 'column',
        gap: 16,
        opacity: fadeOut,
      }}
    >
      <div
        style={{
          width: 80,
          height: 80,
          borderRadius: 20,
          backgroundColor: primaryColor,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 40,
          fontWeight: 'bold',
          color: '#fff',
          fontFamily: 'sans-serif',
          transform: `scale(${scale})`,
          boxShadow: `0 4px 24px ${primaryColor}60`,
        }}
      >
        {stepNumber}
      </div>
      <span
        style={{
          fontSize: 28,
          fontWeight: 600,
          color: '#fff',
          fontFamily: 'sans-serif',
          transform: `scale(${scale})`,
        }}
      >
        {stepTitle}
      </span>
    </AbsoluteFill>
  );
}

// ── Main Tutorial Composition ──

export default function Tutorial({
  clips,
  subtitles = [],
  steps = [],
  totalSteps,
  bgmUrl,
  bgmVolume = 0.2,
  style = {},
  introText,
  outroText,
}: TutorialTemplateProps) {
  const { fps } = useVideoConfig();

  const primaryColor = style.primaryColor || '#3B82F6';
  const resolvedTotalSteps = totalSteps ?? (steps.length || clips.length);

  // Intro: 2 seconds
  const introFrames = introText ? Math.round(2 * fps) : 0;
  // Outro: 2 seconds
  const outroFrames = outroText ? Math.round(2 * fps) : 0;
  // Step transition: 1 second per step
  const stepTransitionFrames = Math.round(1 * fps);

  // Build clip sequences
  const clipSequences = clips.reduce<Array<ClipData & {
    idx: number;
    step?: TutorialStep;
    transitionStart: number;
    clipStart: number;
    clipDurationInFrames: number;
    transFrames: number;
  }>>((acc, clip, idx) => {
    const step = steps[idx];
    const transFrames = step ? stepTransitionFrames : 0;
    const clipDurationInFrames = Math.round(clip.duration * fps);
    const previousEnd =
      acc.length === 0
        ? introFrames
        : acc[acc.length - 1].clipStart + acc[acc.length - 1].clipDurationInFrames;

    acc.push({
      ...clip,
      idx,
      step,
      transitionStart: previousEnd,
      clipStart: previousEnd + transFrames,
      clipDurationInFrames,
      transFrames,
    });
    return acc;
  }, []);

  const outroStartFrame =
    clipSequences.length === 0
      ? introFrames
      : clipSequences[clipSequences.length - 1].clipStart +
        clipSequences[clipSequences.length - 1].clipDurationInFrames;

  return (
    <AbsoluteFill style={{ backgroundColor: '#0a0a0a' }}>
      {/* Intro */}
      {introText && (
        <Sequence from={0} durationInFrames={introFrames}>
          <AbsoluteFill
            style={{
              backgroundColor: '#0a0a0a',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <IntroTitle text={introText} primaryColor={primaryColor} style={style} />
          </AbsoluteFill>
        </Sequence>
      )}

      {/* Steps */}
      {clipSequences.map(({ idx, step, transitionStart, clipStart, clipDurationInFrames, transFrames, url, type }) => (
        <React.Fragment key={idx}>
          {/* Step transition card */}
          {step && transFrames > 0 && (
            <Sequence from={transitionStart} durationInFrames={transFrames}>
              <StepTransition
                stepNumber={step.stepNumber}
                stepTitle={step.stepTitle}
                primaryColor={primaryColor}
              />
            </Sequence>
          )}

          {/* Clip + overlays */}
          <Sequence from={clipStart} durationInFrames={clipDurationInFrames}>
            <AbsoluteFill>
              {/* Media */}
              {type === 'image' ? (
                <Img src={url} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              ) : (
                <Video src={url} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              )}

              {/* Step indicator */}
              {step && (
                <StepIndicator
                  stepNumber={step.stepNumber}
                  totalSteps={resolvedTotalSteps}
                  stepTitle={step.stepTitle}
                  primaryColor={primaryColor}
                />
              )}

              {/* Annotations */}
              {step?.annotations && step.annotations.length > 0 && (
                <AnnotationOverlay annotations={step.annotations} primaryColor={primaryColor} />
              )}
            </AbsoluteFill>
          </Sequence>
        </React.Fragment>
      ))}

      {/* Subtitles / captions */}
      {subtitles.map((sub, idx) => (
        <Sequence key={`sub-${idx}`} from={sub.startFrame} durationInFrames={sub.endFrame - sub.startFrame}>
          <CaptionBar text={sub.text} style={style} />
        </Sequence>
      ))}

      {/* Outro */}
      {outroText && (
        <Sequence from={outroStartFrame} durationInFrames={outroFrames}>
          <AbsoluteFill
            style={{
              backgroundColor: '#0a0a0a',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexDirection: 'column',
              gap: 12,
            }}
          >
            <span
              style={{
                fontSize: style.titleFontSize || 36,
                fontWeight: 'bold',
                color: primaryColor,
                fontFamily: style.fontFamily || 'sans-serif',
              }}
            >
              {outroText}
            </span>
          </AbsoluteFill>
        </Sequence>
      )}

      {/* BGM */}
      {bgmUrl && <Audio src={bgmUrl} volume={bgmVolume} />}
    </AbsoluteFill>
  );
}

// ── Intro title sub-component ──

function IntroTitle({
  text,
  primaryColor,
  style,
}: {
  text: string;
  primaryColor: string;
  style?: TemplateStyle;
}) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = spring({ frame, fps, config: { damping: 15, stiffness: 120 } });

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 16,
        transform: `scale(${scale})`,
      }}
    >
      <div
        style={{
          width: 64,
          height: 64,
          borderRadius: 16,
          backgroundColor: primaryColor,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 28,
          color: '#fff',
          fontFamily: 'sans-serif',
          boxShadow: `0 4px 24px ${primaryColor}60`,
        }}
      >
        &#9654;
      </div>
      <span
        style={{
          fontSize: style?.titleFontSize || 44,
          fontWeight: 'bold',
          color: '#fff',
          fontFamily: style?.fontFamily || 'sans-serif',
          textAlign: 'center',
          maxWidth: '80%',
          lineHeight: 1.3,
          textShadow: '0 2px 8px rgba(0,0,0,0.6)',
        }}
      >
        {text}
      </span>
    </div>
  );
}
