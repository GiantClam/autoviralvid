/**
 * Premium Slide Components — 商业级 Remotion 视频组件
 *
 * 设计原则:
 * - 深色渐变背景 (Apple keynote 风格)
 * - 大字号渐变文字
 * - 动画计数器 (大数字)
 * - 交错入场动画
 * - 专业卡片布局 + 阴影
 * - 粒子/噪点纹理背景
 */

import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig, spring, interpolate, Easing, Img } from 'remotion';

// ── Types ──────────────────────────────────────────────────────────

export type LayoutType = 'hero' | 'points' | 'stats' | 'quote' | 'versus' | 'closing';

export interface SlideData {
  layout: LayoutType;
  title: string;
  subtitle?: string;
  points?: string[];
  stats?: { number: string; label: string; unit?: string }[];
  quote?: string;
  author?: string;
  leftTitle?: string; leftPoints?: string[];
  rightTitle?: string; rightPoints?: string[];
  bgImage?: string;
  emphasisWords?: string[];
}

type StatItem = NonNullable<SlideData['stats']>[number];

// ── 动画 Hook ──────────────────────────────────────────────────────

function useReveal(delay: number = 0) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: frame - delay, fps, config: { damping: 200, stiffness: 80 } });
  return {
    opacity: interpolate(p, [0, 1], [0, 1], { extrapolateRight: 'clamp' }),
    y: interpolate(p, [0, 1], [40, 0], { extrapolateRight: 'clamp' }),
    scale: interpolate(p, [0, 1], [0.95, 1], { extrapolateRight: 'clamp' }),
  };
}

function useCountUp(target: number, delay: number = 0, durationFrames: number = 60) {
  const frame = useCurrentFrame();
  const progress = interpolate(frame - delay, [0, durationFrames], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic),
  });
  return Math.round(target * progress);
}

// ── 文本高亮 ───────────────────────────────────────────────────────

function Highlight({ text, words }: { text: string; words: string[] }) {
  if (!words.length) return <>{text}</>;
  const pattern = words.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
  const parts = text.split(new RegExp(`(${pattern})`, 'gi'));
  return <>{parts.map((p, i) =>
    words.some(w => w.toLowerCase() === p.toLowerCase())
      ? <span key={i} style={{ color: '#38bdf8', fontWeight: 800 }}>{p}</span>
      : <span key={i}>{p}</span>
  )}</>;
}

function RevealPointCard({ point, index, emphasisWords }: { point: string; index: number; emphasisWords: string[] }) {
  const reveal = useReveal(index * 8);
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: 16,
      opacity: reveal.opacity, transform: `translateY(${reveal.y}px)`,
      background: 'rgba(255,255,255,0.03)', borderRadius: 12, padding: '16px 24px',
      borderLeft: '3px solid rgba(56,189,248,0.3)',
    }}>
      <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#38bdf8', marginTop: 8, flexShrink: 0 }} />
      <div style={{ fontSize: 26, color: '#e2e8f0', lineHeight: 1.5 }}>
        <Highlight text={point} words={emphasisWords} />
      </div>
    </div>
  );
}

function StatCard({ stat, index }: { stat: StatItem; index: number }) {
  const reveal = useReveal(index * 15);
  const num = parseFloat(stat.number.replace(/[^0-9.]/g, '')) || 0;
  const displayNum = useCountUp(num, index * 15, 60);

  return (
    <div style={{ textAlign: 'center', opacity: reveal.opacity, transform: `translateY(${reveal.y}px) scale(${reveal.scale})` }}>
      <div style={{ fontSize: 96, fontWeight: 900, background: 'linear-gradient(135deg, #38bdf8, #a78bfa)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', lineHeight: 1 }}>
        {stat.number.includes('%') ? `${displayNum}%` : displayNum}
        {stat.unit && <span style={{ fontSize: 36, marginLeft: 4 }}>{stat.unit}</span>}
      </div>
      <div style={{ fontSize: 20, color: '#94a3b8', marginTop: 12 }}>{stat.label}</div>
    </div>
  );
}

function VersusItem({ item, color, emphasisWords, delay }: { item: string; color: string; emphasisWords: string[]; delay: number }) {
  const reveal = useReveal(delay);
  return (
    <div style={{ display: 'flex', gap: 12, padding: '10px 0', opacity: reveal.opacity, transform: `translateY(${reveal.y}px)` }}>
      <div style={{ color, fontSize: 20, marginTop: 2 }}>&#10003;</div>
      <div style={{ fontSize: 22, color: '#e2e8f0', lineHeight: 1.5 }}>
        <Highlight text={item} words={emphasisWords} />
      </div>
    </div>
  );
}

