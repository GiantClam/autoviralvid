import { renderSvgSlideToPptx } from "./svg-slide-renderer.mjs";
import {
  NON_STANDARD_CHART_TYPES as FACTORY_NON_STANDARD_CHART_TYPES,
  normalizeChartType as normalizeChartTypeFromFactory,
} from "./chart-factory.mjs";

const SLIDE_W_IN = 10;
const SLIDE_H_IN = 5.625;
const CANVAS_W = 960;
const CANVAS_H = 540;

export const NON_STANDARD_CHART_TYPES = [...FACTORY_NON_STANDARD_CHART_TYPES];

function normalizeChartType(value) {
  return normalizeChartTypeFromFactory(value);
}

function toHex(value, fallback = "#2F7BFF") {
  const raw = String(value || "").trim().replace("#", "");
  if (/^[0-9a-fA-F]{6}$/.test(raw)) return `#${raw.toUpperCase()}`;
  return fallback;
}

function escapeXml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function toCanvasX(inches) {
  return (Number(inches || 0) / SLIDE_W_IN) * CANVAS_W;
}

function toCanvasY(inches) {
  return (Number(inches || 0) / SLIDE_H_IN) * CANVAS_H;
}

function normalizeChartData(data = {}) {
  const labelsRaw = Array.isArray(data?.labels) ? data.labels : [];
  const datasetsRaw = Array.isArray(data?.datasets) ? data.datasets : [];
  const values = [];
  if (datasetsRaw.length > 0) {
    const first = datasetsRaw[0] && typeof datasetsRaw[0] === "object" ? datasetsRaw[0] : {};
    const nums = Array.isArray(first.data) ? first.data : [];
    for (const item of nums) {
      const n = Number(item);
      if (Number.isFinite(n)) values.push(n);
    }
  }
  const count = Math.max(values.length, labelsRaw.length, 3);
  const labels = [];
  for (let idx = 0; idx < count; idx += 1) {
    const label = String(labelsRaw[idx] || "").trim() || `Step ${idx + 1}`;
    labels.push(label);
  }
  while (values.length < count) {
    values.push(Math.max(8, 100 - values.length * 18));
  }
  return {
    labels,
    values: values.slice(0, count),
  };
}

function resolveChartRect(card = {}) {
  const cardX = toCanvasX(card.x || 0);
  const cardY = toCanvasY(card.y || 0);
  const cardW = Math.max(60, toCanvasX(card.w || 0));
  const cardH = Math.max(50, toCanvasY(card.h || 0));
  const paddingX = Math.max(8, cardW * 0.08);
  const paddingY = Math.max(8, cardH * 0.1);
  return {
    x: cardX + paddingX,
    y: cardY + paddingY,
    w: Math.max(24, cardW - paddingX * 2),
    h: Math.max(24, cardH - paddingY * 2),
  };
}

function createPalette(theme = {}) {
  return {
    primary: toHex(theme.primary, "#2F7BFF"),
    secondary: toHex(theme.secondary, "#12B6F5"),
    accent: toHex(theme.accent, "#18E0D1"),
    border: toHex(theme.borderColor || theme.light, "#A8BEDD"),
    text: toHex(theme.darkText, "#1E293B"),
    success: toHex(theme.success, "#22C55E"),
    danger: toHex(theme.danger, "#EF4444"),
    cardBg: toHex(theme.cardBg || theme.white, "#FFFFFF"),
  };
}

