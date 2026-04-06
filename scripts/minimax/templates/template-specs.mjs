const DEFAULT_TEMPLATE_SPEC = {
  cardRadius: 0.08,
  borderWidth: 0.6,
  accentWidth: 0.05,
  panelGap: 0.16,
  contentTop: 0.92,
  contentBottom: 5.28,
};

export const TEMPLATE_SPECS = {
  hero_tech_cover: {
    badge: { x: 0.62, y: 0.96, w: 1.48, h: 0.28, radius: 0.14 },
    title: { x: 0.66, y: 1.32, w: 6.28, h: 1.6, fontSizeLong: 34, fontSizeShort: 42 },
    subtitle: { x: 0.66, y: 3.05, w: 5.9, h: 0.58, fontSize: 17 },
    divider: { x: 0.66, y: 3.62, w: 0.95, h: 0.06 },
    footer: { x: 0.66, y: 4.78, w: 8.8, h: 0.28, fontSize: 12 },
    ghostYear: { x: 5.4, y: 4.66, w: 3.9, h: 0.54, fontSize: 44 },
    orbit: { x: 7.05, y: 0.08, w: 2.6, h: 2.2, radius: 1.1 },
  },
  architecture_dark_panel: {
    board: { x: 0.58, y: 0.9, w: 7.24, h: 4.34, radius: 0.08, borderWidth: 0.75 },
    row: { h: 1.19, gap: 0.16, radius: 0.06, borderWidth: 0.58 },
    leftAccent: { xOffset: 0.03, yOffset: 0.12, w: 0.04, h: 0.95 },
    rowTitle: { xOffset: 0.18, yOffset: 0.12, w: 0.9, h: 0.24, fontSize: 12 },
    rowBody: { xOffset: 0.18, yOffset: 0.4, w: 4.22, h: 0.68, fontSize: 16 },
    connector: { xOffset: 5.05, yOffset: 0.58, w: 1.62, h: 0, pt: 1.0, dash: "dot" },
    rightPanel: { x: 8.02, y: 0.9, w: 1.32, h: 4.34, radius: 0.08, borderWidth: 0.88 },
    rightTitle: { x: 8.14, y: 1.26, w: 1.04, h: 0.38, fontSize: 20 },
    rightItems: { x: 8.13, y: 1.97, w: 1.06, h: 0.32, step: 0.91, fontSize: 14 },
  },
  ecosystem_orange_dark: {
    leftCard: { x: 0.58, y: 0.94, w: 2.95, h: 3.86, radius: 0.09, borderWidth: 0.65 },
    kpiNumber: { x: 0.8, y: 1.44, w: 2.32, h: 0.82, fontSize: 58 },
    kpiLabel: { x: 2.48, y: 1.93, w: 1.0, h: 0.32, fontSize: 18 },
    kpiBullets: { x: 0.82, y: 2.61, w: 2.56, h: 0.32, step: 0.42, fontSize: 14 },
    rightCard: { x: 3.72, y: 0.94, w: 5.58, h: 3.86, radius: 0.09, borderWidth: 0.65 },
    centerPill: { x: 5.36, y: 2.24, w: 2.32, h: 0.58, radius: 0.29, fontSize: 22 },
    nodeCircle: { w: 0.9, h: 0.9, borderWidth: 1.1 },
    nodes: [
      { t: "人", x: 6.21, y: 1.18 },
      { t: "车", x: 4.61, y: 3.08 },
      { t: "家", x: 7.81, y: 3.08 },
    ],
    bottomStrip: { x: 3.72, y: 4.96, w: 5.58, h: 0.44, itemGap: 0.14, itemRadius: 0.08, fontSize: 12 },
  },
  neural_blueprint_light: {
    left: { x: 0.64, y: 1.02, w: 2.95, h: 2.35, radius: 0.08 },
    right: { x: 3.74, y: 1.02, w: 5.56, h: 2.35, radius: 0.08 },
    lowerLeft: { x: 0.64, y: 3.62, w: 4.18, h: 1.68, radius: 0.08 },
    lowerRight: { x: 5.0, y: 3.62, w: 4.3, h: 1.68, radius: 0.08 },
  },
  ops_lifecycle_light: {
    grid: [
      { x: 0.64, y: 0.98, w: 4.22, h: 2.02 },
      { x: 5.02, y: 0.98, w: 4.28, h: 2.02 },
      { x: 0.64, y: 3.14, w: 4.22, h: 2.02 },
      { x: 5.02, y: 3.14, w: 4.28, h: 2.02 },
    ],
    title: { xOffset: 0.22, yOffset: 0.24, h: 0.3, fontSize: 20 },
    badge: { xOffset: 0.22, yOffset: 0.62, w: 1.2, h: 0.32, radius: 0.16, fontSize: 12 },
    dashedBox: { xOffset: 0.22, yOffset: 0.78, h: 1.08, radius: 0.06, borderWidth: 0.5 },
    list: { xOffset: 0.26, yOffset: 1.02, wPad: 0.52, h: 0.68, fontSize: 12, step: 0.24 },
  },
  consulting_warm_light: {
    heroRule: { x: 0.64, y: 1.0, w: 8.66, h: 0.46, radius: 0.06 },
    topGrid: { x: 0.64, y: 1.62, cardW: 2.02, cardH: 1.8, gap: 0.12 },
    bottomCards: [
      { x: 0.64, y: 3.58, w: 2.95, h: 1.68 },
      { x: 3.76, y: 3.58, w: 2.6, h: 1.68 },
      { x: 6.52, y: 3.58, w: 2.78, h: 1.68 },
    ],
  },
  split_media_dark: {
    left: { x: 0.64, y: 1.0, w: 4.18, h: 4.18, radius: 0.08 },
    right: { x: 4.98, y: 1.0, w: 4.32, h: 4.18, radius: 0.08 },
  },
  dashboard_dark: {
    canvas: { x: 0.64, y: 0.96, w: 8.66, h: 4.28, radius: 0.08 },
    kpiCards: [
      { x: 0.86, y: 1.12, w: 2.66, h: 1.0 },
      { x: 3.68, y: 1.12, w: 2.66, h: 1.0 },
      { x: 6.5, y: 1.12, w: 2.58, h: 1.0 },
    ],
    left: { x: 0.86, y: 2.32, w: 3.28, h: 2.74, radius: 0.08 },
    chart: { x: 4.34, y: 2.32, w: 4.74, h: 2.74, radius: 0.08 },
  },
  kpi_dashboard_dark: {
    canvas: { x: 0.62, y: 0.94, w: 8.7, h: 4.32, radius: 0.08 },
    kpiCards: [
      { x: 0.84, y: 1.12, w: 2.72, h: 1.04 },
      { x: 3.68, y: 1.12, w: 2.72, h: 1.04 },
      { x: 6.52, y: 1.12, w: 2.62, h: 1.04 },
    ],
    chart: { x: 0.84, y: 2.36, w: 8.3, h: 2.74, radius: 0.08 },
  },
  image_showcase_light: {
    hero: { x: 0.68, y: 1.04, w: 5.72, h: 3.98, radius: 0.08 },
    sideTop: { x: 6.58, y: 1.04, w: 2.72, h: 1.88, radius: 0.08 },
    sideBottom: { x: 6.58, y: 3.14, w: 2.72, h: 1.88, radius: 0.08 },
  },
  process_flow_dark: {
    board: { x: 0.68, y: 1.06, w: 8.62, h: 3.96, radius: 0.09 },
    nodes: [
      { x: 1.0, y: 2.02, w: 1.86, h: 1.72 },
      { x: 3.1, y: 2.02, w: 1.86, h: 1.72 },
      { x: 5.2, y: 2.02, w: 1.86, h: 1.72 },
      { x: 7.3, y: 2.02, w: 1.72, h: 1.72 },
    ],
  },
  comparison_cards_light: {
    cards: [
      { x: 0.68, y: 1.14, w: 2.7, h: 3.9 },
      { x: 3.62, y: 1.14, w: 2.7, h: 3.9 },
      { x: 6.56, y: 1.14, w: 2.7, h: 3.9 },
    ],
  },
  education_textbook_light: {
    left: { x: 0.68, y: 1.18, w: 4.02, h: 3.82, radius: 0.06 },
    right: { x: 4.98, y: 1.18, w: 4.34, h: 3.82, radius: 0.06 },
    footer: { x: 0.68, y: 5.14, w: 8.64, h: 0.22 },
  },
  quote_hero_dark: {
    quotePanel: { x: 0.9, y: 1.34, w: 8.24, h: 3.24, radius: 0.1 },
    quote: { x: 1.18, y: 1.78, w: 7.68, h: 2.06, fontSize: 36 },
    author: { x: 1.18, y: 4.06, w: 7.68, h: 0.34, fontSize: 16 },
  },
};

export function getTemplateSpec(templateFamily = "dashboard_dark") {
  const key = String(templateFamily || "dashboard_dark").trim();
  return { ...DEFAULT_TEMPLATE_SPEC, ...(TEMPLATE_SPECS[key] || {}) };
}
