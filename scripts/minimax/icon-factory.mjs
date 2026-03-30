import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as FiIcons from "react-icons/fi";
import * as Fa6Icons from "react-icons/fa6";
import * as MdIcons from "react-icons/md";
import * as AiIcons from "react-icons/ai";
import * as Io5Icons from "react-icons/io5";
import * as BiIcons from "react-icons/bi";
import * as TbIcons from "react-icons/tb";
import * as RiIcons from "react-icons/ri";
import * as Hi2Icons from "react-icons/hi2";
import { rasterizeSvgToPngDataUri } from "./sharp-rasterizer.mjs";

const DEFAULT_ICON_NAME = "FiCircle";
const DEFAULT_PPT_MASTER_VIEWBOX = "0 0 16 16";
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PPT_MASTER_ICON_DIR = path.resolve(__dirname, "vendor", "ppt-master-icons");
const PPT_MASTER_ICON_INDEX = path.join(PPT_MASTER_ICON_DIR, "icons_index.json");
const REACT_ICON_PACKS = [FiIcons, Fa6Icons, MdIcons, AiIcons, Io5Icons, BiIcons, TbIcons, RiIcons, Hi2Icons];

const ICON_ALIAS = {
  growth: "FiTrendingUp",
  trend: "FiTrendingUp",
  up: "FiTrendingUp",
  increase: "FiTrendingUp",
  target: "FiTarget",
  goal: "FiTarget",
  users: "FiUsers",
  user: "FiUser",
  team: "FiUsers",
  people: "FiUsers",
  client: "FiUsers",
  customer: "FiUsers",
  workflow: "FiGitBranch",
  process: "FiRepeat",
  strategy: "FiCompass",
  risk: "FiAlertTriangle",
  warning: "FiAlertTriangle",
  alert: "FiAlertTriangle",
  security: "FiShield",
  trust: "FiShield",
  quality: "FiCheckCircle",
  success: "FiCheckCircle",
  performance: "FiActivity",
  speed: "FiZap",
  system: "FiCpu",
  cloud: "FiCloud",
  data: "FiDatabase",
  finance: "FiDollarSign",
  revenue: "FiDollarSign",
  money: "FiDollarSign",
  timeline: "FiClock",
  time: "FiClock",
  report: "FiBarChart2",
  chart: "FiBarChart2",
  analytics: "FiBarChart2",
  organization: "FiLayers",
  product: "FiPackage",
  idea: "FiLightbulb",
  operation: "FiSettings",
  support: "FiLifeBuoy",
};

const PPT_MASTER_ICON_ALIAS = {
  growth: "arrow-trend-up",
  trend: "arrow-trend-up",
  up: "arrow-up",
  increase: "arrow-trend-up",
  target: "target",
  goal: "target-arrow",
  users: "users",
  user: "user",
  team: "group",
  people: "users",
  client: "address-card",
  customer: "address-card",
  workflow: "arrows-repeat",
  process: "route",
  strategy: "signpost",
  risk: "triangle-exclamation",
  warning: "triangle-exclamation",
  alert: "triangle-exclamation",
  security: "shield",
  trust: "shield-check",
  quality: "circle-checkmark",
  success: "circle-checkmark",
  performance: "gauge-high",
  speed: "bolt",
  system: "microchip",
  cloud: "cloud",
  data: "database",
  finance: "dollar",
  revenue: "dollar",
  money: "wallet",
  timeline: "clock",
  time: "clock",
  report: "chart-bar",
  chart: "chart-line",
  analytics: "chart-pie",
  organization: "building",
  product: "package",
  idea: "lightbulb",
  operation: "sliders",
  support: "service-bell",
};

const PPT_MASTER_CN_ALIAS_CONTAINS = [
  ["增长", "arrow-trend-up"],
  ["增速", "arrow-trend-up"],
  ["提升", "arrow-trend-up"],
  ["目标", "target-arrow"],
  ["指标", "target"],
  ["风险", "triangle-exclamation"],
  ["预警", "triangle-exclamation"],
  ["流程", "route"],
  ["路径", "route"],
  ["战略", "signpost"],
  ["策略", "signpost"],
  ["用户", "user"],
  ["客户", "address-card"],
  ["团队", "group"],
  ["组织", "building"],
  ["数据", "database"],
  ["图表", "chart-line"],
  ["分析", "chart-pie"],
  ["财务", "dollar"],
  ["收入", "dollar"],
  ["成本", "wallet"],
  ["时间", "clock"],
  ["计划", "clock"],
  ["质量", "circle-checkmark"],
  ["成功", "circle-checkmark"],
  ["安全", "shield"],
  ["合规", "shield-check"],
  ["系统", "microchip"],
  ["性能", "gauge-high"],
  ["云", "cloud"],
  ["创意", "lightbulb"],
  ["创新", "lightbulb"],
  ["支持", "service-bell"],
  ["服务", "service-bell"],
];