function buildFunnelSvg({ labels, values, rect, palette, title = "" }) {
  const count = Math.max(1, Math.min(labels.length, values.length, 6));
  const maxVal = Math.max(1, ...values.slice(0, count).map((v) => Math.abs(Number(v) || 0)));
  const stepH = rect.h / count;
  const centerX = rect.x + rect.w / 2;
  const minRatio = 0.35;
  const rows = [];
  const textRows = [];

  for (let idx = 0; idx < count; idx += 1) {
    const current = Math.abs(Number(values[idx]) || 0);
    const next = idx + 1 < count ? Math.abs(Number(values[idx + 1]) || 0) : current * minRatio;
    const topRatio = Math.max(minRatio, current / maxVal);
    const bottomRatio = Math.max(minRatio, next / maxVal);
    const y1 = rect.y + idx * stepH + 2;
    const y2 = rect.y + (idx + 1) * stepH - 2;
    const topHalf = (rect.w * topRatio) / 2;
    const bottomHalf = (rect.w * bottomRatio) / 2;
    const color = idx % 3 === 0 ? palette.primary : idx % 3 === 1 ? palette.secondary : palette.accent;
    rows.push(
      `<path d="M ${centerX - topHalf} ${y1} L ${centerX + topHalf} ${y1} L ${centerX + bottomHalf} ${y2} L ${centerX - bottomHalf} ${y2} Z" fill="${color}" stroke="${palette.border}" stroke-width="1.2" />`,
    );
    textRows.push(
      `<text x="${centerX}" y="${(y1 + y2) / 2 + 4}" fill="${palette.cardBg}" font-size="${Math.max(
        10,
        Math.min(14, stepH * 0.24),
      )}" text-anchor="middle">${escapeXml(`${labels[idx]}  ${current}`)}</text>`,
    );
  }

  const titleText = title
    ? `<text x="${rect.x}" y="${rect.y - 8}" fill="${palette.text}" font-size="13">${escapeXml(title)}</text>`
    : "";
  return `${titleText}${rows.join("")}${textRows.join("")}`;
}

function buildWaterfallSvg({ labels, values, rect, palette, title = "" }) {
  const count = Math.max(1, Math.min(labels.length, values.length, 8));
  const deltas = values.slice(0, count).map((v) => Number(v) || 0);
  const cumulative = [0];
  for (const d of deltas) cumulative.push(cumulative[cumulative.length - 1] + d);
  const minVal = Math.min(...cumulative, 0);
  const maxVal = Math.max(...cumulative, 0);
  const span = Math.max(1, maxVal - minVal);
  const plotX = rect.x;
  const plotY = rect.y + 6;
  const plotW = rect.w;
  const plotH = rect.h - 16;
  const zeroY = plotY + ((maxVal - 0) / span) * plotH;
  const barGap = Math.max(6, plotW * 0.02);
  const barW = Math.max(10, (plotW - (count - 1) * barGap) / count);
  const bars = [
    `<line x1="${plotX}" y1="${zeroY}" x2="${plotX + plotW}" y2="${zeroY}" stroke="${palette.border}" stroke-width="1" />`,
  ];
  const labelsOut = [];

  let running = 0;
  for (let idx = 0; idx < count; idx += 1) {
    const delta = deltas[idx];
    const start = running;
    running += delta;
    const end = running;
    const yStart = plotY + ((maxVal - start) / span) * plotH;
    const yEnd = plotY + ((maxVal - end) / span) * plotH;
    const barY = Math.min(yStart, yEnd);
    const barH = Math.max(4, Math.abs(yEnd - yStart));
    const x = plotX + idx * (barW + barGap);
    const fill = delta >= 0 ? palette.success : palette.danger;
    bars.push(
      `<rect x="${x}" y="${barY}" width="${barW}" height="${barH}" rx="2" ry="2" fill="${fill}" stroke="${palette.border}" stroke-width="0.8" />`,
    );
    if (idx < count - 1) {
      const nextX = plotX + (idx + 1) * (barW + barGap);
      bars.push(
        `<line x1="${x + barW}" y1="${yEnd}" x2="${nextX}" y2="${yEnd}" stroke="${palette.border}" stroke-width="0.8" stroke-dasharray="3 2" />`,
      );
    }
    labelsOut.push(
      `<text x="${x + barW / 2}" y="${plotY + plotH + 11}" fill="${palette.text}" font-size="9" text-anchor="middle">${escapeXml(
        labels[idx].slice(0, 10),
      )}</text>`,
    );
  }

  const titleText = title
    ? `<text x="${rect.x}" y="${rect.y - 8}" fill="${palette.text}" font-size="13">${escapeXml(title)}</text>`
    : "";
  return `${titleText}${bars.join("")}${labelsOut.join("")}`;
}