function VersusColumn({ title, items, color, emphasisWords, index }: { title: string; items: string[]; color: string; emphasisWords: string[]; index: number }) {
  const reveal = useReveal(index * 10);
  return (
    <div style={{ flex: 1, opacity: reveal.opacity, transform: `translateY(${reveal.y}px)` }}>
      <div style={{ background: color, borderRadius: 12, padding: '14px 24px', marginBottom: 20 }}>
        <div style={{ fontSize: 24, fontWeight: 700, color: '#fff' }}>{title}</div>
      </div>
      {items.map((item, itemIndex) => (
        <VersusItem
          key={`${title}-${itemIndex}`}
          item={item}
          color={color}
          emphasisWords={emphasisWords}
          delay={index * 10 + itemIndex * 5 + 10}
        />
      ))}
    </div>
  );
}

// ── 背景组件 ───────────────────────────────────────────────────────

function PremiumBg({ image, variant = 'dark' }: { image?: string; variant?: 'dark' | 'gradient' | 'light' }) {
  const frame = useCurrentFrame();
  const slowPan = interpolate(frame, [0, 900], [0, -50], { extrapolateRight: 'clamp' });

  if (image) {
    return (
      <AbsoluteFill>
        <Img src={image} style={{ width: '110%', height: '110%', objectFit: 'cover', position: 'absolute', left: slowPan, top: 0, filter: 'brightness(0.3)' }} />
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(180deg, rgba(0,0,0,0.7) 0%, rgba(15,23,42,0.95) 100%)' }} />
      </AbsoluteFill>
    );
  }

  if (variant === 'gradient') {
    return (
      <AbsoluteFill style={{ background: 'linear-gradient(135deg, #0f172a 0%, #1e3a5f 50%, #0f172a 100%)' }}>
        <div style={{ position: 'absolute', width: 600, height: 600, borderRadius: '50%', background: 'radial-gradient(circle, rgba(56,189,248,0.08) 0%, transparent 70%)', top: -100, right: -100 }} />
        <div style={{ position: 'absolute', width: 400, height: 400, borderRadius: '50%', background: 'radial-gradient(circle, rgba(139,92,246,0.06) 0%, transparent 70%)', bottom: -100, left: -100 }} />
      </AbsoluteFill>
    );
  }

  if (variant === 'light') {
    return (
      <AbsoluteFill style={{ background: 'linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%)' }}>
        <div style={{ position: 'absolute', width: 800, height: 800, borderRadius: '50%', background: 'radial-gradient(circle, rgba(37,99,235,0.04) 0%, transparent 70%)', top: -200, right: -200 }} />
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill style={{ background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%)' }}>
      <div style={{ position: 'absolute', width: 600, height: 600, borderRadius: '50%', background: 'radial-gradient(circle, rgba(56,189,248,0.06) 0%, transparent 70%)', top: -150, right: -150 }} />
    </AbsoluteFill>
  );
}

// ── Hero 封面 ──────────────────────────────────────────────────────

export function HeroSlide({ data }: { data: SlideData }) {
  const a1 = useReveal(0);
  const a2 = useReveal(10);
  const a3 = useReveal(20);

  return (
    <AbsoluteFill>
      <PremiumBg variant="gradient" />
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '0 120px' }}>
        <div style={{ fontSize: 16, letterSpacing: 8, color: '#38bdf8', fontWeight: 600, marginBottom: 20, opacity: a1.opacity, transform: `translateY(${a1.y}px)`, textTransform: 'uppercase' }}>
          {data.subtitle || ''}
        </div>
        <div style={{ fontSize: 80, fontWeight: 900, lineHeight: 1.1, background: 'linear-gradient(135deg, #ffffff 0%, #94a3b8 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', opacity: a2.opacity, transform: `translateY(${a2.y}px) scale(${a2.scale})` }}>
          <Highlight text={data.title} words={data.emphasisWords || []} />
        </div>
        <div style={{ width: 80, height: 4, background: 'linear-gradient(90deg, #38bdf8, #8b5cf6)', borderRadius: 2, marginTop: 30, opacity: a3.opacity }} />
      </div>
    </AbsoluteFill>
  );
}

// ── 要点页 ─────────────────────────────────────────────────────────

