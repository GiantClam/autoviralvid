/**
 * Remotion 语义化布局组件库
 *
 * 核心思想: 用 React + CSS Flex/Grid 实现自适应排版
 * 不使用绝对坐标，根据 layoutType 自动渲染精美布局
 */

import React from 'react';
import { AbsoluteFill, Img, useCurrentFrame, useVideoConfig, spring, interpolate } from 'remotion';

// ── Types ──────────────────────────────────────────────────────────

export type LayoutType = 'cover' | 'bullet_points' | 'split_left_img' | 'split_right_img' | 'quote' | 'comparison' | 'big_number';

export interface ComparisonData {
  leftTitle: string; leftItems: string[];
  rightTitle: string; rightItems: string[];
}

export interface BigNumberData {
  number: string; unit: string; description: string;
}

export interface VisualContent {
  title: string; subtitle?: string;
  bodyText?: string[]; imageUrl?: string;
  comparison?: ComparisonData; bigNumber?: BigNumberData;
  bgStyle?: 'light' | 'dark' | 'gradient';
}

export interface SlideContentV5 {
  id: string; order: number;
  layoutType: LayoutType; content: VisualContent;
  narration: string; narrationAudioUrl?: string;
  emphasisWords: string[]; duration: number;
}

// ── 配色 ───────────────────────────────────────────────────────────

const COLORS = {
  primary: '#1e3a5f', secondary: '#2563eb', accent: '#38bdf8',
  text: '#1e293b', textLight: '#64748b',
  white: '#ffffff', bgLight: '#ffffff', bgDark: '#0f172a',
};

function getBgStyle(bg?: string): React.CSSProperties {
  if (bg === 'dark') return { backgroundColor: COLORS.bgDark };
  if (bg === 'gradient') return {
    background: `linear-gradient(135deg, ${COLORS.bgDark}, ${COLORS.primary})`,
  };
  return { backgroundColor: COLORS.bgLight };
}

function getTextColor(bg?: string): string {
  return bg === 'dark' || bg === 'gradient' ? COLORS.white : COLORS.text;
}

// ── 交错入场动画 ───────────────────────────────────────────────────

function useStagger(index: number) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const delay = Math.round(index * 0.15 * fps);
  const progress = spring({ frame: frame - delay, fps, config: { damping: 200, stiffness: 120 } });
  return {
    opacity: interpolate(progress, [0, 1], [0, 1], { extrapolateRight: 'clamp' }),
    translateY: interpolate(progress, [0, 1], [20, 0], { extrapolateRight: 'clamp' }),
  };
}

function StaggeredTextRow({ text, emphasisWords, style, prefix = '', index }: {
  text: string;
  emphasisWords: string[];
  style: React.CSSProperties;
  prefix?: string;
  index: number;
}) {
  const anim = useStagger(index);
  return (
    <div style={{
      ...style,
      opacity: anim.opacity,
      transform: `translateY(${anim.translateY}px)`,
    }}>
      <HighlightText text={`${prefix}${text}`} emphasisWords={emphasisWords} style={{ color: style.color || COLORS.text }} />
    </div>
  );
}

function ComparisonColumn({ title, items, color, emphasisWords }: {
  title: string;
  items: string[];
  color: string;
  emphasisWords: string[];
}) {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
      <div style={{ backgroundColor: color, borderRadius: 8, padding: '10px 16px', marginBottom: 16 }}>
        <div style={{ fontSize: 20, fontWeight: 700, color: COLORS.white }}>{title}</div>
      </div>
      {items.map((item, index) => (
        <StaggeredTextRow
          key={`${title}-${index}`}
          text={item}
          emphasisWords={emphasisWords}
          prefix="✓ "
          index={index}
          style={{ fontSize: 18, color: COLORS.text, padding: '6px 0', lineHeight: 1.5 }}
        />
      ))}
    </div>
  );
}

// ── 文本高亮组件 ───────────────────────────────────────────────────

function HighlightText({ text, emphasisWords, style }: {
  text: string; emphasisWords: string[]; style: React.CSSProperties;
}) {
  if (!emphasisWords.length) return <span style={style}>{text}</span>;

  // 用正则按 emphasisWords 切分
  const pattern = emphasisWords.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
  const regex = new RegExp(`(${pattern})`, 'gi');
  const parts = text.split(regex);

  return (
    <span style={style}>
      {parts.map((part, i) => {
        const isEmphasis = emphasisWords.some(w => w.toLowerCase() === part.toLowerCase());
        return isEmphasis ? (
          <span key={i} style={{
            color: COLORS.secondary, fontWeight: 700,
            backgroundColor: 'rgba(37,99,235,0.1)', padding: '0 4px', borderRadius: 4,
          }}>
            {part}
          </span>
        ) : <span key={i}>{part}</span>;
      })}
    </span>
  );
}

// ── 封面布局 ───────────────────────────────────────────────────────