function buildSankeySvg({ labels, values, rect, palette, title = "" }) {
  const count = Math.max(3, Math.min(labels.length, values.length, 6));
  const maxVal = Math.max(1, ...values.slice(0, count).map((v) => Math.abs(Number(v) || 0)));
  const nodeW = Math.max(12, rect.w * 0.08);
  const leftX = rect.x;
  const rightX = rect.x + rect.w - nodeW;
  const rows = [];
  const links = [];
  for (let idx = 0; idx < count; idx += 1) {
    const val = Math.abs(Number(values[idx]) || 0);
    const ratio = Math.max(0.18, val / maxVal);
    const nodeH = Math.max(12, rect.h * 0.12 * ratio + 10);
    const y = rect.y + (idx * rect.h) / count + 2;
    rows.push(`<rect x="${leftX}" y="${y}" width="${nodeW}" height="${nodeH}" fill="${palette.primary}" rx="2" ry="2" />`);
    rows.push(`<rect x="${rightX}" y="${y}" width="${nodeW}" height="${nodeH}" fill="${palette.secondary}" rx="2" ry="2" />`);
    rows.push(`<text x="${leftX + nodeW + 6}" y="${y + 10}" fill="${palette.text}" font-size="9">${escapeXml(labels[idx].slice(0, 16))}</text>`);
    const c1x = leftX + nodeW + rect.w * 0.28;
    const c2x = rightX - rect.w * 0.28;
    const yMid = y + nodeH / 2;
    links.push(
      `<path d="M ${leftX + nodeW} ${yMid} C ${c1x} ${yMid - 8}, ${c2x} ${yMid + 8}, ${rightX} ${yMid}" fill="none" stroke="${palette.accent}" stroke-width="${Math.max(
        2,
        nodeH * 0.35,
      )}" stroke-opacity="0.55" />`,
    );
  }
  const titleText = title
    ? `<text x="${rect.x}" y="${rect.y - 8}" fill="${palette.text}" font-size="13">${escapeXml(title)}</text>`
    : "";
  return `${titleText}${links.join("")}${rows.join("")}`;
}

function buildTreemapSvg({ labels, values, rect, palette, title = "" }) {
  const count = Math.max(2, Math.min(labels.length, values.length, 8));
  const normalizedValues = values.slice(0, count).map((v) => Math.max(1, Math.abs(Number(v) || 0)));
  const sum = Math.max(1, normalizedValues.reduce((acc, n) => acc + n, 0));
  const titleText = title
    ? `<text x="${rect.x}" y="${rect.y - 8}" fill="${palette.text}" font-size="13">${escapeXml(title)}</text>`
    : "";
  const tiles = [];
  let x = rect.x;
  let y = rect.y;
  let w = rect.w;
  let h = rect.h;
  for (let idx = 0; idx < count; idx += 1) {
    const value = normalizedValues[idx];
    const ratio = value / sum;
    const isLast = idx === count - 1;
    let tileW = w;
    let tileH = h;
    if (!isLast) {
      if (w >= h) {
        tileW = Math.max(20, w * ratio * 1.25);
      } else {
        tileH = Math.max(16, h * ratio * 1.25);
      }
    }
    const color = idx % 3 === 0 ? palette.primary : idx % 3 === 1 ? palette.secondary : palette.accent;
    tiles.push(
      `<rect x="${x}" y="${y}" width="${tileW}" height="${tileH}" rx="2" ry="2" fill="${color}" stroke="${palette.border}" stroke-width="0.8" />`,
    );
    tiles.push(
      `<text x="${x + 4}" y="${y + 12}" fill="${palette.cardBg}" font-size="9">${escapeXml(labels[idx].slice(0, 14))}</text>`,
    );
    if (!isLast) {
      if (w >= h) {
        x += tileW;
        w -= tileW;
      } else {
        y += tileH;
        h -= tileH;
      }
    }
  }
  return `${titleText}${tiles.join("")}`;
}

