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

// ── Types ──

export interface ClipData {
  url: string;
  duration: number; // in seconds
  type?: 'video' | 'image';
}

export interface SubtitleData {
  text: string;
  startFrame: number;
  endFrame: number;
}

export type TransitionType = 'fade' | 'slide' | 'none';

export interface TemplateStyle {
  primaryColor?: string;
  secondaryColor?: string;
  fontFamily?: string;
  titleFontSize?: number;
  subtitleFontSize?: number;
  overlayOpacity?: number;
}

export interface VideoTemplateProps {
  clips: ClipData[];
  subtitles?: SubtitleData[];
  bgmUrl?: string;
  bgmVolume?: number;
  transition?: TransitionType;
  style?: TemplateStyle;
  introText?: string;
  outroText?: string;
}

// ── Sub-components ──

function FadeTransition({ children, durationInFrames }: { children: React.ReactNode; durationInFrames: number }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fadeDuration = Math.min(Math.floor(fps * 0.5), Math.floor(durationInFrames / 4));

  const opacity = interpolate(
    frame,
    [0, fadeDuration, durationInFrames - fadeDuration, durationInFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );

  return <AbsoluteFill style={{ opacity }}>{children}</AbsoluteFill>;
}

function SlideTransition({ children, durationInFrames }: { children: React.ReactNode; durationInFrames: number }) {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const slideDuration = Math.min(Math.floor(fps * 0.3), Math.floor(durationInFrames / 4));

  const translateX = interpolate(
    frame,
    [0, slideDuration],
    [width, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );

  return (
    <AbsoluteFill style={{ transform: `translateX(${translateX}px)` }}>
      {children}
    </AbsoluteFill>
  );
}

function TextOverlay({
  text,
  fontSize = 48,
  color = '#ffffff',
  position = 'center',
  style,
}: {
  text: string;
  fontSize?: number;
  color?: string;
  position?: 'top' | 'center' | 'bottom';
  style?: TemplateStyle;
}) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const animatedScale = spring({ frame, fps, config: { damping: 15, stiffness: 120 } });

  const positionStyles: Record<string, React.CSSProperties> = {
    top: { top: '10%', left: '50%', transform: `translateX(-50%) scale(${animatedScale})` },
    center: { top: '50%', left: '50%', transform: `translate(-50%, -50%) scale(${animatedScale})` },
    bottom: { bottom: '10%', left: '50%', transform: `translateX(-50%) scale(${animatedScale})` },
  };

  return (
    <div
      style={{
        position: 'absolute',
        ...positionStyles[position],
        fontSize,
        color,
        fontFamily: style?.fontFamily || 'sans-serif',
        fontWeight: 'bold',
        textShadow: '0 2px 8px rgba(0,0,0,0.6)',
        textAlign: 'center',
        padding: '0 20px',
        lineHeight: 1.3,
        whiteSpace: 'pre-wrap',
        maxWidth: '80%',
      }}
    >
      {text}
    </div>
  );
}

function SubtitleOverlay({ text, style }: { text: string; style?: TemplateStyle }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const opacity = spring({ frame, fps, config: { damping: 20, stiffness: 200 } });

  return (
    <div
      style={{
        position: 'absolute',
        bottom: '8%',
        left: '50%',
        transform: 'translateX(-50%)',
        opacity,
        backgroundColor: `rgba(0,0,0,${style?.overlayOpacity ?? 0.6})`,
        padding: '8px 24px',
        borderRadius: 8,
        maxWidth: '85%',
        textAlign: 'center',
      }}
    >
      <span
        style={{
          color: '#ffffff',
          fontSize: style?.subtitleFontSize || 28,
          fontFamily: style?.fontFamily || 'sans-serif',
          lineHeight: 1.4,
        }}
      >
        {text}
      </span>
    </div>
  );
}

// ── Main Composition ──

export default function VideoTemplate({
  clips,
  subtitles = [],
  bgmUrl,
  bgmVolume = 0.3,
  transition = 'fade',
  style = {},
  introText,
  outroText,
}: VideoTemplateProps) {
  const { fps } = useVideoConfig();

  // Calculate frame positions for each clip
  const clipSequences = clips.reduce<Array<ClipData & { startFrame: number; durationInFrames: number; idx: number }>>(
    (acc, clip, idx) => {
      const previousEnd =
        acc.length === 0
          ? 0
          : acc[acc.length - 1].startFrame + acc[acc.length - 1].durationInFrames;
      const durationInFrames = Math.round(clip.duration * fps);
      acc.push({ ...clip, startFrame: previousEnd, durationInFrames, idx });
      return acc;
    },
    [],
  );

  const totalFrames = clipSequences.reduce(
    (sum, clip) => sum + clip.durationInFrames,
    0,
  );

  // Intro: first 2 seconds
  const introFrames = introText ? Math.round(2 * fps) : 0;
  // Outro: last 2 seconds
  const outroFrames = outroText ? Math.round(2 * fps) : 0;

  const TransitionWrapper = transition === 'fade' ? FadeTransition :
    transition === 'slide' ? SlideTransition :
    ({ children }: { children: React.ReactNode }) => (
      <AbsoluteFill>{children}</AbsoluteFill>
    );

  return (
    <AbsoluteFill style={{ backgroundColor: '#000000' }}>
      {/* Intro text overlay */}
      {introText && (
        <Sequence from={0} durationInFrames={introFrames}>
          <AbsoluteFill style={{ backgroundColor: '#000000' }}>
            <TextOverlay
              text={introText}
              fontSize={style.titleFontSize || 56}
              color={style.primaryColor || '#ffffff'}
              position="center"
              style={style}
            />
          </AbsoluteFill>
        </Sequence>
      )}

      {/* Video/Image clips */}
      {clipSequences.map(({ url, startFrame, durationInFrames, type, idx }) => (
        <Sequence key={idx} from={startFrame + introFrames} durationInFrames={durationInFrames}>
          <TransitionWrapper durationInFrames={durationInFrames}>
            <AbsoluteFill>
              {type === 'image' ? (
                <Img
                  src={url}
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                />
              ) : (
                <Video
                  src={url}
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                />
              )}
            </AbsoluteFill>
          </TransitionWrapper>
        </Sequence>
      ))}

      {/* Subtitles */}
      {subtitles.map((sub, idx) => (
        <Sequence key={`sub-${idx}`} from={sub.startFrame + introFrames} durationInFrames={sub.endFrame - sub.startFrame}>
          <SubtitleOverlay text={sub.text} style={style} />
        </Sequence>
      ))}

      {/* Outro text overlay */}
      {outroText && (
        <Sequence from={totalFrames + introFrames} durationInFrames={outroFrames}>
          <AbsoluteFill style={{ backgroundColor: '#000000' }}>
            <TextOverlay
              text={outroText}
              fontSize={style.titleFontSize || 56}
              color={style.primaryColor || '#ffffff'}
              position="center"
              style={style}
            />
          </AbsoluteFill>
        </Sequence>
      )}

      {/* Background music */}
      {bgmUrl && (
        <Audio src={bgmUrl} volume={bgmVolume} />
      )}
    </AbsoluteFill>
  );
}