export function CoverLayout({ content }: { content: VisualContent }) {
  const anim = useStagger(0);
  const isDark = content.bgStyle === 'dark' || content.bgStyle === 'gradient';

  return (
    <AbsoluteFill style={{
      ...getBgStyle(content.bgStyle),
      display: 'flex', flexDirection: 'column',
      justifyContent: 'center', alignItems: 'flex-start',
      padding: '0 80px',
    }}>
      {/* 装饰圆 */}
      <div style={{
        position: 'absolute', right: -100, top: -100,
        width: 500, height: 500, borderRadius: '50%',
        backgroundColor: COLORS.accent, opacity: 0.08,
      }} />
      {/* 标题 */}
      <div style={{
        fontSize: 56, fontWeight: 700,
        color: isDark ? COLORS.white : COLORS.text,
        opacity: anim.opacity, transform: `translateY(${anim.translateY}px)`,
        zIndex: 2,
      }}>
        {content.title}
      </div>
      {/* 装饰线 */}
      <div style={{
        width: 100, height: 4, backgroundColor: COLORS.accent,
        borderRadius: 2, margin: '16px 0', opacity: anim.opacity,
      }} />
      {/* 副标题 */}
      {content.subtitle && (
        <div style={{
          fontSize: 24, color: COLORS.accent, fontWeight: 400,
          opacity: anim.opacity, transform: `translateY(${anim.translateY}px)`,
          zIndex: 2,
        }}>
          {content.subtitle}
        </div>
      )}
    </AbsoluteFill>
  );
}

// ── 要点列表布局 ───────────────────────────────────────────────────