function buildHeatmapSvg({ labels, values, rect, palette, title = "" }) {
  const count = Math.max(4, Math.min(labels.length, values.length, 16));
  const gridCols = Math.max(2, Math.min(4, Math.round(Math.sqrt(count))));
  const gridRows = Math.ceil(count / gridCols);
  const cellW = rect.w / gridCols;
  const cellH = rect.h / gridRows;
  const normalizedValues = values.slice(0, count).map((v) => Math.abs(Number(v) || 0));
  while (normalizedValues.length < count) normalizedValues.push(0);
  const maxVal = Math.max(1, ...normalizedValues);
  const minVal = Math.min(...normalizedValues);
  const span = Math.max(1, maxVal - minVal);
  const titleText = title
    ? `<text x="${rect.x}" y="${rect.y - 8}" fill="${palette.text}" font-size="13">${escapeXml(title)}</text>`
    : "";
  const cells = [];
  for (let idx = 0; idx < count; idx += 1) {
    const row = Math.floor(idx / gridCols);
    const col = idx % gridCols;
    const x = rect.x + col * cellW;
    const y = rect.y + row * cellH;
    const ratio = (normalizedValues[idx] - minVal) / span;
    const alpha = (0.25 + ratio * 0.7).toFixed(2);
    cells.push(
      `<rect x="${x + 1.5}" y="${y + 1.5}" width="${Math.max(8, cellW - 3)}" height="${Math.max(
        8,
        cellH - 3,
      )}" rx="2" ry="2" fill="${palette.primary}" fill-opacity="${alpha}" stroke="${palette.border}" stroke-width="0.6" />`,
    );
    cells.push(
      `<text x="${x + cellW / 2}" y="${y + cellH / 2 + 3}" fill="${palette.text}" font-size="8" text-anchor="middle">${escapeXml(
        String(normalizedValues[idx]),
      )}</text>`,
    );
  }
  return `${titleText}${cells.join("")}`;
}

function buildGaugeSvg({ values, rect, palette, title = "" }) {
  const value = Math.max(0, Math.min(100, Math.abs(Number(values[0]) || 0)));
  const centerX = rect.x + rect.w / 2;
  const centerY = rect.y + rect.h * 0.92;
  const radius = Math.max(20, Math.min(rect.w * 0.42, rect.h * 0.8));
  const band = Math.max(6, radius * 0.18);
  const startAngle = Math.PI;
  const endAngle = 0;
  const valueAngle = startAngle - (Math.PI * value) / 100;
  const toPoint = (angle, r) => ({ x: centerX + Math.cos(angle) * r, y: centerY - Math.sin(angle) * r });
  const arcStart = toPoint(startAngle, radius);
  const arcEnd = toPoint(endAngle, radius);
  const valuePoint = toPoint(valueAngle, radius - band * 0.4);
  const titleText = title
    ? `<text x="${rect.x}" y="${rect.y - 8}" fill="${palette.text}" font-size="13">${escapeXml(title)}</text>`
    : "";
  return `${titleText}
    <path d="M ${arcStart.x} ${arcStart.y} A ${radius} ${radius} 0 0 1 ${arcEnd.x} ${arcEnd.y}" fill="none" stroke="${palette.border}" stroke-width="${band}" />
    <path d="M ${arcStart.x} ${arcStart.y} A ${radius} ${radius} 0 ${value > 50 ? 1 : 0} 1 ${valuePoint.x} ${valuePoint.y}" fill="none" stroke="${palette.accent}" stroke-width="${band}" />
    <line x1="${centerX}" y1="${centerY}" x2="${valuePoint.x}" y2="${valuePoint.y}" stroke="${palette.primary}" stroke-width="2.2" />
    <circle cx="${centerX}" cy="${centerY}" r="3.8" fill="${palette.primary}" />
    <text x="${centerX}" y="${centerY - band - 8}" fill="${palette.text}" font-size="16" text-anchor="middle">${value}%</text>`;
}

function buildPyramidSvg({ labels, values, rect, palette, title = "" }) {
  const count = Math.max(3, Math.min(labels.length, values.length, 6));
  const maxVal = Math.max(1, ...values.slice(0, count).map((v) => Math.abs(Number(v) || 0)));
  const stepH = rect.h / count;
  const centerX = rect.x + rect.w / 2;
  const rows = [];
  for (let idx = 0; idx < count; idx += 1) {
    const current = Math.abs(Number(values[idx]) || 0);
    const ratio = Math.max(0.18, current / maxVal);
    const topRatio = Math.max(0.08, ratio * (idx / count));
    const y1 = rect.y + idx * stepH + 2;
    const y2 = rect.y + (idx + 1) * stepH - 2;
    const topHalf = (rect.w * topRatio) / 2;
    const bottomHalf = (rect.w * ratio) / 2;
    const color = idx % 3 === 0 ? palette.primary : idx % 3 === 1 ? palette.secondary : palette.accent;
    rows.push(
      `<path d="M ${centerX - topHalf} ${y1} L ${centerX + topHalf} ${y1} L ${centerX + bottomHalf} ${y2} L ${centerX - bottomHalf} ${y2} Z" fill="${color}" stroke="${palette.border}" stroke-width="1" />`,
    );
    rows.push(
      `<text x="${centerX}" y="${(y1 + y2) / 2 + 4}" fill="${palette.cardBg}" font-size="${Math.max(
        9,
        Math.min(12, stepH * 0.22),
      )}" text-anchor="middle">${escapeXml(labels[idx].slice(0, 12))}</text>`,
    );
  }
  const titleText = title
    ? `<text x="${rect.x}" y="${rect.y - 8}" fill="${palette.text}" font-size="13">${escapeXml(title)}</text>`
    : "";
  return `${titleText}${rows.join("")}`;
}