let pptMasterIndexCache = null;
const pptMasterSvgCache = new Map();

function reactIconStats() {
  return {
    packCount: REACT_ICON_PACKS.length,
    iconCount: REACT_ICON_PACKS.reduce((acc, pack) => acc + Object.keys(pack || {}).length, 0),
  };
}

function normalizeHex(value, fallback = "2F7BFF") {
  const text = String(value || "").trim().replace("#", "");
  if (/^[0-9a-fA-F]{6}$/.test(text)) return text.toUpperCase();
  return fallback;
}

function normalizeToken(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[_-]+/g, " ")
    .replace(/[^a-z0-9\u4e00-\u9fff ]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function loadPptMasterIndex() {
  if (pptMasterIndexCache) return pptMasterIndexCache;
  const empty = {
    loaded: false,
    viewBox: DEFAULT_PPT_MASTER_VIEWBOX,
    iconNames: new Set(),
    lookup: new Map(),
    keywords: new Map(),
  };
  if (!fs.existsSync(PPT_MASTER_ICON_INDEX)) {
    pptMasterIndexCache = empty;
    return pptMasterIndexCache;
  }
  try {
    const payload = JSON.parse(fs.readFileSync(PPT_MASTER_ICON_INDEX, "utf-8"));
    const iconNames = new Set();
    const lookup = new Map();
    const keywords = new Map();
    const categories = payload?.categories && typeof payload.categories === "object" ? payload.categories : {};
    for (const [categoryKey, categoryValue] of Object.entries(categories)) {
      const categoryToken = normalizeToken(categoryKey);
      const icons = Array.isArray(categoryValue?.icons) ? categoryValue.icons : [];
      for (const icon of icons) {
        const raw = String(icon || "").trim();
        if (!raw) continue;
        const lowered = raw.toLowerCase();
        const normalized = normalizeToken(raw);
        iconNames.add(raw);
        lookup.set(lowered, raw);
        if (normalized) lookup.set(normalized, raw);
        if (categoryToken && !keywords.has(categoryToken)) keywords.set(categoryToken, raw);
        for (const token of normalized.split(" ").filter(Boolean)) {
          if (!keywords.has(token)) keywords.set(token, raw);
        }
      }
    }
    pptMasterIndexCache = {
      loaded: true,
      viewBox: String(payload?.meta?.viewBox || DEFAULT_PPT_MASTER_VIEWBOX),
      iconNames,
      lookup,
      keywords,
    };
    return pptMasterIndexCache;
  } catch {
    pptMasterIndexCache = empty;
    return pptMasterIndexCache;
  }
}

function resolveReactByKeyword(text) {
  const normalized = normalizeToken(text);
  if (!normalized) return "";
  const words = normalized.split(" ").filter(Boolean);
  for (const word of words) {
    if (ICON_ALIAS[word]) return ICON_ALIAS[word];
  }
  return "";
}

function findReactIconComponent(iconName = "") {
  const key = String(iconName || "").trim();
  if (!key) return null;
  for (const pack of REACT_ICON_PACKS) {
    if (pack && pack[key]) return pack[key];
  }
  return null;
}

function resolvePptMasterByKeyword(text) {
  const state = loadPptMasterIndex();
  if (!state.loaded) return "";
  const normalized = normalizeToken(text);
  if (!normalized) return "";
  if (state.lookup.has(normalized)) return state.lookup.get(normalized);
  const words = normalized.split(" ").filter(Boolean);
  for (const word of words) {
    const alias = PPT_MASTER_ICON_ALIAS[word];
    if (alias && state.lookup.has(alias)) return state.lookup.get(alias);
    if (state.keywords.has(word)) return state.keywords.get(word);
  }
  for (const [keyword, iconName] of PPT_MASTER_CN_ALIAS_CONTAINS) {
    if (!keyword || !iconName) continue;
    if (normalized.includes(keyword) && state.lookup.has(iconName)) return state.lookup.get(iconName);
  }
  return "";
}

function pickReactIconName(candidate = "") {
  const raw = String(candidate || "").trim();
  if (!raw) return "";
  if (findReactIconComponent(raw)) return raw;
  return "";
}

function pickPptMasterIconName(candidate = "") {
  const raw = String(candidate || "").trim();
  if (!raw) return "";
  const state = loadPptMasterIndex();
  if (!state.loaded) return "";
  const lowered = raw.toLowerCase();
  if (state.lookup.has(lowered)) return state.lookup.get(lowered);
  const normalized = normalizeToken(raw);
  if (state.lookup.has(normalized)) return state.lookup.get(normalized);
  return "";
}

export function resolveIconName({
  icon = "",
  title = "",
  text = "",
  fallback = DEFAULT_ICON_NAME,
} = {}) {
  const directPptMaster = pickPptMasterIconName(icon);
  if (directPptMaster) return directPptMaster;
  const directReact = pickReactIconName(icon);
  if (directReact) return directReact;
  for (const source of [icon, title, text]) {
    const byPptMasterKeyword = resolvePptMasterByKeyword(source);
    if (byPptMasterKeyword) return byPptMasterKeyword;
    const byReactKeyword = resolveReactByKeyword(source);
    if (byReactKeyword && findReactIconComponent(byReactKeyword)) return byReactKeyword;
  }
  const fallbackPptMaster = pickPptMasterIconName(fallback);
  if (fallbackPptMaster) return fallbackPptMaster;
  return findReactIconComponent(fallback) ? fallback : DEFAULT_ICON_NAME;
}

function isPptMasterIconName(iconName = "") {
  const state = loadPptMasterIndex();
  return state.loaded && state.iconNames.has(String(iconName || "").trim());
}

function readPptMasterSvg(iconName = "") {
  const raw = String(iconName || "").trim();
  if (!raw || !/^[a-z0-9-]+$/i.test(raw)) return "";
  const cached = pptMasterSvgCache.get(raw);
  if (cached !== undefined) return cached;
  const filePath = path.join(PPT_MASTER_ICON_DIR, `${raw}.svg`);
  if (!fs.existsSync(filePath)) {
    pptMasterSvgCache.set(raw, "");
    return "";
  }
  try {
    const svg = fs.readFileSync(filePath, "utf-8");
    pptMasterSvgCache.set(raw, svg);
    return svg;
  } catch {
    pptMasterSvgCache.set(raw, "");
    return "";
  }
}

function normalizePptMasterSvgMarkup(svgMarkup = "", { size = 56, color = "2F7BFF" } = {}) {
  const raw = String(svgMarkup || "").trim();
  if (!raw) return "";
  const state = loadPptMasterIndex();
  const hex = `#${normalizeHex(color)}`;
  let inner = raw
    .replace(/<\?xml[\s\S]*?\?>/gi, "")
    .replace(/<!--[\s\S]*?-->/g, "")
    .trim();
  inner = inner.replace(/^.*?<svg\b[^>]*>/is, "").replace(/<\/svg>\s*$/is, "");
  if (!inner.trim()) return "";
  inner = inner
    .replace(/fill="(?!none)[^"]*"/gi, `fill="${hex}"`)
    .replace(/stroke="(?!none)[^"]*"/gi, `stroke="${hex}"`);
  const targetSize = Math.max(18, Number(size) || 56);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${targetSize}" height="${targetSize}" viewBox="${state.viewBox || DEFAULT_PPT_MASTER_VIEWBOX}" fill="none">${inner}</svg>`;
}

export function renderIconSvgMarkup({
  icon = "",
  title = "",
  text = "",
  size = 56,
  color = "2F7BFF",
  strokeWidth = 1.9,
} = {}) {
  const iconName = resolveIconName({ icon, title, text });
  if (isPptMasterIconName(iconName)) {
    const rawSvg = readPptMasterSvg(iconName);
    const normalizedSvg = normalizePptMasterSvgMarkup(rawSvg, { size, color });
    if (normalizedSvg) return normalizedSvg;
  }
  const Comp = findReactIconComponent(iconName) || FiIcons[DEFAULT_ICON_NAME];
  const hex = `#${normalizeHex(color)}`;
  return renderToStaticMarkup(
    createElement(Comp, {
      size: Math.max(18, Number(size) || 56),
      color: hex,
      strokeWidth: Math.max(1.2, Number(strokeWidth) || 1.9),
      "aria-hidden": true,
    }),
  );
}

export function renderIconDataForPptx(options = {}) {
  const svgMarkup = renderIconSvgMarkup(options);
  const iconSize = Math.max(18, Number(options?.size) || 56);
  const rasterSize = Math.max(72, Math.round(iconSize * 4));
  const pngData = rasterizeSvgToPngDataUri(svgMarkup, {
    width: rasterSize,
    height: rasterSize,
    density: 480,
  });
  if (pngData) return pngData;
  const encoded = Buffer.from(String(svgMarkup || ""), "utf-8").toString("base64");
  return `image/svg+xml;base64,${encoded}`;
}

export function getIconLibraryStats() {
  const react = reactIconStats();
  const pptMaster = loadPptMasterIndex();
  return {
    react_pack_count: react.packCount,
    react_icon_count: react.iconCount,
    ppt_master_icon_count: pptMaster.iconNames?.size || 0,
    total_icon_count: react.iconCount + (pptMaster.iconNames?.size || 0),
  };
}
