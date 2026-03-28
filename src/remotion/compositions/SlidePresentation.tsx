/**
 * SlidePresentation — Remotion PPT讲解视频组件 (v2 商用级)
 *
 * 借鉴 OpenMAIC + Remotion 社区最佳实践:
 * - TransitionSeries 专业转场 (fade/slide/wipe)
 * - Spring 动画 (元素入场)
 * - 模板背景 (渐变/纯色)
 * - TTS 音频同步
 */

import React from 'react';
import {
  AbsoluteFill,
  Sequence,
  Audio,
  Img,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  spring,
  Easing,
} from 'remotion';
import { TransitionSeries, linearTiming, springTiming } from '@remotion/transitions';
import { fade } from '@remotion/transitions/fade';
import { slide } from '@remotion/transitions/slide';
import { wipe } from '@remotion/transitions/wipe';

// ── Types ──────────────────────────────────────────────────────────

function sanitizeHtml(raw: string): string {
  if (!raw) return '';
  return raw
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/on\w+\s*=\s*"[^"]*"/gi, '')
    .replace(/on\w+\s*=\s*'[^']*'/gi, '')
    .replace(/on\w+\s*=[^\s>]+/gi, '')
    .replace(/javascript:/gi, '')
    .replace(/data:/gi, '');
}

interface SlideElement {
  id: string;
  type: 'text' | 'image' | 'shape' | 'chart' | 'table' | 'latex' | 'video' | 'audio';
  left: number; top: number; width: number; height: number;
  content?: string; src?: string; style?: Record<string, any>;
  chartType?: string; chartData?: Record<string, any>;
  tableRows?: string[][];
}

interface SlideBackground {
  type: 'solid' | 'gradient' | 'image';
  color?: string;
  gradient?: { type: string; colors: { pos: number; color: string }[]; rotate: number };
  imageUrl?: string;
}

interface SlideContent {
  id: string; order: number; title: string;
  elements: SlideElement[]; background?: SlideBackground;
  narration: string; narrationAudioUrl?: string; duration: number;
}

export interface SlidePresentationProps {
  slides: SlideContent[];
  bgmUrl?: string; bgmVolume?: number;
  defaultTransition?: 'fade' | 'slide' | 'wipe';
}

// ── 转场映射 ───────────────────────────────────────────────────────

function getPresentation(type: string) {
  switch (type) {
    case 'slide': return slide({ direction: 'from-right' }) as any;
    case 'wipe': return wipe({ direction: 'from-top-left' }) as any;
    case 'fade':
    default: return fade() as any;
  }
}

const transitionTiming = springTiming({
  config: { damping: 200, stiffness: 80 }, // 平滑无弹跳
  durationInFrames: 20,
});

// ── 主组件 ─────────────────────────────────────────────────────────

export default function SlidePresentation({
  slides, bgmUrl, bgmVolume = 0.15, defaultTransition = 'fade',
}: SlidePresentationProps) {
  const { fps } = useVideoConfig();

  if (!slides.length) return <AbsoluteFill style={{ backgroundColor: '#000' }} />;

  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      {/* TransitionSeries 专业转场 — 音频内嵌于每页 */}
      <TransitionSeries>
        {slides.map((slide, idx) => {
          // 帧数 = 音频时长 × fps (音频驱动)
          const dur = Math.max(Math.round(slide.duration * fps), fps * 2);
          return (
            <React.Fragment key={slide.id}>
              <TransitionSeries.Sequence durationInFrames={dur}>
                <AbsoluteFill>
                  <SingleSlide slide={slide} />
                  {/* TTS 音频与页面同步播放 */}
                  {slide.narrationAudioUrl && (
                    <Audio src={slide.narrationAudioUrl} volume={1} />
                  )}
                </AbsoluteFill>
              </TransitionSeries.Sequence>
              {idx < slides.length - 1 && (
                <TransitionSeries.Transition
                  timing={transitionTiming}
                  presentation={getPresentation(defaultTransition)}
                />
              )}
            </React.Fragment>
          );
        })}
      </TransitionSeries>

      {/* BGM (全片循环) */}
      {bgmUrl && <Audio src={bgmUrl} volume={bgmVolume} loop />}
    </AbsoluteFill>
  );
}