export function BulletPointsLayout({ content, emphasisWords }: {
  content: VisualContent; emphasisWords: string[];
}) {
  const items = content.bodyText || [];

  return (
    <AbsoluteFill style={{ ...getBgStyle(content.bgStyle) }}>
      {/* 标题栏 */}
      <div style={{
        backgroundColor: COLORS.primary, height: 80,
        display: 'flex', alignItems: 'center', padding: '0 60px',
      }}>
        <div style={{ fontSize: 30, fontWeight: 700, color: COLORS.white }}>
          {content.title}
        </div>
      </div>
      {/* 内容区 */}
      <div style={{ display: 'flex', flex: 1, padding: '30px 60px' }}>
        {/* 左侧强调竖条 */}
        <div style={{
          width: 5, borderRadius: 3, backgroundColor: COLORS.accent, flexShrink: 0,
          height: `${Math.min(items.length * 50, 400)}px`, marginRight: 20, marginTop: 10,
        }} />
        {/* 要点列表 */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {items.map((item, index) => (
            <StaggeredTextRow
              key={index}
              text={item}
              emphasisWords={emphasisWords}
              prefix="• "
              index={index}
              style={{ fontSize: 20, lineHeight: 1.5, paddingLeft: 8, color: getTextColor(content.bgStyle) }}
            />
          ))}
        </div>
        {/* 右侧高亮数据 */}
        {emphasisWords.length > 0 && (
          <div style={{
            width: 280, flexShrink: 0,
            backgroundColor: `${COLORS.accent}22`, borderRadius: 12,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: 20, marginLeft: 20,
          }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.primary, textAlign: 'center' }}>
              {emphasisWords[0]}
            </div>
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
}

// ── 对比布局 ───────────────────────────────────────────────────────

export function ComparisonLayout({ content, emphasisWords }: {
  content: VisualContent; emphasisWords: string[];
}) {
  const comp = content.comparison;
  if (!comp) return <BulletPointsLayout content={content} emphasisWords={emphasisWords} />;

  return (
    <AbsoluteFill style={{ ...getBgStyle(content.bgStyle) }}>
      {/* 标题栏 */}
      <div style={{
        backgroundColor: COLORS.primary, height: 80,
        display: 'flex', alignItems: 'center', padding: '0 60px',
      }}>
        <div style={{ fontSize: 30, fontWeight: 700, color: COLORS.white }}>{content.title}</div>
      </div>
      {/* 双栏 */}
      <div style={{ display: 'flex', flex: 1, padding: '20px 60px', gap: 30 }}>
        {/* 左栏 */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <div style={{
            backgroundColor: COLORS.secondary, borderRadius: 8,
            padding: '10px 16px', marginBottom: 16,
          }}>
            <div style={{ fontSize: 20, fontWeight: 700, color: COLORS.white }}>{comp.leftTitle}</div>
          </div>
          {comp.leftItems.map((item, index) => (
            <StaggeredTextRow
              key={`left-${index}`}
              text={item}
              emphasisWords={emphasisWords}
              prefix="✓ "
              index={index}
              style={{ fontSize: 18, color: COLORS.text, padding: '6px 0', lineHeight: 1.5 }}
            />
          ))}
        </div>
        {/* 右栏 */}
        <ComparisonColumn title={comp.rightTitle} items={comp.rightItems} color={COLORS.accent} emphasisWords={emphasisWords} />
      </div>
    </AbsoluteFill>
  );
}

// ── 名言布局 ───────────────────────────────────────────────────────

export function QuoteLayout({ content, emphasisWords }: {
  content: VisualContent; emphasisWords: string[];
}) {
  const text = content.bodyText?.[0] || content.title;

  return (
    <AbsoluteFill style={{
      ...getBgStyle('dark'), display: 'flex', flexDirection: 'column',
      justifyContent: 'center', alignItems: 'center', padding: '0 120px',
    }}>
      <div style={{ fontSize: 64, color: COLORS.accent, marginBottom: -20, opacity: 0.6 }}>“</div>
      <div style={{ fontSize: 32, color: COLORS.white, textAlign: 'center', lineHeight: 1.6 }}>
        <HighlightText text={text} emphasisWords={emphasisWords}
          style={{ color: COLORS.white }} />
      </div>
      <div style={{
        width: 120, height: 3, backgroundColor: COLORS.accent,
        borderRadius: 2, margin: '24px 0 16px',
      }} />
      {content.subtitle && (
        <div style={{ fontSize: 18, color: COLORS.textLight }}>—— {content.subtitle}</div>
      )}
    </AbsoluteFill>
  );
}

// ── 大数字布局 ─────────────────────────────────────────────────────

export function BigNumberLayout({ content }: { content: VisualContent }) {
  const anim = useStagger(0);
  const bn = content.bigNumber;

  return (
    <AbsoluteFill style={{ ...getBgStyle(content.bgStyle) }}>
      {/* 标题栏 */}
      <div style={{
        backgroundColor: COLORS.primary, height: 80,
        display: 'flex', alignItems: 'center', padding: '0 60px',
      }}>
        <div style={{ fontSize: 30, fontWeight: 700, color: COLORS.white }}>{content.title}</div>
      </div>
      {/* 大数字 */}
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        justifyContent: 'center', alignItems: 'center',
      }}>
        {bn && (
          <>
            <div style={{
              fontSize: 100, fontWeight: 900, color: COLORS.secondary,
              opacity: anim.opacity, transform: `scale(${anim.opacity})`,
            }}>
              {bn.number}
            </div>
            {bn.unit && <div style={{ fontSize: 22, color: COLORS.textLight, marginTop: -10 }}>{bn.unit}</div>}
            {bn.description && <div style={{ fontSize: 18, color: COLORS.text, marginTop: 20, textAlign: 'center', maxWidth: 600 }}>{bn.description}</div>}
          </>
        )}
      </div>
    </AbsoluteFill>
  );
}

// ── 图文分栏布局 ───────────────────────────────────────────────────

export function SplitImageLayout({ content, emphasisWords, imagePos = 'left' }: {
  content: VisualContent; emphasisWords: string[]; imagePos?: 'left' | 'right';
}) {
  const items = content.bodyText || [];
  const textBlock = (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '0 40px', gap: 10 }}>
      {items.map((item, index) => (
        <StaggeredTextRow
          key={index}
          text={item}
          emphasisWords={emphasisWords}
          prefix="• "
          index={index}
          style={{ fontSize: 18, lineHeight: 1.5, color: getTextColor(content.bgStyle) }}
        />
      ))}
    </div>
  );

  const imageBlock = content.imageUrl ? (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
      <Img src={content.imageUrl}
        style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', borderRadius: 12 }} />
    </div>
  ) : (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
      backgroundColor: '#e2e8f0', borderRadius: 12, margin: 20 }}>
      <span style={{ fontSize: 14, color: COLORS.textLight }}>Image Placeholder</span>
    </div>
  );

  return (
    <AbsoluteFill style={{ ...getBgStyle(content.bgStyle) }}>
      {/* 标题栏 */}
      <div style={{
        backgroundColor: COLORS.primary, height: 80,
        display: 'flex', alignItems: 'center', padding: '0 60px',
      }}>
        <div style={{ fontSize: 30, fontWeight: 700, color: COLORS.white }}>{content.title}</div>
      </div>
      {/* 内容区 */}
      <div style={{ display: 'flex', flex: 1 }}>
        {imagePos === 'left' ? <>{imageBlock}{textBlock}</> : <>{textBlock}{imageBlock}</>}
      </div>
    </AbsoluteFill>
  );
}

// ── 布局路由器 ─────────────────────────────────────────────────────

export function SlideLayoutRenderer({ slide }: { slide: SlideContentV5 }) {
  switch (slide.layoutType) {
    case 'cover': return <CoverLayout content={slide.content} />;
    case 'bullet_points': return <BulletPointsLayout content={slide.content} emphasisWords={slide.emphasisWords} />;
    case 'comparison': return <ComparisonLayout content={slide.content} emphasisWords={slide.emphasisWords} />;
    case 'quote': return <QuoteLayout content={slide.content} emphasisWords={slide.emphasisWords} />;
    case 'big_number': return <BigNumberLayout content={slide.content} />;
    case 'split_left_img': return <SplitImageLayout content={slide.content} emphasisWords={slide.emphasisWords} imagePos="left" />;
    case 'split_right_img': return <SplitImageLayout content={slide.content} emphasisWords={slide.emphasisWords} imagePos="right" />;
    default: return <BulletPointsLayout content={slide.content} emphasisWords={slide.emphasisWords} />;
  }
}
