/**
 * 动作引擎 + 多角色字幕 — Remotion 组件
 *
 * 动作: spotlight, draw_circle, underline, zoom_in
 * 字幕: host (蓝色), student (绿色), expert (紫色)
 * 语义区域: title_area, bullet_1, bullet_2, image_area, etc.
 */

import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, spring, Audio } from 'remotion';

// ── Types ──────────────────────────────────────────────────────────

export type RoleType = 'host' | 'student' | 'expert';
export type ActionType = 'none' | 'spotlight' | 'draw_circle' | 'underline' | 'zoom_in';

export interface DialogueLine {
  role: RoleType;
  text: string;
  targetElementId?: string;
  action: ActionType;
  audioUrl?: string;
  audioDuration?: number;
}

export interface ScriptSegment {
  line: DialogueLine;
  startFrame: number;
  durationFrames: number;
}

// ── 角色样式 ───────────────────────────────────────────────────────

const ROLE_STYLES: Record<RoleType, { color: string; label: string; bg: string }> = {
  host: { color: '#2563eb', label: '导师', bg: 'rgba(37,99,235,0.1)' },
  student: { color: '#16a34a', label: '学生', bg: 'rgba(22,163,74,0.1)' },
  expert: { color: '#7c3aed', label: '专家', bg: 'rgba(124,58,237,0.1)' },
};

// ── 语义区域注册表 ─────────────────────────────────────────────────
// 每种 LayoutType 为其子元素预设标准 ID
// Remotion 组件渲染时注册自己的区域，动作引擎读取后定位

export const LAYOUT_ZONES: Record<string, string[]> = {
  cover: ['title_area', 'subtitle_area'],
  bullet_points: ['title_area', 'bullet_1', 'bullet_2', 'bullet_3', 'bullet_4', 'bullet_5'],
  comparison: ['title_area', 'left_column', 'right_column'],
  quote: ['quote_text', 'author_area'],
  split_image: ['title_area', 'image_area', 'text_area'],
  qa_transition: ['question_area'],
};

// ── 动作: 画红圈 ───────────────────────────────────────────────────

export function DrawCircleAction({ width = 200, height = 200 }: {
  targetArea?: string; width?: number; height?: number;
}) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const progress = spring({ frame, fps, config: { damping: 15, stiffness: 80 } });
  const strokeDashoffset = interpolate(progress, [0, 1], [600, 0], { extrapolateRight: 'clamp' });
  const opacity = interpolate(frame, [0, 10], [0, 1], { extrapolateRight: 'clamp' });

  return (
    <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 100, opacity }}>
      <svg width={width} height={height} style={{ position: 'absolute', left: '50%', top: '50%', transform: 'translate(-50%, -50%)' }}>
        <ellipse
          cx={width / 2} cy={height / 2}
          rx={width / 2 - 10} ry={height / 2 - 10}
          fill="none" stroke="#ef4444" strokeWidth={4}
          strokeDasharray="600" strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}

// ── 动作: 聚光灯 ───────────────────────────────────────────────────

export function SpotlightAction({ children }: { children: React.ReactNode }) {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 15], [0, 0.6], { extrapolateRight: 'clamp' });

  return (
    <div style={{ position: 'relative' }}>
      {children}
      <div style={{
        position: 'absolute', inset: -20, borderRadius: 16,
        boxShadow: `0 0 60px 20px rgba(37,99,235,${opacity})`,
        pointerEvents: 'none', zIndex: 50,
      }} />
    </div>
  );
}

// ── 动作: 下划线 ───────────────────────────────────────────────────

export function UnderlineAction({ width = 300 }: { width?: number }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const progress = spring({ frame, fps, config: { damping: 200, stiffness: 100 } });
  const lineWidth = interpolate(progress, [0, 1], [0, width], { extrapolateRight: 'clamp' });

  return (
    <div style={{ position: 'absolute', bottom: -4, left: 0, height: 3, width: lineWidth, backgroundColor: '#ef4444', borderRadius: 2, zIndex: 100 }} />
  );
}

// ── 多角色字幕条 ───────────────────────────────────────────────────

export function SubtitleBar({ role, text }: { role: RoleType; text: string }) {
  const frame = useCurrentFrame();
  const style = ROLE_STYLES[role];
  const opacity = interpolate(frame, [0, 8], [0, 1], { extrapolateRight: 'clamp' });
  const translateY = interpolate(frame, [0, 8], [20, 0], { extrapolateRight: 'clamp' });

  return (
    <div style={{
      position: 'absolute', bottom: 30, left: '50%', transform: `translateX(-50%) translateY(${translateY}px)`,
      opacity, zIndex: 200, display: 'flex', alignItems: 'center', gap: 12,
      backgroundColor: 'rgba(0,0,0,0.85)', borderRadius: 12, padding: '10px 24px',
      maxWidth: '80%', backdropFilter: 'blur(8px)',
    }}>
      {/* 角色标签 */}
      <div style={{
        backgroundColor: style.color, color: '#fff', fontSize: 12, fontWeight: 700,
        padding: '3px 10px', borderRadius: 6, flexShrink: 0,
      }}>
        {style.label}
      </div>
      {/* 台词 */}
      <div style={{ fontSize: 16, color: '#f1f5f9', lineHeight: 1.4 }}>{text}</div>
    </div>
  );
}

// ── 剧本播放器 ─────────────────────────────────────────────────────

export function ScriptPlayer({ script, segments, visualContent }: {
  script: DialogueLine[];
  segments: ScriptSegment[];
  visualContent?: React.ReactNode;
}) {
  const frame = useCurrentFrame();

  // 找到当前活跃的对话
  let activeIdx = 0;
  for (let i = segments.length - 1; i >= 0; i--) {
    if (frame >= segments[i].startFrame) {
      activeIdx = i;
      break;
    }
  }

  const activeLine = script[activeIdx] || script[0];
  const activeSegment = segments[activeIdx] || segments[0];

  return (
    <AbsoluteFill>
      {/* 视觉内容 */}
      {visualContent}

      {/* 当前台词的音频 */}
      {activeLine?.audioUrl && frame >= (activeSegment?.startFrame || 0) && (
        <Audio src={activeLine.audioUrl} volume={1} />
      )}

      {/* 动作效果 */}
      {activeLine?.action === 'draw_circle' && <DrawCircleAction />}
      {activeLine?.action === 'spotlight' && <SpotlightAction><div /></SpotlightAction>}

      {/* 字幕条 */}
      {activeLine && <SubtitleBar role={activeLine.role} text={activeLine.text} />}
    </AbsoluteFill>
  );
}