// ── 单页幻灯片 ─────────────────────────────────────────────────────

function SingleSlide({ slide }: { slide: SlideContent }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // 背景
  const bgStyle = getBackgroundStyle(slide.background);

  return (
    <AbsoluteFill style={bgStyle}>
      {/* 背景图片 */}
      {slide.background?.type === 'image' && slide.background.imageUrl && (
        <Img src={slide.background.imageUrl}
          style={{ position: 'absolute', width: '100%', height: '100%', objectFit: 'cover', opacity: 0.3 }} />
      )}

      {/* 标题 */}
      {slide.title && (
        <div style={{
          position: 'absolute', top: 40, left: 60, right: 60,
          fontSize: 32, fontWeight: 'bold', color: inferTextColor(slide.background),
          fontFamily: 'Microsoft YaHei, sans-serif', zIndex: 10,
        }}>
          {slide.title}
        </div>
      )}

      {/* 元素 (spring 入场动画) */}
      {slide.elements.map((el, idx) => (
        <AnimatedElement key={el.id} element={el} index={idx} bg={slide.background} />
      ))}

      {/* 页码 */}
      <div style={{
        position: 'absolute', bottom: 16, right: 24,
        fontSize: 12, color: inferTextColor(slide.background, 0.4), fontFamily: 'sans-serif',
      }}>
        {slide.order + 1}
      </div>
    </AbsoluteFill>
  );
}

// ── 背景样式 ───────────────────────────────────────────────────────

function getBackgroundStyle(bg?: SlideBackground): React.CSSProperties {
  if (!bg) return { backgroundColor: '#ffffff' };
  if (bg.type === 'gradient' && bg.gradient) {
    const colors = bg.gradient.colors || [];
    const stops = colors.map(c => `${c.color} ${c.pos}%`).join(', ');
    const angle = bg.gradient.rotate || 180;
    return { background: `linear-gradient(${angle}deg, ${stops})` };
  }
  return { backgroundColor: bg.color || '#ffffff' };
}

function inferTextColor(bg?: SlideBackground, alpha: number = 1): string {
  if (!bg) return `rgba(30,41,59,${alpha})`;
  if (bg.type === 'gradient' && bg.gradient) {
    const colors = bg.gradient.colors || [];
    const lastColor = colors[colors.length - 1]?.color || '#333';
    return isLightColor(lastColor) ? `rgba(30,41,59,${alpha})` : `rgba(226,232,240,${alpha})`;
  }
  return isLightColor(bg.color || '#fff') ? `rgba(30,41,59,${alpha})` : `rgba(226,232,240,${alpha})`;
}

function isLightColor(hex: string): boolean {
  const c = hex.replace('#', '');
  const r = parseInt(c.substring(0, 2), 16) || 0;
  const g = parseInt(c.substring(2, 4), 16) || 0;
  const b = parseInt(c.substring(4, 6), 16) || 0;
  return (r * 299 + g * 587 + b * 114) / 1000 > 128;
}

// ── 元素动画 (借鉴 OpenMAIC spring + staggered entry) ──────────────

function AnimatedElement({
  element, index, bg,
}: {
  element: SlideElement; index: number; bg?: SlideBackground;
}) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const enterDelay = Math.round(index * 0.15 * fps);
  const progress = spring({
    frame: frame - enterDelay, fps,
    config: { damping: 200, stiffness: 120 }, // 平滑无弹跳
  });

  const opacity = interpolate(progress, [0, 1], [0, 1], { extrapolateRight: 'clamp' });
  const translateY = interpolate(progress, [0, 1], [20, 0], { extrapolateRight: 'clamp' });

  return (
    <div style={{
      position: 'absolute',
      left: element.left, top: element.top,
      width: element.width, height: element.height,
      opacity, transform: `translateY(${translateY}px)`,
      transition: 'none',
    }}>
      <ElementRenderer element={element} bg={bg} />
    </div>
  );
}

// ── 元素渲染器 ─────────────────────────────────────────────────────