function resolveRendererChartType(chartType) {
  const normalized = normalizeChartType(chartType);
  if (!normalized) return "funnel";
  const exact = new Set([
    "funnel",
    "waterfall",
    "sankey",
    "treemap",
    "heatmap",
    "gauge",
    "pyramid",
  ]);
  if (exact.has(normalized)) return normalized;

  // Keep incremental support practical by mapping the long-tail chart family
  // to robust SVG primitives that already have stable rendering behavior.
  if (normalized === "radialbar" || normalized === "bullet" || normalized === "variance") return "gauge";
  if (normalized === "sunburst" || normalized === "rose" || normalized === "radar_area") return "pyramid";
  if (normalized === "bubble_map" || normalized === "choropleth" || normalized === "marimekko" || normalized === "mekko") return "treemap";
  if (normalized === "boxplot" || normalized === "violin" || normalized === "candlestick" || normalized === "pareto") return "waterfall";
  if (normalized === "wordcloud" || normalized === "streamgraph") return "heatmap";
  if (normalized === "network" || normalized === "alluvial") return "sankey";
  return "funnel";
}

export function isNonStandardChartType(chartType) {
  return NON_STANDARD_CHART_TYPES.includes(normalizeChartType(chartType));
}

export function buildNonStandardChartSvg({
  chartType,
  labels = [],
  datasets = [],
  card = {},
  theme = {},
  title = "",
} = {}) {
  const normalizedType = normalizeChartType(chartType);
  const rendererType = resolveRendererChartType(normalizedType);
  const palette = createPalette(theme);
  const rect = resolveChartRect(card);
  const normalized = normalizeChartData({ labels, datasets });
  let body = "";
  if (rendererType === "waterfall") {
    body = buildWaterfallSvg({ ...normalized, rect, palette, title });
  } else if (rendererType === "sankey") {
    body = buildSankeySvg({ ...normalized, rect, palette, title });
  } else if (rendererType === "treemap") {
    body = buildTreemapSvg({ ...normalized, rect, palette, title });
  } else if (rendererType === "heatmap") {
    body = buildHeatmapSvg({ ...normalized, rect, palette, title });
  } else if (rendererType === "gauge") {
    body = buildGaugeSvg({ ...normalized, rect, palette, title });
  } else if (rendererType === "pyramid") {
    body = buildPyramidSvg({ ...normalized, rect, palette, title });
  } else {
    body = buildFunnelSvg({ ...normalized, rect, palette, title });
  }
  return `<svg width="${CANVAS_W}" height="${CANVAS_H}" viewBox="0 0 ${CANVAS_W} ${CANVAS_H}" xmlns="http://www.w3.org/2000/svg">${body}</svg>`;
}

export function renderNonStandardChartInCard({
  slide,
  pptx,
  card = {},
  theme = {},
  designSpec = {},
  data = {},
} = {}) {
  const chartType = normalizeChartType(data?.chartType || data?.type);
  if (!isNonStandardChartType(chartType)) {
    return { applied: false, mode: "none", reason: "chart_type_not_nonstandard" };
  }
  const labels = Array.isArray(data?.labels) ? data.labels : [];
  const datasets = Array.isArray(data?.datasets) ? data.datasets : [];
  if (datasets.length === 0) {
    return { applied: false, mode: "none", reason: "chart_data_missing" };
  }
  const svgMarkup = buildNonStandardChartSvg({
    chartType,
    labels,
    datasets,
    card,
    theme,
    title: String(data?.title || data?.label || "").trim(),
  });
  const result = renderSvgSlideToPptx({
    slide,
    pptx,
    sourceSlide: { svg_markup: svgMarkup },
    theme,
    designSpec,
  });
  return {
    ...result,
    chart_type: chartType,
    mode: result?.mode ? `svg_${result.mode}` : "svg",
  };
}