export function PointsSlide({ data }: { data: SlideData }) {
  const points = data.points || [];

  return (
    <AbsoluteFill>
      <PremiumBg variant="dark" />
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 100, background: 'linear-gradient(90deg, #1e3a5f, #2563eb)', display: 'flex', alignItems: 'center', padding: '0 80px' }}>
        <div style={{ fontSize: 36, fontWeight: 700, color: '#fff' }}>{data.title}</div>
      </div>
      <div style={{ position: 'absolute', top: 130, left: 80, right: 80, bottom: 60, display: 'flex', gap: 40 }}>
        <div style={{ width: 6, background: 'linear-gradient(180deg, #38bdf8, #8b5cf6)', borderRadius: 3, flexShrink: 0 }} />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 20 }}>
          {points.map((point, index) => (
            <RevealPointCard key={index} point={point} index={index} emphasisWords={data.emphasisWords || []} />
          ))}
        </div>
        {data.emphasisWords && data.emphasisWords.length > 0 && (
          <div style={{
            width: 280, flexShrink: 0, background: 'rgba(56,189,248,0.08)', borderRadius: 16,
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
            border: '1px solid rgba(56,189,248,0.15)',
          }}>
            <div style={{ fontSize: 32, fontWeight: 800, color: '#38bdf8', textAlign: 'center' }}>{data.emphasisWords[0]}</div>
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
}

// ── 大数字页 ───────────────────────────────────────────────────────

export function StatsSlide({ data }: { data: SlideData }) {
  const stats = data.stats || [];

  return (
    <AbsoluteFill>
      <PremiumBg variant="gradient" />
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', padding: '0 80px' }}>
        <div style={{ fontSize: 28, color: '#94a3b8', marginBottom: 40, letterSpacing: 4, textTransform: 'uppercase' }}>{data.title}</div>
        <div style={{ display: 'flex', gap: 80, justifyContent: 'center' }}>
          {stats.map((stat, index) => (
            <StatCard key={index} stat={stat} index={index} />
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
}

// ── 金句页 ─────────────────────────────────────────────────────────

export function QuoteSlide({ data }: { data: SlideData }) {
  const a1 = useReveal(0);
  const a2 = useReveal(15);

  return (
    <AbsoluteFill>
      <PremiumBg variant="dark" />
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', padding: '0 160px' }}>
        <div style={{ fontSize: 72, color: '#38bdf8', opacity: 0.3, marginBottom: -20 }}>“</div>
        <div style={{ fontSize: 44, color: '#f1f5f9', textAlign: 'center', lineHeight: 1.6, fontStyle: 'italic', opacity: a1.opacity, transform: `translateY(${a1.y}px)` }}>
          <Highlight text={data.quote || ''} words={data.emphasisWords || []} />
        </div>
        <div style={{ width: 60, height: 3, background: 'linear-gradient(90deg, #38bdf8, #8b5cf6)', borderRadius: 2, margin: '30px 0 16px', opacity: a2.opacity }} />
        {data.author && <div style={{ fontSize: 18, color: '#64748b', opacity: a2.opacity }}>&mdash; {data.author}</div>}
      </div>
    </AbsoluteFill>
  );
}

// ── 对比页 ─────────────────────────────────────────────────────────

export function VersusSlide({ data }: { data: SlideData }) {
  return (
    <AbsoluteFill>
      <PremiumBg variant="dark" />
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 100, background: 'linear-gradient(90deg, #1e3a5f, #2563eb)', display: 'flex', alignItems: 'center', padding: '0 80px' }}>
        <div style={{ fontSize: 36, fontWeight: 700, color: '#fff' }}>{data.title}</div>
      </div>
      <div style={{ position: 'absolute', top: 130, left: 80, right: 80, bottom: 60, display: 'flex', gap: 40 }}>
        {[
          { title: data.leftTitle || '', items: data.leftPoints || [], color: '#2563eb' },
          { title: data.rightTitle || '', items: data.rightPoints || [], color: '#8b5cf6' },
        ].map((column, index) => (
          <VersusColumn
            key={index}
            title={column.title}
            items={column.items}
            color={column.color}
            emphasisWords={data.emphasisWords || []}
            index={index}
          />
        ))}
      </div>
    </AbsoluteFill>
  );
}

// ── 结尾页 ─────────────────────────────────────────────────────────

export function ClosingSlide({ data }: { data: SlideData }) {
  const a1 = useReveal(0);
  const a2 = useReveal(15);

  return (
    <AbsoluteFill>
      <PremiumBg variant="gradient" />
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center' }}>
        <div style={{ fontSize: 64, fontWeight: 900, background: 'linear-gradient(135deg, #38bdf8, #a78bfa)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', opacity: a1.opacity, transform: `translateY(${a1.y}px)` }}>
          {data.title}
        </div>
        <div style={{ width: 80, height: 3, background: 'linear-gradient(90deg, #38bdf8, #8b5cf6)', borderRadius: 2, margin: '24px 0 16px', opacity: a2.opacity }} />
        <div style={{ fontSize: 20, color: '#94a3b8', opacity: a2.opacity }}>{data.subtitle || '期待与您合作'}</div>
        {data.points && data.points.length > 0 && (
          <div style={{ marginTop: 30, opacity: a2.opacity }}>
            {data.points.map((p, i) => (
              <div key={i} style={{ fontSize: 16, color: '#64748b', marginBottom: 6, textAlign: 'center' }}>{p}</div>
            ))}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
}

// ── 路由器 ─────────────────────────────────────────────────────────

export function PremiumSlideRenderer({ data }: { data: SlideData }) {
  switch (data.layout) {
    case 'hero': return <HeroSlide data={data} />;
    case 'points': return <PointsSlide data={data} />;
    case 'stats': return <StatsSlide data={data} />;
    case 'quote': return <QuoteSlide data={data} />;
    case 'versus': return <VersusSlide data={data} />;
    case 'closing': return <ClosingSlide data={data} />;
    default: return <PointsSlide data={data} />;
  }
}