function ElementRenderer({ element, bg }: { element: SlideElement; bg?: SlideBackground }) {
  const s = element.style || {};
  const textColor = s.color || inferTextColor(bg);

  switch (element.type) {
    case 'text':
      return (
        <div style={{
          fontSize: s.fontSize || 18,
          fontFamily: s.fontFamily || 'Microsoft YaHei, sans-serif',
          color: textColor,
          fontWeight: s.bold ? 'bold' : 'normal',
          fontStyle: s.italic ? 'italic' : 'normal',
          textAlign: s.align || 'left',
          lineHeight: 1.5, width: '100%', height: '100%', overflow: 'hidden',
          backgroundColor: s.backgroundColor || 'transparent',
          borderRadius: s.borderRadius || 0,
          padding: s.padding || 0,
        }}
          dangerouslySetInnerHTML={{ __html: sanitizeHtml(element.content || '') }}
        />
      );

    case 'image':
      if (!element.src) return <div style={{ width: '100%', height: '100%', backgroundColor: '#e2e8f0', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8', fontSize: 14 }}>Image</div>;
      return <Img src={element.src} style={{ width: '100%', height: '100%', objectFit: s.objectFit || 'cover', borderRadius: s.borderRadius || 8 }} />;

    case 'shape':
      return <div style={{
        width: '100%', height: '100%',
        backgroundColor: s.backgroundColor || '#2563eb',
        borderRadius: s.borderRadius || 0,
      }} />;

    case 'chart':
      return <ChartRenderer chartType={element.chartType || 'bar'} chartData={element.chartData || {}} />;

    case 'table':
      return <TableRenderer rows={element.tableRows || []} />;

    default:
      return null;
  }
}

// ── 图表渲染器 ─────────────────────────────────────────────────────

function ChartRenderer({ chartType, chartData }: { chartType: string; chartData: Record<string, any> }) {
  const labels: string[] = chartData.labels || [];
  const datasets = chartData.datasets || [];
  const data: number[] = datasets[0]?.data || [];
  const maxVal = Math.max(...data, 1);
  const colors = ['#2563eb', '#7c3aed', '#06b6d4', '#22c55e', '#f59e0b', '#ef4444', '#ec4899', '#8b5cf6'];

  if (chartType === 'bar' || chartType === 'column') {
    return (
      <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'flex-end', justifyContent: 'center', gap: 6, padding: 16 }}>
        {data.map((val, i) => (
          <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1 }}>
            <div style={{ fontSize: 10, color: '#64748b', marginBottom: 2 }}>{val}</div>
            <div style={{
              width: '60%', height: `${(val / maxVal) * 70}%`,
              backgroundColor: colors[i % colors.length], borderRadius: '4px 4px 0 0', minHeight: 12,
            }} />
            <div style={{ fontSize: 9, color: '#64748b', marginTop: 4, textAlign: 'center', maxWidth: 60, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {labels[i]}
            </div>
          </div>
        ))}
      </div>
    );
  }

  // pie/doughnut: 色块列表
  if (chartType === 'pie' || chartType === 'doughnut') {
    return (
      <div style={{ width: '100%', height: '100%', padding: 16 }}>
        {data.map((val, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', marginBottom: 6 }}>
            <div style={{ width: 14, height: 14, backgroundColor: colors[i % colors.length], borderRadius: 3, marginRight: 8 }} />
            <span style={{ fontSize: 13, color: '#334155' }}>{labels[i]}: {val}</span>
          </div>
        ))}
      </div>
    );
  }

  // line: 数值列表
  return (
    <div style={{ width: '100%', height: '100%', padding: 16 }}>
      {data.map((val, i) => (
        <div key={i} style={{ fontSize: 13, color: '#334155', marginBottom: 3 }}>{labels[i]}: {val}</div>
      ))}
    </div>
  );
}

// ── 表格渲染器 ─────────────────────────────────────────────────────

function TableRenderer({ rows }: { rows: string[][] }) {
  if (!rows.length) return null;
  return (
    <table style={{ width: '100%', height: '100%', borderCollapse: 'collapse', fontSize: 13, fontFamily: 'Microsoft YaHei, sans-serif' }}>
      <tbody>
        {rows.map((row, ri) => (
          <tr key={ri}>
            {row.map((cell, ci) => (
              <td key={ci} style={{
                border: '1px solid #e2e8f0', padding: '6px 10px',
                backgroundColor: ri === 0 ? '#f1f5f9' : '#ffffff',
                fontWeight: ri === 0 ? 600 : 400, color: '#334155',
              }}>
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
