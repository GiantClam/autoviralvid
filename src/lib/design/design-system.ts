/**
 * PPT 设计系统 — 配色方案 + 字体对 + 背景模板
 *
 * 借鉴 OpenMAIC 的 SlideTheme + Gradient + Shadow 系统
 */

// ── 配色方案 ───────────────────────────────────────────────────────

export interface ColorPalette {
  name: string;
  primary: string;
  secondary: string;
  accent: string;
  background: string;
  text: string;
  textSecondary: string;
  themeColors: string[]; // 5色主题
}

export const COLOR_PALETTES: Record<string, ColorPalette> = {
  // 商务蓝 — 经典企业风格
  businessBlue: {
    name: '商务蓝',
    primary: '#1e3a5f',
    secondary: '#2563eb',
    accent: '#38bdf8',
    background: '#ffffff',
    text: '#1e293b',
    textSecondary: '#64748b',
    themeColors: ['#1e3a5f', '#2563eb', '#38bdf8', '#f59e0b', '#64748b'],
  },
  // 科技深蓝 — 深色科技感
  techDark: {
    name: '科技深蓝',
    primary: '#0f172a',
    secondary: '#1e3a5f',
    accent: '#38bdf8',
    background: '#0f172a',
    text: '#e2e8f0',
    textSecondary: '#94a3b8',
    themeColors: ['#38bdf8', '#8b5cf6', '#22c55e', '#f59e0b', '#e2e8f0'],
  },
  // 优雅紫 — 高端品牌
  elegantPurple: {
    name: '优雅紫',
    primary: '#581c87',
    secondary: '#7c3aed',
    accent: '#a78bfa',
    background: '#faf5ff',
    text: '#1e1b4b',
    textSecondary: '#6b7280',
    themeColors: ['#581c87', '#7c3aed', '#a78bfa', '#f59e0b', '#6b7280'],
  },
  // 活力橙 — 创意营销
  vibrantOrange: {
    name: '活力橙',
    primary: '#c2410c',
    secondary: '#ea580c',
    accent: '#fb923c',
    background: '#fffbeb',
    text: '#1c1917',
    textSecondary: '#78716c',
    themeColors: ['#c2410c', '#ea580c', '#fb923c', '#0ea5e9', '#78716c'],
  },
  // 清新绿 — 教育环保
  freshGreen: {
    name: '清新绿',
    primary: '#166534',
    secondary: '#16a34a',
    accent: '#4ade80',
    background: '#f0fdf4',
    text: '#14532d',
    textSecondary: '#6b7280',
    themeColors: ['#166534', '#16a34a', '#4ade80', '#0ea5e9', '#6b7280'],
  },
  // 暖红 — 品牌活动
  warmRed: {
    name: '暖红',
    primary: '#991b1b',
    secondary: '#dc2626',
    accent: '#f87171',
    background: '#fef2f2',
    text: '#1c1917',
    textSecondary: '#78716c',
    themeColors: ['#991b1b', '#dc2626', '#f87171', '#f59e0b', '#78716c'],
  },
};

// ── 字体对 ─────────────────────────────────────────────────────────

export interface FontPair {
  name: string;
  heading: string;
  body: string;
}

export const FONT_PAIRS: FontPair[] = [
  { name: 'Microsoft', heading: 'Microsoft YaHei', body: 'Microsoft YaHei' },
  { name: '思源黑体', heading: 'Source Han Sans CN', body: 'Source Han Sans CN' },
  { name: 'Arial组合', heading: 'Arial Black', body: 'Arial' },
  { name: 'Times组合', heading: 'Georgia', body: 'Times New Roman' },
  { name: '现代无衬线', heading: 'Helvetica', body: 'Helvetica' },
];

// ── 背景模板 ───────────────────────────────────────────────────────

export interface BackgroundTemplate {
  name: string;
  type: 'solid' | 'gradient' | 'pattern';
  config: {
    color?: string;
    gradient?: { type: 'linear' | 'radial'; colors: { pos: number; color: string }[]; rotate: number };
    patternSvg?: string;
  };
}

export const BACKGROUND_TEMPLATES: BackgroundTemplate[] = [
  // 纯色
  { name: '纯白', type: 'solid', config: { color: '#ffffff' } },
  { name: '深蓝', type: 'solid', config: { color: '#0f172a' } },
  { name: '浅灰', type: 'solid', config: { color: '#f8fafc' } },
  // 渐变
  {
    name: '蓝紫渐变',
    type: 'gradient',
    config: {
      gradient: {
        type: 'linear',
        colors: [{ pos: 0, color: '#1e3a5f' }, { pos: 100, color: '#581c87' }],
        rotate: 135,
      },
    },
  },
  {
    name: '深空渐变',
    type: 'gradient',
    config: {
      gradient: {
        type: 'linear',
        colors: [{ pos: 0, color: '#0f172a' }, { pos: 50, color: '#1e293b' }, { pos: 100, color: '#334155' }],
        rotate: 180,
      },
    },
  },
  {
    name: '日出渐变',
    type: 'gradient',
    config: {
      gradient: {
        type: 'linear',
        colors: [{ pos: 0, color: '#fef3c7' }, { pos: 100, color: '#fde68a' }],
        rotate: 0,
      },
    },
  },
  {
    name: '海洋渐变',
    type: 'gradient',
    config: {
      gradient: {
        type: 'linear',
        colors: [{ pos: 0, color: '#0c4a6e' }, { pos: 100, color: '#0369a1' }],
        rotate: 180,
      },
    },
  },
  {
    name: '森林渐变',
    type: 'gradient',
    config: {
      gradient: {
        type: 'linear',
        colors: [{ pos: 0, color: '#14532d' }, { pos: 100, color: '#166534' }],
        rotate: 135,
      },
    },
  },
];

// ── 渐变文字 ───────────────────────────────────────────────────────

export interface GradientText {
  from: string;
  to: string;
  angle: number;
}

export const GRADIENT_TEXT_PRESETS: GradientText[] = [
  { from: '#3b82f6', to: '#8b5cf6', angle: 90 },
  { from: '#f59e0b', to: '#ef4444', angle: 90 },
  { from: '#22c55e', to: '#06b6d4', angle: 90 },
  { from: '#ec4899', to: '#8b5cf6', angle: 90 },
];

// ── 图表预设色板 ───────────────────────────────────────────────────

export const CHART_COLOR_PRESETS = [
  ['#2563eb', '#7c3aed', '#06b6d4', '#22c55e', '#f59e0b', '#ef4444', '#ec4899', '#8b5cf6'],
  ['#1e3a5f', '#ea580c', '#6b7280', '#facc15', '#0ea5e9'],
  ['#0f172a', '#38bdf8', '#a78bfa', '#4ade80', '#fb923c'],
];
