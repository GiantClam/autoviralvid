/**
 * MiniMax original-skill-inspired PPTX generator.
 *
 * Features:
 * - 18 palette library + auto palette selection
 * - 4 style recipes (sharp/soft/rounded/pill) + auto style
 * - cover / toc / content subtypes / summary structure
 *
 * Usage:
 *   node scripts/generate-pptx-minimax.mjs --input <json_file> --output <pptx_file> [--style <variant>] [--palette <key>] [--render-output <json_file>]
 */

import { parseArgs } from "node:util";
import { readFileSync, writeFileSync } from "node:fs";
import pptxgen from "pptxgenjs";
import {
  inferSubtype as inferSubtypeHeuristic,
  normalizeKey,
  selectPalette as selectPaletteHeuristic,
  selectStyle as selectStyleHeuristic,
} from "./minimax-style-heuristics.mjs";
import { canRenderBentoSlide, renderBentoSlide } from "./minimax/card-renderers.mjs";
import { normalizeRenderInput, validateRenderInput } from "./minimax/render-contract.mjs";
import { fromOfficialOutput } from "./minimax/official_skill_adapter.mjs";
import { resolveOfficialPlan } from "./minimax/official_orchestrator.mjs";
import { buildDarkTheme, normalizeTemplateFamily } from "./minimax/design-tokens.mjs";
import { addSvgOverlay, buildSlideSvg } from "./minimax/svg-slide.mjs";
import { getTemplateProfiles } from "./minimax/templates/template-profiles.mjs";
import {
  resolveSubtypeByTemplate as resolveSubtypeByTemplateRegistry,
  resolveTemplateFamilyForSlide,
} from "./minimax/templates/template-registry.mjs";
import {
  hasTemplateContentRenderer,
  hasTemplateCoverRenderer,
  renderTemplateContent,
  renderTemplateCover,
} from "./minimax/templates/template-renderers.mjs";

const { values } = parseArgs({
  options: {
    input: { type: "string" },
    output: { type: "string" },
    style: { type: "string" },
    palette: { type: "string" },
    "render-output": { type: "string" },
    "verbatim-content": { type: "boolean" },
    "deck-id": { type: "string" },
    "retry-scope": { type: "string" },
    "target-slide-ids": { type: "string" },
    "target-block-ids": { type: "string" },
    "retry-hint": { type: "string" },
    "idempotency-key": { type: "string" },
    "original-style": { type: "boolean" },
    "disable-local-style-rewrite": { type: "boolean" },
    "generator-mode": { type: "string" },
    "visual-priority": { type: "boolean" },
    "visual-preset": { type: "string" },
    "visual-density": { type: "string" },
    "constraint-hardness": { type: "string" },
    "svg-mode": { type: "string" },
    "template-family": { type: "string" },
  },
});

if (!values.input || !values.output) {
  console.error("Usage: node generate-pptx-minimax.mjs --input <json_file> --output <pptx_file> [--style <variant>] [--palette <key>] [--render-output <json_file>] [--generator-mode official|legacy] [--visual-priority] [--visual-preset <name>] [--constraint-hardness minimal|balanced]");
  process.exit(1);
}

const rawInput = readFileSync(values.input, "utf-8");
const parsedInput = JSON.parse(rawInput.charCodeAt(0) === 0xfeff ? rawInput.slice(1) : rawInput);
const payload = normalizeRenderInput(parsedInput);
const contractValidation = validateRenderInput(payload);
if (!contractValidation.ok) {
  console.error(
    JSON.stringify({
      success: false,
      failure_code: "schema_invalid",
      error: `Render contract invalid: ${contractValidation.errors.slice(0, 6).join("; ")}`,
    }),
  );
  process.exit(2);
}
const slides = Array.isArray(payload.slides) ? payload.slides : [];
const deckTitle = String(payload.title || "Presentation");
const deckAuthor = String(payload.author || "AutoViralVid");
const requestedStyle = String(values.style || payload.minimax_style_variant || "auto");
const requestedPalette = String(values.palette || payload.minimax_palette_key || "auto");
const renderOutputPath = values["render-output"] ? String(values["render-output"]) : "";
const deckStyleHint = String(payload.deck_style || payload.style || "").toLowerCase();
const deckId = String(values["deck-id"] || payload.deck_id || "").trim();
const idempotencyKey = String(values["idempotency-key"] || payload.idempotency_key || "").trim();
const retryScope = normalizeKey(values["retry-scope"] || payload.retry_scope || "deck") || "deck";
const retryHint = String(values["retry-hint"] || payload.retry_hint || "").trim();

function parseCsv(rawValue) {
  return String(rawValue || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

const targetSlideIds = parseCsv(values["target-slide-ids"] || payload.target_slide_ids || "");
const targetBlockIds = parseCsv(values["target-block-ids"] || payload.target_block_ids || "");
const originalStyle = asBool(values["original-style"], payload.original_style, true);
const requestedDisableLocalStyleRewrite = asBool(
  values["disable-local-style-rewrite"],
  payload.disable_local_style_rewrite,
  originalStyle,
);

const MOJIBAKE_TOKENS = ["鈥", "锛", "鍙", "鐨", "銆", "闄"];
const GARBLE_HINTS = ["\uFFFD", "???"];

function asBool(...candidates) {
  for (const candidate of candidates) {
    if (typeof candidate === "boolean") return candidate;
    if (typeof candidate === "string") {
      const normalized = candidate.trim().toLowerCase();
      if (["1", "true", "yes", "on"].includes(normalized)) return true;
      if (["0", "false", "no", "off"].includes(normalized)) return false;
    }
    if (typeof candidate === "number") return candidate !== 0;
  }
  return false;
}

const verbatimContent = asBool(
  values["verbatim-content"],
  payload.verbatim_content,
  false,
);
const officialPlan = resolveOfficialPlan({
  payload,
  cliValues: values,
  originalStyle,
  disableLocalStyleRewrite: requestedDisableLocalStyleRewrite,
  retryScope,
});
const generatorMode = officialPlan.generatorMode;
const disableLocalStyleRewrite = officialPlan.disableLocalStyleRewrite;
const effectiveVerbatimContent = verbatimContent;
const requestedVisualPreset = String(values["visual-preset"] || payload.visual_preset || "auto");
const requestedVisualDensity = String(values["visual-density"] || payload.visual_density || "balanced");
const requestedConstraintHardness = String(
  values["constraint-hardness"] || payload.constraint_hardness || "minimal",
);
const requestedSvgMode = String(values["svg-mode"] || payload.svg_mode || "auto");
const requestedTemplateFamily = String(values["template-family"] || parsedInput.template_family || "auto");
const visualPriority = asBool(
  values["visual-priority"],
  payload.visual_priority,
  generatorMode === "official" && !disableLocalStyleRewrite,
);
const normalizedSvgModeRaw = normalizeKey(requestedSvgMode || "auto");
const normalizedSvgMode = (
  normalizedSvgModeRaw === "force" || normalizedSvgModeRaw === "on"
    ? "force"
    : normalizedSvgModeRaw === "off"
      ? "off"
      : "auto"
);
const svgModeEnabled = normalizedSvgMode !== "off";

function normalizeConstraintHardness(input) {
  const normalized = normalizeKey(input || "");
  if (normalized === "balanced" || normalized === "strict") return "balanced";
  return "minimal";
}

function looksGarbledText(input) {
  const text = String(input || "").trim();
  if (!text) return false;
  if (GARBLE_HINTS.some((token) => text.includes(token))) return true;
  const tokenHits = MOJIBAKE_TOKENS.reduce((acc, token) => acc + text.split(token).length - 1, 0);
  if (tokenHits >= 2 && text.length >= 6) return true;
  const qRatio = (text.split("?").length - 1) / Math.max(1, text.length);
  return (text.split("?").length - 1) >= 3 && qRatio >= 0.15;
}

function detectEncodingIssues(node, path = "$", issues = []) {
  if (typeof node === "string") {
    if (looksGarbledText(node)) {
      issues.push(`${path}: ${String(node).slice(0, 80)}`);
    }
    return issues;
  }
  if (Array.isArray(node)) {
    node.forEach((item, idx) => detectEncodingIssues(item, `${path}[${idx}]`, issues));
    return issues;
  }
  if (node && typeof node === "object") {
    for (const [key, value] of Object.entries(node)) {
      detectEncodingIssues(value, `${path}.${key}`, issues);
    }
  }
  return issues;
}

const encodingIssues = detectEncodingIssues(payload);
if (encodingIssues.length > 0) {
  console.error(
    JSON.stringify({
      success: false,
      failure_code: "encoding_invalid",
      error: `Input contains likely garbled text at ${encodingIssues.slice(0, 6).join("; ")}`,
    }),
  );
  process.exit(2);
}
const constraintHardness = normalizeConstraintHardness(requestedConstraintHardness);

const PALETTES = {
  modern_wellness: ["006D77", "83C5BE", "EDF6F9", "FFDDD2", "E29578"],
  business_authority: ["2B2D42", "8D99AE", "EDF2F4", "EF233C", "D90429"],
  nature_outdoors: ["606C38", "283618", "FEFAE0", "DDA15E", "BC6C25"],
  vintage_academic: ["780000", "C1121F", "FDF0D5", "003049", "669BBC"],
  soft_creative: ["CDB4DB", "FFC8DD", "FFAFCC", "BDE0FE", "A2D2FF"],
  bohemian: ["CCD5AE", "E9EDC9", "FEFAE0", "FAEDCD", "D4A373"],
  vibrant_tech: ["8ECAE6", "219EBC", "023047", "FFB703", "FB8500"],
  craft_artisan: ["7F5539", "A68A64", "EDE0D4", "656D4A", "414833"],
  tech_night: ["000814", "001D3D", "003566", "FFC300", "FFD60A"],
  education_charts: ["264653", "2A9D8F", "E9C46A", "F4A261", "E76F51"],
  forest_eco: ["DAD7CD", "A3B18A", "588157", "3A5A40", "344E41"],
  elegant_fashion: ["EDAFB8", "F7E1D7", "DEDBD2", "B0C4B1", "4A5759"],
  art_food: ["335C67", "FFF3B0", "E09F3E", "9E2A2B", "540B0E"],
  luxury_mysterious: ["22223B", "4A4E69", "9A8C98", "C9ADA7", "F2E9E4"],
  pure_tech_blue: ["03045E", "0077B6", "00B4D8", "90E0EF", "CAF0F8"],
  coastal_coral: ["0081A7", "00AFB9", "FDFCDC", "FED9B7", "F07167"],
  vibrant_orange_mint: ["FF9F1C", "FFBF69", "FFFFFF", "CBF3F0", "2EC4B6"],
  platinum_white_gold: ["0A0A0A", "0070F3", "D4AF37", "F5F5F5", "FFFFFF"],
};

const STYLE_RECIPES = {
  sharp: {
    pageMargin: 0.35,
    gap: 0.16,
    headerHeight: 0.62,
    cardRadius: 0.03,
    badgeRadius: 0.03,
    titleSize: 24,
    bodySize: 14,
    bulletStep: 0.46,
  },
  soft: {
    pageMargin: 0.45,
    gap: 0.2,
    headerHeight: 0.68,
    cardRadius: 0.1,
    badgeRadius: 0.08,
    titleSize: 26,
    bodySize: 15,
    bulletStep: 0.52,
  },
  rounded: {
    pageMargin: 0.52,
    gap: 0.28,
    headerHeight: 0.72,
    cardRadius: 0.2,
    badgeRadius: 0.12,
    titleSize: 27,
    bodySize: 16,
    bulletStep: 0.56,
  },
  pill: {
    pageMargin: 0.6,
    gap: 0.34,
    headerHeight: 0.74,
    cardRadius: 0.3,
    badgeRadius: 0.16,
    titleSize: 28,
    bodySize: 16,
    bulletStep: 0.6,
  },
};

const FONT_BY_STYLE = {
  sharp: { enTitle: "Bahnschrift SemiBold", enBody: "Segoe UI" },
  soft: { enTitle: "Aptos Display", enBody: "Aptos" },
  rounded: { enTitle: "Trebuchet MS", enBody: "Segoe UI" },
  pill: { enTitle: "Gill Sans MT", enBody: "Segoe UI" },
};
const FONT_ZH = "Microsoft YaHei";
const SLIDE_WIDTH = 10;
const SLIDE_HEIGHT = 5.625;
const DECOR_INSET = 0.12;

const VISUAL_PRESETS = {
  tech_cinematic: {
    style: "pill",
    palette: "pure_tech_blue",
    maxBullets: 4,
    backdrop: "high-contrast",
  },
  executive_brief: {
    style: "sharp",
    palette: "business_authority",
    maxBullets: 4,
    backdrop: "minimal-grid",
  },
  premium_light: {
    style: "rounded",
    palette: "platinum_white_gold",
    maxBullets: 5,
    backdrop: "soft-gradient",
  },
  energetic: {
    style: "pill",
    palette: "vibrant_orange_mint",
    maxBullets: 4,
    backdrop: "color-block",
  },
};

function normalizeVisualPreset(input, topicText = "") {
  const normalized = normalizeKey(input || "");
  if (normalized && normalized !== "auto" && VISUAL_PRESETS[normalized]) return normalized;
  if (!normalized || normalized === "auto") return "tech_cinematic";
  const topic = String(topicText || "").toLowerCase();
  if (/(ai|cloud|tech|科技|数字|智能|digital)/.test(topic)) return "tech_cinematic";
  if (/(premium|高端|luxury|investor|融资)/.test(topic)) return "premium_light";
  if (/(brand|campaign|marketing|增长|转化)/.test(topic)) return "energetic";
  return "executive_brief";
}

function resolveSlideTemplateFamily(sourceSlide) {
  const explicitType = normalizeKey(
    pick(sourceSlide || {}, ["page_type", "pageType", "slide_type", "slideType", "subtype"], ""),
  ) || "content";
  const layoutGrid = normalizeKey(String(sourceSlide?.layout_grid || sourceSlide?.layout || "")) || "split_2";
  const lockTemplate = asBool(sourceSlide?.template_lock, false);
  const perSlideTemplate = String(
    pick(sourceSlide || {}, ["template_family", "template_id"], ""),
  ).trim();
  const requestedTemplate = lockTemplate && perSlideTemplate ? perSlideTemplate : requestedTemplateFamily;
  return resolveTemplateFamilyForSlide({
    sourceSlide,
    requestedTemplateFamily: requestedTemplate,
    explicitType,
    layoutGrid,
    desiredDensity: requestedVisualDensity,
    normalizeTemplateFamily,
  });
}

function maybeAddSvgLayer(slide, sourceSlide, theme, fallbackLayout = "split_2") {
  if (!svgModeEnabled) return false;
  const explicitSvgFlag = asBool(
    sourceSlide?.svg_overlay,
    sourceSlide?.force_svg_overlay,
    sourceSlide?.use_svg_overlay,
    false,
  );
  const blocks = Array.isArray(sourceSlide?.blocks) ? sourceSlide.blocks : [];
  const hasSvgBlock = blocks.some((block) => blockType(block) === "svg");
  const shouldInject = normalizedSvgMode === "force" || explicitSvgFlag || hasSvgBlock;
  if (!shouldInject) return false;
  const svgSource = {
    ...(sourceSlide || {}),
    title: pick(sourceSlide || {}, ["title"], deckTitle),
    narration: pick(sourceSlide || {}, ["narration", "speaker_notes", "speakerNotes"], ""),
    layout_grid: pick(sourceSlide || {}, ["layout_grid", "layout"], fallbackLayout),
  };
  const svg = buildSlideSvg(svgSource, theme);
  return addSvgOverlay(slide, svg);
}

function resolveVisualConfig(topicText = "") {
  const presetKey = normalizeVisualPreset(requestedVisualPreset, topicText);
  const preset = VISUAL_PRESETS[presetKey] || VISUAL_PRESETS.executive_brief;
  const density = normalizeKey(requestedVisualDensity || "balanced");
  const densityMaxBullets = density === "sparse" ? 4 : density === "dense" ? 7 : preset.maxBullets;
  let maxBullets = densityMaxBullets;
  if (constraintHardness === "minimal") maxBullets = Math.max(6, maxBullets);
  else maxBullets = Math.min(5, maxBullets);
  return {
    enabled: Boolean(visualPriority),
    preset: presetKey,
    styleOverride: preset.style,
    paletteOverride: preset.palette,
    enforcePreset: false,
    showDecorations: !(constraintHardness === "minimal" || density === "sparse"),
    maxBullets: Math.max(4, Math.min(7, maxBullets)),
    backdrop: preset.backdrop,
    density: density || "balanced",
    constraintHardness,
  };
}

function cleanHex(value, fallback = "FFFFFF") {
  const v = String(value || "").replace("#", "").trim();
  if (/^[0-9a-fA-F]{6}$/.test(v)) return v.toUpperCase();
  return fallback;
}

function blendHex(baseHex, mixHex, ratio = 0.5) {
  const base = cleanHex(baseHex, "000000");
  const mix = cleanHex(mixHex, "FFFFFF");
  const r = Math.min(1, Math.max(0, Number(ratio) || 0));
  const toChannel = (offset) => {
    const a = parseInt(base.slice(offset, offset + 2), 16);
    const b = parseInt(mix.slice(offset, offset + 2), 16);
    return Math.round(a * (1 - r) + b * r)
      .toString(16)
      .padStart(2, "0")
      .toUpperCase();
  };
  return `${toChannel(0)}${toChannel(2)}${toChannel(4)}`;
}

function clampRectToSlide(x, y, w, h, inset = 0) {
  const safeInset = Math.max(0, Number(inset) || 0);
  const safeX = Math.min(Math.max(Number(x) || 0, safeInset), SLIDE_WIDTH - safeInset - 0.2);
  const safeY = Math.min(Math.max(Number(y) || 0, safeInset), SLIDE_HEIGHT - safeInset - 0.2);
  const maxW = Math.max(0.2, SLIDE_WIDTH - safeInset - safeX);
  const maxH = Math.max(0.2, SLIDE_HEIGHT - safeInset - safeY);
  return {
    x: safeX,
    y: safeY,
    w: Math.max(0.2, Math.min(Number(w) || 0.2, maxW)),
    h: Math.max(0.2, Math.min(Number(h) || 0.2, maxH)),
  };
}

function isDark(hex) {
  const c = cleanHex(hex, "000000");
  const r = parseInt(c.slice(0, 2), 16);
  const g = parseInt(c.slice(2, 4), 16);
  const b = parseInt(c.slice(4, 6), 16);
  const luma = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luma < 0.55;
}

function relativeLuminance(hex) {
  const c = cleanHex(hex, "000000");
  const channels = [
    parseInt(c.slice(0, 2), 16),
    parseInt(c.slice(2, 4), 16),
    parseInt(c.slice(4, 6), 16),
  ].map((v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrastRatio(fgHex, bgHex) {
  const l1 = relativeLuminance(fgHex);
  const l2 = relativeLuminance(bgHex);
  const bright = Math.max(l1, l2);
  const dark = Math.min(l1, l2);
  return (bright + 0.05) / (dark + 0.05);
}

function pickReadableTextColor(bgHex, light = "FFFFFF", dark = "111827") {
  const lightHex = cleanHex(light, "FFFFFF");
  const darkHex = cleanHex(dark, "111827");
  const bg = cleanHex(bgHex, "000000");
  const lightContrast = contrastRatio(lightHex, bg);
  const darkContrast = contrastRatio(darkHex, bg);
  if (Math.abs(lightContrast - darkContrast) < 0.15) {
    return isDark(bg) ? lightHex : darkHex;
  }
  return lightContrast >= darkContrast ? lightHex : darkHex;
}

function htmlToText(input) {
  return String(input || "")
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/\s+/g, " ")
    .trim();
}

function htmlToMultilineText(input) {
  return String(input || "")
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/p>/gi, "\n")
    .replace(/<\/li>/gi, "\n")
    .replace(/<li[^>]*>/gi, "• ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .join("\n");
}

function pick(obj, keys, fallback = "") {
  for (const key of keys) {
    if (obj && obj[key] !== undefined && obj[key] !== null) return obj[key];
  }
  return fallback;
}

function stableSlideId(sourceSlide, index) {
  return String(
    pick(sourceSlide, ["slide_id", "id", "page_number"], `slide-${index + 1}`),
  ).trim();
}

function stableBlockId(block, slideId, index) {
  return String(
    pick(block, ["block_id", "id"], `${slideId}-block-${index + 1}`),
  ).trim();
}

function blockType(block) {
  return String(block?.block_type || block?.type || "").toLowerCase().trim();
}

function blockText(block) {
  const content = block?.content;
  if (typeof content === "string") return content.trim();
  if (content && typeof content === "object") {
    const parts = [];
    for (const key of ["title", "body", "text", "label", "caption", "description"]) {
      const value = String(content[key] || "").trim();
      if (value) parts.push(value);
    }
    if (parts.length) return parts.join(" ");
  }
  const data = block?.data;
  if (data && typeof data === "object") {
    for (const key of ["title", "label", "description"]) {
      const value = String(data[key] || "").trim();
      if (value) return value;
    }
  }
  return "";
}

function normalizeTextKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, " ")
    .replace(/[^0-9a-z\u4e00-\u9fff%+.-]/g, "");
}

const targetSlideIdSet = new Set(targetSlideIds.map((id) => String(id).trim()).filter(Boolean));
const targetBlockIdSet = new Set(targetBlockIds.map((id) => String(id).trim()).filter(Boolean));

function isSlideInRetryScope(sourceSlide, index) {
  if (retryScope === "deck") return true;
  const slideId = stableSlideId(sourceSlide, index);
  if (retryScope === "slide") {
    if (targetSlideIdSet.size === 0) return true;
    return targetSlideIdSet.has(slideId);
  }
  if (retryScope === "block") {
    if (targetSlideIdSet.has(slideId)) return true;
    const elements = Array.isArray(sourceSlide?.elements) ? sourceSlide.elements : [];
    const blocks = Array.isArray(sourceSlide?.blocks) ? sourceSlide.blocks : [];
    if (targetBlockIdSet.size === 0) return true;
    const matchedElement = elements.some((el, idx2) => targetBlockIdSet.has(stableBlockId(el, slideId, idx2)));
    const matchedBlock = blocks.some((block, idx2) =>
      targetBlockIdSet.has(stableBlockId(block, slideId, idx2)),
    );
    return matchedElement || matchedBlock;
  }
  return true;
}

function collectBullets(slide, fallbackText = "") {
  const elements = Array.isArray(slide.elements) ? slide.elements : [];
  const blocks = Array.isArray(slide?.blocks) ? slide.blocks : [];
  const titleKey = normalizeTextKey(htmlToText(String(pick(slide, ["title"], ""))));
  const textElements = elements
    .filter((el) => String(el.type || "").toLowerCase() === "text")
    .sort((a, b) => Number(a.top || 0) - Number(b.top || 0));

  const lines = [];
  const sentenceSplit = /[。！？；;.!?]/;
  const bulletPrefix = /^[\s\-*+•·●○◆▶✓]+\s*/;
  const appendLines = (rawText) => {
    const plain = htmlToMultilineText(rawText);
    if (!plain) return;
    const lineChunks = plain
      .split(/\r?\n/)
      .map((line) => line.replace(bulletPrefix, "").trim())
      .filter(Boolean);
    if (lineChunks.length > 1) {
      for (const line of lineChunks) {
        if (line.length >= 4) lines.push(line);
      }
      return;
    }
    for (const line of plain.split(sentenceSplit)) {
      const t = line.replace(bulletPrefix, "").trim();
      if (t.length < 4) continue;
      lines.push(t);
    }
  };

  for (const block of blocks) {
    const t = blockType(block);
    if (!["subtitle", "body", "list", "quote", "icon_text", "text"].includes(t)) continue;
    appendLines(blockText(block));
  }

  for (const el of textElements) {
    appendLines(pick(el, ["content"], ""));
  }

  if (lines.length === 0 && fallbackText) {
    const fbLines = String(fallbackText).split(/\r?\n/).map((line) => line.replace(bulletPrefix, "").trim()).filter(Boolean);
    if (fbLines.length > 1) {
      for (const line of fbLines) {
        if (line.length >= 4) lines.push(line);
      }
    } else {
      for (const line of String(fallbackText).split(sentenceSplit)) {
        const t = line.replace(bulletPrefix, "").trim();
        if (t.length >= 4) lines.push(t);
      }
    }
  } else if (lines.length > 0 && lines.length < 4 && fallbackText) {
    for (const line of String(fallbackText).split(sentenceSplit)) {
      const t = line.replace(bulletPrefix, "").trim();
      if (t.length >= 6) lines.push(t);
      if (lines.length >= 8) break;
    }
  }

  const dedup = [];
  const seen = new Set();
  for (const item of lines) {
    const key = normalizeTextKey(item);
    if (!key || key === titleKey) continue;
    if (seen.has(key)) continue;
    seen.add(key);
    dedup.push(item);
    if (dedup.length >= 8) break;
  }
  return dedup;
}

function hasNumericSignal(lines) {
  return lines.some((item) => /[0-9]+(?:\.[0-9]+)?%?/.test(String(item || "")));
}

function buildSubtypeCandidates(slide, index, total) {
  const title = htmlToText(String(pick(slide, ["title"], ""))).toLowerCase();
  const elements = Array.isArray(slide?.elements) ? slide.elements : [];
  const blocks = Array.isArray(slide?.blocks) ? slide.blocks : [];
  const bullets = collectBullets(slide, "");
  const inferred = inferSubtype(slide);
  const hasTable =
    elements.some((el) => String(el?.type || "").toLowerCase() === "table")
    || blocks.some((block) => blockType(block) === "table");
  const hasChart =
    elements.some((el) => String(el?.type || "").toLowerCase() === "chart")
    || blocks.some((block) => ["chart", "kpi"].includes(blockType(block)));
  const candidates = [];

  const push = (value) => {
    const key = normalizeKey(value || "");
    if (!["content", "comparison", "timeline", "data", "table", "section"].includes(key)) return;
    if (!candidates.includes(key)) candidates.push(key);
  };

  const normalizedInferred = inferred === "mixed" ? "content" : inferred;
  if (normalizedInferred && normalizedInferred !== "content") push(normalizedInferred);
  if (hasTable) push("table");
  if (hasChart || hasNumericSignal(bullets)) push("data");
  if (/(\u5bf9\u6bd4|\u6bd4\u8f83|vs|versus|\u4f18\u52bf|\u5dee\u5f02)/.test(title)) push("comparison");
  if (/(\u8def\u7ebf|\u91cc\u7a0b\u7891|roadmap|timeline|\u9636\u6bb5|\u6b65\u9aa4|\u5b9e\u65bd)/.test(title)) push("timeline");
  if (/(\u7ae0\u8282|\u90e8\u5206|part|section)/.test(title)) push("section");
  if (/(\u6848\u4f8b|\u65b9\u6848|\u573a\u666f|\u5ba2\u6237)/.test(title)) push("comparison");
  if (index === total - 1 && hasNumericSignal(bullets)) push("data");
  if (normalizedInferred === "content") push("content");
  push("content");
  return candidates.length ? candidates : ["content"];
}

function planDeckSubtypes(deckSlides) {
  const total = Array.isArray(deckSlides) ? deckSlides.length : 0;
  if (total <= 0) return [];

  const typeCounts = new Map();
  const maxTypeRatio = total >= 8 ? 0.45 : 0.5;
  const maxPerType = Math.max(2, Math.floor(total * maxTypeRatio));
  const maxAdjacentRepeat = 1;
  let prevType = "";
  let runLength = 0;

  return deckSlides.map((slide, idx) => {
    const candidates = buildSubtypeCandidates(slide, idx, total);
    let selected = candidates[0] || "content";

    for (const candidate of candidates) {
      const used = Number(typeCounts.get(candidate) || 0);
      const exceedsRatio = used >= maxPerType && candidates.length > 1;
      const exceedsAdjacent =
        candidate === prevType && runLength >= maxAdjacentRepeat && candidates.length > 1;
      if (exceedsRatio || exceedsAdjacent) continue;
      selected = candidate;
      break;
    }

    const nextCount = Number(typeCounts.get(selected) || 0) + 1;
    typeCounts.set(selected, nextCount);
    if (selected === prevType) runLength += 1;
    else {
      prevType = selected;
      runLength = 1;
    }
    return selected;
  });
}

function extractChartSeries(slide) {
  const elements = Array.isArray(slide.elements) ? slide.elements : [];
  const chart = elements.find((el) => String(el.type || "").toLowerCase() === "chart" && el.chart_data);
  const chartData = chart?.chart_data
    || (() => {
      const blocks = Array.isArray(slide?.blocks) ? slide.blocks : [];
      const blockChart = blocks.find((block) => blockType(block) === "chart");
      if (!blockChart || typeof blockChart !== "object") return null;
      const data = blockChart?.data;
      if (data && typeof data === "object") return data;
      const content = blockChart?.content;
      if (content && typeof content === "object") return content;
      return null;
    })();
  if (!chartData) return null;
  const labels = Array.isArray(chartData?.labels) ? chartData.labels : [];
  const ds = Array.isArray(chartData?.datasets) ? chartData.datasets[0] : null;
  const values = Array.isArray(ds?.data) ? ds.data.map((v) => Number(v) || 0) : [];
  if (!labels.length || !values.length) return null;
  return labels.map((label, i) => ({ label: String(label), value: Number(values[i] || 0) })).slice(0, 5);
}

function inferSubtype(slide) {
  return inferSubtypeHeuristic(slide);
}

function resolveSubtypeByTemplate(subtype, templateFamily) {
  return resolveSubtypeByTemplateRegistry(subtype, templateFamily);
}

function selectStyle(styleInput, styleHint, topicText, preserveOriginal = false) {
  return selectStyleHeuristic(styleInput, styleHint, topicText, preserveOriginal);
}

function selectPalette(paletteInput, topicText, preserveOriginal = false) {
  return selectPaletteHeuristic(paletteInput, topicText, preserveOriginal);
}

function buildTheme(paletteKey, templateFamily = "dashboard_dark") {
  const colors = PALETTES[paletteKey] || PALETTES.luxury_mysterious;
  const bg = cleanHex(colors[2], "F2E9E4");
  const primary = cleanHex(colors[0], "22223B");
  const secondary = cleanHex(colors[1], "4A4E69");
  const accentStrong = cleanHex(colors[3], "C9ADA7");
  const accent = blendHex(accentStrong, bg, 0.55);
  const accentSoft = blendHex(accentStrong, bg, 0.72);
  const light = cleanHex(colors[4], "F2E9E4");
  const darkText = isDark(bg) ? "F8FAFC" : "111827";
  const mutedText = isDark(bg) ? "CBD5E1" : "6B7280";
  const baseTheme = {
    primary,
    secondary,
    accent,
    accentStrong,
    accentSoft,
    light,
    bg,
    white: "FFFFFF",
    darkText,
    mutedText,
  };
  return buildDarkTheme(baseTheme, templateFamily);
}

function addPageBadge(slide, index, theme, style) {
  const y = 5.14;
  const w = style === "pill" ? 0.7 : 0.55;
  const x = 9.85 - w;
  slide.addShape("roundRect", {
    x,
    y,
    w,
    h: 0.35,
    rectRadius: STYLE_RECIPES[style].badgeRadius,
    fill: { color: theme.accentStrong || theme.accent },
    line: { color: theme.accentStrong || theme.accent, pt: 0 },
  });
  slide.addText(String(index).padStart(2, "0"), {
    x,
    y,
    w,
    h: 0.35,
    fontFace: FONT_BY_STYLE[style].enBody,
    fontSize: 11,
    bold: true,
    color: theme.white,
    align: "center",
    valign: "mid",
    margin: 0,
  });
}

function addVisualBackdrop(slide, theme, visualConfig, mode = "content") {
  if (!visualConfig?.enabled) return;
  if (!visualConfig?.showDecorations) {
    if (mode === "cover") {
      slide.addShape("line", {
        x: 0,
        y: 4.86,
        w: 10,
        h: 0,
        line: { color: theme.light, pt: 0.6, transparency: 62 },
      });
    } else {
      slide.addShape("line", {
        x: 9.42,
        y: 0.92,
        w: 0,
        h: 4.03,
        line: { color: theme.light, pt: 0.55, transparency: 64 },
      });
    }
    return;
  }
  const transparencyBase = mode === "cover" ? 78 : 86;
  if (visualConfig.backdrop === "high-contrast") {
    const topRight = clampRectToSlide(7.08, 0.14, 2.74, 1.2, DECOR_INSET);
    const bottomLeft = clampRectToSlide(0.18, 4.18, 2.46, 1.2, DECOR_INSET);
    slide.addShape("roundRect", {
      ...topRight,
      rectRadius: 0.34,
      fill: { color: theme.accentSoft || theme.accent, transparency: transparencyBase + 4 },
      line: { color: theme.accentSoft || theme.accent, pt: 0 },
    });
    slide.addShape("roundRect", {
      ...bottomLeft,
      rectRadius: 0.32,
      fill: { color: theme.secondary, transparency: transparencyBase + 6 },
      line: { color: theme.secondary, pt: 0 },
    });
    return;
  }
  if (visualConfig.backdrop === "color-block") {
    const topRight = clampRectToSlide(7.3, 0.18, 2.45, 1.15, DECOR_INSET);
    slide.addShape("rect", {
      x: 0,
      y: 4.9,
      w: 10,
      h: 0.75,
      fill: { color: theme.accentSoft || theme.accent, transparency: 92 },
      line: { color: theme.accentSoft || theme.accent, pt: 0 },
    });
    slide.addShape("roundRect", {
      ...topRight,
      rectRadius: 0.35,
      fill: { color: theme.primary, transparency: transparencyBase + 4 },
      line: { color: theme.primary, pt: 0 },
    });
    return;
  }
  if (visualConfig.backdrop === "soft-gradient") {
    const topRight = clampRectToSlide(7.38, 0.22, 2.46, 1.12, DECOR_INSET);
    const bottomLeft = clampRectToSlide(0.18, 4.24, 2.2, 1.1, DECOR_INSET);
    slide.addShape("roundRect", {
      ...topRight,
      rectRadius: 0.3,
      fill: { color: theme.light, transparency: 58 },
      line: { color: theme.light, pt: 0 },
    });
    slide.addShape("roundRect", {
      ...bottomLeft,
      rectRadius: 0.3,
      fill: { color: theme.accentSoft || theme.accent, transparency: 92 },
      line: { color: theme.accentSoft || theme.accent, pt: 0 },
    });
    return;
  }
  if (mode === "cover") {
    slide.addShape("line", {
      x: 0,
      y: 4.7,
      w: 10,
      h: 0,
      line: { color: theme.light, pt: 0.65, transparency: 52 },
    });
    return;
  }
  slide.addShape("line", {
    x: 9.35,
    y: 0.92,
    w: 0,
    h: 4,
    line: { color: theme.light, pt: 0.65, transparency: 54 },
  });
  slide.addShape("line", {
    x: 9.62,
    y: 1.26,
    w: 0,
    h: 3.32,
    line: { color: theme.light, pt: 0.35, transparency: 62 },
  });
}

function addKpiChip(slide, text, x, y, theme, style) {
  const w = Math.max(0.95, Math.min(2.2, 0.75 + String(text || "").length * 0.12));
  slide.addShape("roundRect", {
    x,
    y,
    w,
    h: 0.34,
    rectRadius: Math.min(0.1, STYLE_RECIPES[style].badgeRadius + 0.03),
    fill: { color: theme.secondary, transparency: 20 },
    line: { color: theme.secondary, pt: 0 },
  });
  slide.addText(String(text || ""), {
    x,
    y,
    w,
    h: 0.34,
    fontFace: FONT_BY_STYLE[style].enBody,
    fontSize: 10,
    bold: true,
    color: pickReadableTextColor(theme.accentStrong || theme.accent, theme.white || "FFFFFF", "111827"),
    align: "center",
    valign: "mid",
    margin: 0,
  });
  return w;
}

function addCover(pres, title, subtitle, theme, style, visualConfig, sourceSlide = undefined, templateFamily = "hero_dark") {
  const recipe = STYLE_RECIPES[style];
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };
  maybeAddSvgLayer(
    slide,
    sourceSlide || { title, narration: subtitle, layout_grid: "hero_1" },
    theme,
    "hero_1",
  );
  if (!hasTemplateCoverRenderer(templateFamily)) {
    addVisualBackdrop(slide, theme, visualConfig, "cover");
  }
  if (
    renderTemplateCover({
      templateFamily,
      slide,
      title,
      subtitle,
      theme,
      style,
      sourceSlide,
      helpers: { FONT_BY_STYLE, FONT_ZH },
    })
  ) {
    return;
  }

  slide.addShape("rect", {
    x: 0,
    y: 0,
    w: 10,
    h: 0.95,
    fill: { color: theme.primary },
    line: { color: theme.primary, pt: 0 },
  });
  slide.addShape("roundRect", {
    x: recipe.pageMargin + 0.05,
    y: 1.25,
    w: 5.95,
    h: 3.25,
    rectRadius: recipe.cardRadius,
    fill: { color: theme.white, transparency: 1 },
    line: { color: theme.light, pt: 1 },
  });
  slide.addShape("roundRect", {
    x: 6.62,
    y: 1.25,
    w: 2.78,
    h: 3.25,
    rectRadius: recipe.cardRadius,
    fill: { color: theme.secondary, transparency: 70 },
    line: { color: theme.secondary, pt: 0 },
  });

  const titleText = String(title || "Presentation").trim();
  const titleSize = titleText.length > 22 ? (style === "sharp" ? 34 : 36) : style === "sharp" ? 40 : 44;
  slide.addText(titleText, {
    x: recipe.pageMargin + 0.3,
    y: 1.7,
    w: 5.45,
    h: 1.5,
    fontFace: FONT_ZH,
    fontSize: titleSize,
    bold: true,
    color: theme.primary,
    margin: 0,
  });
  const subtitleText = String(subtitle || "").trim();
  if (subtitleText) {
    slide.addText(subtitleText, {
      x: recipe.pageMargin + 0.3,
      y: 3.2,
      w: 5.35,
      h: 0.75,
      fontFace: FONT_BY_STYLE[style].enBody,
      fontSize: 13,
      color: theme.secondary,
      margin: 0,
      valign: "top",
    });
  }
}

function addToc(pres, sectionTitles, theme, style, visualConfig, pageNumber = 2, sourceSlide = undefined) {
  const recipe = STYLE_RECIPES[style];
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };
  maybeAddSvgLayer(
    slide,
    sourceSlide || { title: "Table of Contents", layout_grid: "grid_3" },
    theme,
    "grid_3",
  );
  addVisualBackdrop(slide, theme, visualConfig, "content");
  slide.addText("Table of Contents", {
    x: recipe.pageMargin,
    y: 0.58,
    w: 8.8,
    h: 0.65,
    fontFace: FONT_BY_STYLE[style].enTitle,
    fontSize: 30,
    bold: true,
    color: theme.primary,
    margin: 0,
  });

  sectionTitles.slice(0, 6).forEach((name, idx) => {
    const y = 1.34 + idx * 0.7;
    const rowFill = idx % 2 === 0 ? theme.white : cleanHex(theme.light, "E2E8F0");
    slide.addShape("roundRect", {
      x: recipe.pageMargin + 0.48,
      y: y - 0.08,
      w: 7.85,
      h: 0.48,
      rectRadius: 0.08,
      fill: { color: rowFill, transparency: 6 },
      line: { color: theme.light, pt: 0.3 },
    });
    slide.addShape("roundRect", {
      x: recipe.pageMargin,
      y,
      w: 0.44,
      h: 0.34,
      rectRadius: Math.min(0.1, recipe.badgeRadius),
      fill: { color: theme.secondary },
      line: { color: theme.secondary, pt: 0 },
    });
    slide.addText(String(idx + 1).padStart(2, "0"), {
      x: recipe.pageMargin,
      y,
      w: 0.44,
      h: 0.34,
      fontFace: FONT_BY_STYLE[style].enBody,
      fontSize: 11,
      bold: true,
      color: theme.white,
      align: "center",
      valign: "mid",
      margin: 0,
    });
    slide.addText(name, {
      x: recipe.pageMargin + 0.56,
      y: y + 0.02,
      w: 7.7,
      h: 0.4,
      fontFace: FONT_ZH,
      fontSize: 15,
      color: theme.darkText,
      margin: 0,
    });
  });

  addPageBadge(slide, pageNumber, theme, style);
}

function addHeader(slide, title, theme, style, visualConfig, templateFamily = "dashboard_dark") {
  const recipe = STYLE_RECIPES[style];
  const isLightTemplate = String(templateFamily || "").endsWith("_light");
  const lightBg = templateFamily === "consulting_warm_light" ? "F7F3EE" : "F4F7FC";
  const bgColor = isLightTemplate ? lightBg : theme.bg;
  const borderColor = isLightTemplate ? (templateFamily === "consulting_warm_light" ? "D8BFAA" : "CFDAEC") : theme.borderColor;
  const titleColor = isLightTemplate
    ? (templateFamily === "consulting_warm_light" ? "3A2A23" : "0F1E35")
    : pickReadableTextColor(theme.primary, theme.white || "FFFFFF", theme.darkText || "111827");
  const accentColor = isLightTemplate ? (templateFamily === "consulting_warm_light" ? "9B3B2E" : "2F67E8") : theme.primary;
  const allowBackdropDecor = !hasTemplateContentRenderer(templateFamily);
  slide.background = { color: bgColor };
  if (!isLightTemplate && allowBackdropDecor) {
    addVisualBackdrop(slide, theme, visualConfig, "content");
  }
  slide.addShape("rect", {
    x: 0,
    y: 0,
    w: 10,
    h: recipe.headerHeight,
    fill: { color: isLightTemplate ? bgColor : theme.primary },
    line: { color: isLightTemplate ? borderColor : theme.primary, pt: isLightTemplate ? 0.5 : 0 },
  });
  if (isLightTemplate) {
    slide.addShape("line", {
      x: 0.62,
      y: recipe.headerHeight - 0.02,
      w: 8.7,
      h: 0,
      line: { color: accentColor, pt: 1.8, transparency: 16 },
    });
    slide.addShape("roundRect", {
      x: 0.58,
      y: 0.14,
      w: 0.06,
      h: 0.32,
      rectRadius: 0.03,
      fill: { color: accentColor },
      line: { color: accentColor, pt: 0 },
    });
  }
  const titleText = String(title || "");
  const titleLen = titleText.length;
  const baseTitleSize = recipe.titleSize;
  const dynamicTitleSize = titleLen > 28 ? baseTitleSize - 3 : titleLen > 20 ? baseTitleSize - 1 : baseTitleSize;
  slide.addText(title, {
    x: isLightTemplate ? recipe.pageMargin + 0.12 : recipe.pageMargin,
    y: 0.1,
    w: visualConfig?.enabled ? 7.6 : 8.8,
    h: 0.5,
    fontFace: FONT_ZH,
    fontSize: Math.max(18, dynamicTitleSize),
    bold: true,
    color: titleColor,
    margin: 0,
  });
}

function addBulletList(slide, bullets, x, y, w, h, theme, style, maxItems = 5) {
  const recipe = STYLE_RECIPES[style];
  bullets.slice(0, maxItems).forEach((item, i) => {
    const text = String(item || "").trim();
    if (!text) return;
    const size = text.length > 44 ? Math.max(12, recipe.bodySize - 2) : recipe.bodySize;
    const rowH = text.length > 44 ? 0.52 : 0.46;
    const yy = y + i * Math.max(recipe.bulletStep, rowH + 0.06);
    if (yy + rowH > y + h) return;
    slide.addText(`• ${item}`, {
      x: x + 0.02,
      y: yy,
      w: Math.max(0.6, w - 0.04),
      h: rowH,
      fontFace: FONT_ZH,
      fontSize: size,
      bold: false,
      color: theme.darkText,
      margin: 0,
    });
  });
}

function addDataBars(slide, series, x, y, w, h, theme, style) {
  const maxValue = Math.max(1, ...series.map((s) => s.value));
  const gap = 0.14;
  const barAreaH = h - 0.28;
  const itemH = (barAreaH - gap * (series.length - 1)) / series.length;
  series.forEach((it, i) => {
    const yy = y + i * (itemH + gap);
    const barW = Math.max(0.2, ((w - 1.4) * it.value) / maxValue);
    slide.addText(it.label.slice(0, 10), {
      x,
      y: yy + 0.02,
      w: 1.15,
      h: itemH,
      fontFace: FONT_ZH,
      fontSize: style === "sharp" ? 10 : 11,
      bold: false,
      color: theme.mutedText,
      margin: 0,
    });
    slide.addShape("roundRect", {
      x: x + 1.2,
      y: yy + 0.03,
      w: barW,
      h: Math.max(0.12, itemH - 0.08),
      rectRadius: Math.min(0.08, STYLE_RECIPES[style].cardRadius),
    fill: { color: theme.accentStrong || theme.accent },
    line: { color: theme.accentStrong || theme.accent, pt: 0 },
  });
    slide.addText(String(it.value), {
      x: x + 1.2 + barW + 0.06,
      y: yy + 0.02,
      w: 0.8,
      h: itemH,
      fontFace: FONT_BY_STYLE[style].enBody,
      fontSize: 10,
      bold: true,
      color: theme.secondary,
      margin: 0,
    });
  });
}

function buildTableRows(slide, bullets) {
  const tableEl = (Array.isArray(slide.elements) ? slide.elements : []).find(
    (el) => String(el.type || "").toLowerCase() === "table" && Array.isArray(el.table_rows),
  );
  if (tableEl && tableEl.table_rows.length) {
    return tableEl.table_rows.map((row) => row.map((c) => String(c)));
  }
  const rows = [["Item", "Key Point"]];
  bullets.slice(0, 5).forEach((b, i) => rows.push([`P${i + 1}`, b]));
  return rows;
}

function isNumericCell(value) {
  if (typeof value === "number") return Number.isFinite(value);
  const text = String(value ?? "").trim();
  if (!text) return false;
  return /^-?\d+(\.\d+)?%?$/.test(text.replace(/,/g, ""));
}

function renderEnhancedTable(slide, position, rows, theme) {
  const normalizedRows = Array.isArray(rows)
    ? rows
      .filter((row) => Array.isArray(row) && row.length > 0)
      .map((row) => row.map((cell) => String(cell ?? "").trim()))
    : [];
  if (!normalizedRows.length) return false;

  const headers = normalizedRows[0];
  const body = normalizedRows.slice(1);
  const tableData = [
    headers.map((header) => ({
      text: header,
      options: {
        bold: true,
        fontSize: 12,
        color: "FFFFFF",
        fill: { color: theme.primary },
        align: "center",
      },
    })),
    ...body.map((row, i) =>
      headers.map((_, colIdx) => {
        const cell = row[colIdx] ?? "";
        return {
          text: String(cell),
          options: {
            fontSize: 11,
            fill: { color: i % 2 === 0 ? "FFFFFF" : theme.light },
            align: isNumericCell(cell) ? "right" : "left",
          },
        };
      })),
  ];

  slide.addTable(tableData, {
    x: position.x,
    y: position.y,
    w: position.w,
    h: position.h,
    border: { type: "solid", pt: 0.5, color: "E2E8F0" },
    colW: headers.map(() => position.w / headers.length),
    autoPage: false,
  });
  return true;
}

function splitComparison(bullets) {
  const half = Math.ceil(bullets.length / 2);
  return {
    left: bullets.slice(0, half),
    right: bullets.slice(half),
  };
}

function addSectionDivider(slide, title, pageNumber, theme, style) {
  slide.background = { color: theme.primary };
  slide.addShape("roundRect", {
    x: 0.9,
    y: 1.25,
    w: 8.2,
    h: 2.9,
    rectRadius: STYLE_RECIPES[style].cardRadius,
    fill: { color: theme.bg, transparency: 10 },
    line: { color: theme.light, pt: 1 },
  });
  slide.addText(String(pageNumber).padStart(2, "0"), {
    x: 1.3,
    y: 1.8,
    w: 2,
    h: 0.9,
    fontFace: FONT_BY_STYLE[style].enTitle,
    fontSize: 70,
    bold: true,
    color: theme.accent,
    margin: 0,
  });
  slide.addText(title, {
    x: 3.2,
    y: 2.05,
    w: 5.4,
    h: 0.8,
    fontFace: FONT_ZH,
    fontSize: 34,
    bold: true,
    color: theme.white,
    margin: 0,
  });
  addPageBadge(slide, pageNumber, theme, style);
}

function addContentSlide(
  pres,
  slideData,
  pageNumber,
  theme,
  style,
  visualConfig,
  forcedSubtype = "",
  templateFamily = "dashboard_dark",
) {
  const recipe = STYLE_RECIPES[style];
  const title = htmlToText(String(pick(slideData, ["title"], `Slide ${pageNumber}`))) || `Slide ${pageNumber}`;
  const narration = htmlToText(String(pick(slideData, ["narration", "speaker_notes", "speakerNotes"], "")));
  const bullets = collectBullets(slideData, narration);
  const subtype = resolveSubtypeByTemplate(
    normalizeKey(forcedSubtype || "") || inferSubtype(slideData),
    templateFamily,
  );
  const maxBullets = Math.max(3, visualConfig?.maxBullets || 5);

  const slide = pres.addSlide();
  maybeAddSvgLayer(slide, slideData, theme, pick(slideData, ["layout_grid", "layout"], "split_2"));
  if (subtype === "section") {
    addSectionDivider(slide, title, pageNumber, theme, style);
    return;
  }

  addHeader(slide, title, theme, style, visualConfig, templateFamily);
  const bodyTop = recipe.headerHeight + recipe.gap;
  const bodyBottom = 5.05;

  if (
    renderTemplateContent({
      templateFamily,
      slide,
      title,
      bullets,
      pageNumber,
      theme,
      style,
      sourceSlide: slideData,
      helpers: {
        FONT_BY_STYLE,
        FONT_ZH,
        addPageBadge,
        addBulletList,
        pptx: pptxgen,
      },
    })
  ) {
    return;
  }

  if (subtype === "table") {
    const rows = buildTableRows(slideData, bullets);
    renderEnhancedTable(slide, {
      x: recipe.pageMargin,
      y: bodyTop,
      w: 9.2,
      h: bodyBottom - bodyTop,
    }, rows, theme);
  } else if (subtype === "comparison") {
    const { left, right } = splitComparison(
      bullets.length ? bullets : ["要点A", "要点B", "要点C", "要点D"],
    );
    const colW = (9.2 - recipe.gap) / 2;
    slide.addShape("roundRect", {
      x: recipe.pageMargin,
      y: bodyTop,
      w: colW,
      h: bodyBottom - bodyTop,
      rectRadius: recipe.cardRadius,
      fill: { color: theme.white, transparency: 4 },
      line: { color: theme.light, pt: 1 },
    });
    slide.addShape("roundRect", {
      x: recipe.pageMargin + colW + recipe.gap,
      y: bodyTop,
      w: colW,
      h: bodyBottom - bodyTop,
      rectRadius: recipe.cardRadius,
      fill: { color: theme.white, transparency: 4 },
      line: { color: theme.light, pt: 1 },
    });
    slide.addText("A", {
      x: recipe.pageMargin + 0.18,
      y: bodyTop + 0.14,
      w: 0.4,
      h: 0.3,
      fontFace: FONT_BY_STYLE[style].enTitle,
      fontSize: 16,
      bold: true,
      color: theme.secondary,
      margin: 0,
    });
    slide.addText("B", {
      x: recipe.pageMargin + colW + recipe.gap + 0.18,
      y: bodyTop + 0.14,
      w: 0.4,
      h: 0.3,
      fontFace: FONT_BY_STYLE[style].enTitle,
      fontSize: 16,
      bold: true,
      color: theme.secondary,
      margin: 0,
    });
    addBulletList(slide, left, recipe.pageMargin + 0.2, bodyTop + 0.45, colW - 0.34, bodyBottom - bodyTop - 0.5, theme, style, maxBullets);
    addBulletList(
      slide,
      right,
      recipe.pageMargin + colW + recipe.gap + 0.2,
      bodyTop + 0.45,
      colW - 0.34,
      bodyBottom - bodyTop - 0.5,
      theme,
      style,
      maxBullets,
    );
  } else if (subtype === "timeline") {
    const steps = (bullets.length ? bullets : ["阶段一", "阶段二", "阶段三", "阶段四"]).slice(0, 5);
    const lineY = bodyTop + 1.1;
    const startX = recipe.pageMargin + 0.45;
    const endX = recipe.pageMargin + 8.75;
    const gapX = steps.length > 1 ? (endX - startX) / (steps.length - 1) : 0;
    slide.addShape("line", {
      x: startX,
      y: lineY + 0.16,
      w: Math.max(0, gapX * (steps.length - 1)),
      h: 0,
      line: { color: theme.secondary, pt: 2 },
    });
    steps.forEach((s, i) => {
      const xx = startX + gapX * i;
      const itemW = Math.min(1.7, Math.max(1.2, gapX * 0.95));
      slide.addShape("roundRect", {
        x: xx - 0.14,
        y: lineY,
        w: 0.32,
        h: 0.32,
        rectRadius: 0.16,
        fill: { color: theme.accent },
        line: { color: theme.accent, pt: 0 },
      });
      slide.addText(String(i + 1), {
        x: xx - 0.14,
        y: lineY,
        w: 0.32,
        h: 0.32,
        fontFace: FONT_BY_STYLE[style].enBody,
        fontSize: 11,
        bold: true,
        color: theme.white,
        align: "center",
        valign: "mid",
        margin: 0,
      });
      slide.addText(s, {
        x: xx - itemW / 2,
        y: lineY + 0.45,
        w: itemW,
        h: 0.9,
        fontFace: FONT_ZH,
        fontSize: 13,
        bold: false,
        color: theme.darkText,
        align: "center",
        margin: 0,
      });
    });
  } else {
    const leftW = visualConfig?.enabled ? 5.55 : 5.9;
    const safeBullets = bullets.length ? bullets : [narration || title];
    const useSingleColumn = safeBullets.length >= 5;
    if (useSingleColumn) {
      slide.addShape("roundRect", {
        x: recipe.pageMargin,
        y: bodyTop,
        w: 9.2,
        h: bodyBottom - bodyTop,
        rectRadius: recipe.cardRadius,
        fill: { color: theme.white, transparency: 4 },
        line: { color: theme.light, pt: 1 },
      });
      addBulletList(
        slide,
        safeBullets,
        recipe.pageMargin + 0.18,
        bodyTop + 0.18,
        8.8,
        bodyBottom - bodyTop - 0.3,
        theme,
        style,
        Math.max(maxBullets, 6),
      );
      addPageBadge(slide, pageNumber, theme, style);
      return;
    }
    addBulletList(slide, safeBullets, recipe.pageMargin, bodyTop, leftW, bodyBottom - bodyTop, theme, style, maxBullets);

    const rightX = recipe.pageMargin + leftW + recipe.gap;
    const rightW = 9.2 - leftW - recipe.gap;
    slide.addShape("roundRect", {
      x: rightX,
      y: bodyTop,
      w: rightW,
      h: bodyBottom - bodyTop,
      rectRadius: recipe.cardRadius,
      fill: { color: theme.white, transparency: 6 },
      line: { color: theme.light, pt: 1 },
    });
    if (visualConfig?.enabled) {
      slide.addShape("rect", {
        x: rightX + 0.16,
        y: bodyTop + 0.16,
        w: rightW - 0.32,
        h: 0.06,
        fill: { color: theme.light, transparency: 15 },
        line: { color: theme.light, pt: 0 },
      });
    }

    if (subtype === "data") {
      const bars = extractChartSeries(slideData);
      if (bars && bars.length) {
        addDataBars(slide, bars, rightX + 0.2, bodyTop + 0.22, rightW - 0.4, bodyBottom - bodyTop - 0.4, theme, style);
      } else {
        const first = bullets[0] || title;
        slide.addText(first.slice(0, 42), {
          x: rightX + 0.2,
          y: bodyTop + 0.6,
          w: rightW - 0.4,
          h: 0.8,
          fontFace: FONT_BY_STYLE[style].enTitle,
          fontSize: 17,
          bold: true,
          color: theme.secondary,
          align: "center",
          valign: "mid",
          margin: 0,
        });
      }
    } else {
      const keyMetric = (bullets.find((b) => /[0-9]+(?:\.[0-9]+)?%?/.test(b)) || bullets[0] || title).slice(0, 26);
      slide.addText(keyMetric, {
        x: rightX + 0.2,
        y: bodyTop + 0.65,
        w: rightW - 0.4,
        h: 0.8,
        fontFace: FONT_BY_STYLE[style].enTitle,
        fontSize: 16,
        bold: true,
        color: theme.secondary,
        align: "center",
        valign: "mid",
        margin: 0,
      });
      if (visualConfig?.enabled) {
        const second = (safeBullets[1] || safeBullets[0] || "").slice(0, 14);
        if (second) {
          slide.addText(second, {
            x: rightX + 0.2,
            y: bodyTop + 1.55,
            w: rightW - 0.4,
            h: 0.4,
            fontFace: FONT_ZH,
            fontSize: 12,
            color: theme.mutedText,
            align: "center",
            margin: 0,
          });
        }
      }
    }
  }

  addPageBadge(slide, pageNumber, theme, style);
}

function collectTextLines(slideData, fallbackText = "") {
  const elements = Array.isArray(slideData?.elements) ? slideData.elements : [];
  const blocks = Array.isArray(slideData?.blocks) ? slideData.blocks : [];
  const textElements = elements
    .filter((el) => String(el?.type || "").toLowerCase() === "text")
    .sort((a, b) => Number(a?.top || 0) - Number(b?.top || 0));

  const lines = [];
  for (const el of textElements) {
    const text = htmlToMultilineText(pick(el, ["content"], ""));
    if (!text) continue;
    for (const line of text.split("\n")) {
      const cleaned = String(line || "").trim();
      if (cleaned) lines.push(cleaned);
    }
  }

  if (!lines.length && fallbackText) {
    const fb = htmlToMultilineText(fallbackText);
    for (const line of fb.split("\n")) {
      const cleaned = String(line || "").trim();
      if (cleaned) lines.push(cleaned);
    }
  }

  return lines;
}

function addVerbatimContentSlide(pres, slideData, pageNumber, theme, style, visualConfig, templateFamily = "dashboard_dark") {
  const recipe = STYLE_RECIPES[style];
  const title = htmlToText(String(pick(slideData, ["title"], `Slide ${pageNumber}`))) || `Slide ${pageNumber}`;
  const narration = htmlToMultilineText(String(pick(slideData, ["narration", "speaker_notes", "speakerNotes"], "")));
  const lines = collectTextLines(slideData, narration || title);
  const bodyText = lines.join("\n");

  const slide = pres.addSlide();
  addHeader(slide, title, theme, style, visualConfig, templateFamily);

  const bodyTop = recipe.headerHeight + recipe.gap;
  const bodyBottom = 5.05;
  const boxX = recipe.pageMargin;
  const boxW = 9.2;
  const boxH = bodyBottom - bodyTop;

  slide.addShape("roundRect", {
    x: boxX,
    y: bodyTop,
    w: boxW,
    h: boxH,
    rectRadius: recipe.cardRadius,
    fill: { color: theme.white, transparency: 4 },
    line: { color: theme.light, pt: 1 },
  });

  const textLen = bodyText.length;
  let fontSize = Math.max(14, recipe.bodySize);
  if (textLen > 900) fontSize = 12;
  else if (textLen > 700) fontSize = 13;
  else if (textLen > 520) fontSize = 14;
  else if (textLen > 360) fontSize = 15;

  slide.addText(bodyText || title, {
    x: boxX + 0.24,
    y: bodyTop + 0.18,
    w: boxW - 0.48,
    h: boxH - 0.26,
    fontFace: FONT_ZH,
    fontSize,
    bold: false,
    color: theme.darkText,
    margin: 0,
    valign: "top",
  });

  addPageBadge(slide, pageNumber, theme, style);
}

function addSummarySlide(pres, title, bullets, pageNumber, theme, style, visualConfig, sourceSlide = undefined) {
  const recipe = STYLE_RECIPES[style];
  const maxBullets = Math.max(3, visualConfig?.maxBullets || 5);
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };
  maybeAddSvgLayer(
    slide,
    sourceSlide || { title, layout_grid: "hero_1" },
    theme,
    "hero_1",
  );
  addVisualBackdrop(slide, theme, visualConfig, "content");
  slide.addText(title || "Summary", {
    x: recipe.pageMargin,
    y: 0.72,
    w: 8.4,
    h: 0.8,
    fontFace: FONT_ZH,
    fontSize: 36,
    bold: true,
    color: theme.primary,
    margin: 0,
  });
  slide.addShape("line", {
    x: recipe.pageMargin,
    y: 1.58,
    w: 1.8,
    h: 0,
    line: { color: theme.accentStrong || theme.accent, pt: 1.5 },
  });
  slide.addShape("roundRect", {
    x: recipe.pageMargin + 0.05,
    y: 1.84,
    w: 8.9,
    h: 3.28,
    rectRadius: recipe.cardRadius,
    fill: { color: theme.white, transparency: 2 },
    line: { color: theme.light, pt: 1 },
  });

  bullets.slice(0, maxBullets).forEach((item, i) => {
    slide.addText(`• ${item}`, {
      x: recipe.pageMargin + 0.24,
      y: 2.03 + i * Math.max(recipe.bulletStep, 0.5),
      w: 8.45,
      h: 0.46,
      fontFace: FONT_ZH,
      fontSize: recipe.bodySize,
      bold: false,
      color: theme.darkText,
      margin: 0,
    });
  });

  slide.addText("Thank you", {
    x: recipe.pageMargin + 0.24,
    y: 4.9,
    w: 3.3,
    h: 0.35,
    fontFace: FONT_BY_STYLE[style].enBody,
    fontSize: 14,
    color: theme.mutedText,
    margin: 0,
  });
  addPageBadge(slide, pageNumber, theme, style);
}

function mdEscape(text) {
  return String(text || "")
    .replace(/\\/g, "\\\\")
    .replace(/\|/g, "\\|")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\r?\n/g, " ")
    .trim();
}

function pickHighlightKeyword(lines) {
  for (const line of lines) {
    const text = String(line || "");
    const match = text.match(/[0-9]+(?:\.[0-9]+)?%?/);
    if (match && match[0]) return match[0];
  }
  for (const line of lines) {
    const text = String(line || "").trim();
    if (text.length >= 2) return text.slice(0, Math.min(10, text.length));
  }
  return "重点";
}

function asScriptLine(sourceSlide, fallbackText) {
  const narration = htmlToText(
    String(
      pick(sourceSlide, ["narration", "speaker_notes", "speakerNotes"], fallbackText || ""),
    ),
  );
  const text = narration || fallbackText || "本页重点讲解";
  return [{ role: "host", text }];
}

function asDuration(sourceSlide, fallback = 6) {
  const raw = Number(pick(sourceSlide, ["duration"], fallback));
  if (!Number.isFinite(raw) || raw <= 0) return fallback;
  return Math.max(3, Math.round(raw));
}

function asNarrationAudio(sourceSlide) {
  const url = pick(sourceSlide, ["narration_audio_url", "narrationAudioUrl"], "");
  return url ? String(url) : undefined;
}

function renderIdentity(pageNumber, sourceSlide) {
  return {
    deck_id: deckId || undefined,
    slide_id: stableSlideId(sourceSlide || {}, Math.max(pageNumber - 1, 0)),
  };
}

function buildCoverRenderSlide(pageNumber, title, subtitle, style, paletteKey, sourceSlide, templateFamily = "hero_dark") {
  const subtitleText = String(subtitle || "").trim();
  const subtitleLine = subtitleText ? `\n## ${mdEscape(subtitleText)}` : "";
  const templateProfiles = getTemplateProfiles(templateFamily);
  return {
    ...renderIdentity(pageNumber, sourceSlide),
    page_number: pageNumber,
    slide_type: "cover",
    template_family: templateFamily,
    ...templateProfiles,
    svg_mode: svgModeEnabled ? "on" : "off",
    markdown: `<!-- _class: lead -->\n# ${mdEscape(title || "Presentation")}${subtitleLine}`,
    script: asScriptLine(sourceSlide, title || "封面介绍"),
    actions: [
      { type: "highlight", keyword: pickHighlightKeyword([title, subtitleText]), startFrame: 20 },
    ],
    narration_audio_url: asNarrationAudio(sourceSlide),
    duration: asDuration(sourceSlide, 5),
  };
}

function buildTocRenderSlide(pageNumber, sectionTitles, sourceSlide) {
  const list = sectionTitles.slice(0, 6).map((s, i) => `- ${String(i + 1).padStart(2, "0")} ${mdEscape(s)}`);
  const templateFamily = resolveSlideTemplateFamily(sourceSlide || {});
  const templateProfiles = getTemplateProfiles(templateFamily);
  return {
    ...renderIdentity(pageNumber, sourceSlide),
    page_number: pageNumber,
    slide_type: "toc",
    template_family: templateFamily,
    ...templateProfiles,
    markdown: `# Table of Contents\n${list.join("\n")}\n\n<mark>Agenda</mark>`,
    script: asScriptLine(sourceSlide, "目录与章节安排"),
    actions: [{ type: "appear_items", items: sectionTitles.slice(0, 5), startFrame: 24 }],
    narration_audio_url: asNarrationAudio(sourceSlide),
    duration: asDuration(sourceSlide, 6),
  };
}

function buildTableMarkdown(rows) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return "- 暂无表格数据";
  }
  const safeRows = rows
    .map((row) => (Array.isArray(row) ? row.map((c) => mdEscape(c)) : []))
    .filter((row) => row.length > 0);
  if (!safeRows.length) return "- 暂无表格数据";
  const header = safeRows[0];
  const divider = header.map(() => "---");
  const body = safeRows.slice(1, 6);
  const lines = [
    `| ${header.join(" | ")} |`,
    `| ${divider.join(" | ")} |`,
    ...body.map((row) => `| ${row.join(" | ")} |`),
  ];
  return lines.join("\n");
}

function buildContentRenderSlide(pageNumber, sourceSlide, subtype, title, bullets, templateFamily = "dashboard_dark") {
  const safeBullets = (bullets.length ? bullets : [title]).slice(0, 6);
  const actions = [];
  const templateProfiles = getTemplateProfiles(templateFamily);
  if (safeBullets.length) {
    actions.push({ type: "appear_items", items: safeBullets.slice(0, 4), startFrame: 24 });
  }
  const keyword = pickHighlightKeyword([title, ...safeBullets]);
  if (keyword) {
    actions.push({ type: "highlight", keyword, startFrame: 36 });
  }

  if (subtype === "section") {
    return {
      ...renderIdentity(pageNumber, sourceSlide),
      page_number: pageNumber,
      slide_type: "divider",
      template_family: templateFamily,
      ...templateProfiles,
      svg_mode: svgModeEnabled ? "on" : "off",
      markdown: `<!-- _class: lead -->\n# ${mdEscape(title)}\n<mark>Section</mark>`,
      script: asScriptLine(sourceSlide, title),
      actions: [{ type: "highlight", keyword: pickHighlightKeyword([title]), startFrame: 20 }],
      narration_audio_url: asNarrationAudio(sourceSlide),
      duration: asDuration(sourceSlide, 4),
    };
  }

  if (subtype === "timeline") {
    return {
      ...renderIdentity(pageNumber, sourceSlide),
      page_number: pageNumber,
      slide_type: "timeline",
      template_family: templateFamily,
      ...templateProfiles,
      svg_mode: svgModeEnabled ? "on" : "off",
      markdown: `# ${mdEscape(title)}\n${safeBullets.map((b, i) => `${i + 1}. ${mdEscape(b)}`).join("\n")}`,
      script: asScriptLine(sourceSlide, title),
      actions,
      narration_audio_url: asNarrationAudio(sourceSlide),
      duration: asDuration(sourceSlide, 6),
    };
  }

  if (subtype === "table") {
    const rows = buildTableRows(sourceSlide, safeBullets);
    return {
      ...renderIdentity(pageNumber, sourceSlide),
      page_number: pageNumber,
      slide_type: "grid_2",
      template_family: templateFamily,
      ...templateProfiles,
      svg_mode: svgModeEnabled ? "on" : "off",
      markdown: `# ${mdEscape(title)}\n${buildTableMarkdown(rows)}`,
      script: asScriptLine(sourceSlide, title),
      actions: [{ type: "zoom_in", region: "center", startFrame: 28 }],
      narration_audio_url: asNarrationAudio(sourceSlide),
      duration: asDuration(sourceSlide, 7),
    };
  }

  if (subtype === "comparison") {
    const { left, right } = splitComparison(safeBullets);
    return {
      ...renderIdentity(pageNumber, sourceSlide),
      page_number: pageNumber,
      slide_type: "grid_2",
      template_family: templateFamily,
      ...templateProfiles,
      svg_mode: svgModeEnabled ? "on" : "off",
      markdown: `# ${mdEscape(title)}\n<div class="grid-2">\n<div class="card">\n\n### A\n${left.map((b) => `- ${mdEscape(b)}`).join("\n")}\n\n</div>\n<div class="card accent">\n\n### B\n${right.map((b) => `- ${mdEscape(b)}`).join("\n")}\n\n</div>\n</div>`,
      script: asScriptLine(sourceSlide, title),
      actions: [
        { type: "appear_items", items: safeBullets.slice(0, 4), startFrame: 24 },
        { type: "circle", x: 560, y: 530, r: 180, startFrame: 44 },
      ],
      narration_audio_url: asNarrationAudio(sourceSlide),
      duration: asDuration(sourceSlide, 7),
    };
  }

  if (subtype === "data") {
    const bars = extractChartSeries(sourceSlide);
    const dataLines = bars && bars.length
      ? bars.map((b) => `- ${mdEscape(b.label)}: <mark>${b.value}</mark>`)
      : safeBullets.map((b) => `- ${mdEscape(b)}`);
    return {
      ...renderIdentity(pageNumber, sourceSlide),
      page_number: pageNumber,
      slide_type: "quote_stat",
      template_family: templateFamily,
      ...templateProfiles,
      svg_mode: svgModeEnabled ? "on" : "off",
      markdown: `# ${mdEscape(title)}\n${dataLines.join("\n")}`,
      script: asScriptLine(sourceSlide, title),
      actions: [
        { type: "zoom_in", region: "center", startFrame: 26 },
        { type: "highlight", keyword, startFrame: 42 },
      ],
      narration_audio_url: asNarrationAudio(sourceSlide),
      duration: asDuration(sourceSlide, 6),
    };
  }

  return {
    ...renderIdentity(pageNumber, sourceSlide),
    page_number: pageNumber,
    slide_type: "grid_3",
    template_family: templateFamily,
    ...templateProfiles,
    svg_mode: svgModeEnabled ? "on" : "off",
    markdown: `# ${mdEscape(title)}\n${safeBullets.map((b) => `- ${mdEscape(b)}`).join("\n")}`,
    script: asScriptLine(sourceSlide, title),
    actions,
    narration_audio_url: asNarrationAudio(sourceSlide),
    duration: asDuration(sourceSlide, 6),
  };
}

function buildSummaryRenderSlide(pageNumber, title, bullets, sourceSlide, templateFamily = "hero_dark") {
  const summaryBullets = (bullets.length ? bullets : [title || "Summary"]).slice(0, 5);
  const templateProfiles = getTemplateProfiles(templateFamily);
  return {
    ...renderIdentity(pageNumber, sourceSlide),
    page_number: pageNumber,
    slide_type: "summary",
    template_family: templateFamily,
    ...templateProfiles,
    svg_mode: svgModeEnabled ? "on" : "off",
    markdown: `# ${mdEscape(title || "Summary")}\n${summaryBullets.map((b) => `- ${mdEscape(b)}`).join("\n")}\n\n<mark>Thank you</mark>`,
    script: asScriptLine(sourceSlide, title || "总结"),
    actions: [{ type: "appear_items", items: summaryBullets.slice(0, 5), startFrame: 22 }],
    narration_audio_url: asNarrationAudio(sourceSlide),
    duration: asDuration(sourceSlide, 6),
  };
}

function collectBentoBlockTexts(sourceSlide) {
  const blocks = Array.isArray(sourceSlide?.blocks) ? sourceSlide.blocks : [];
  const lines = [];
  for (const block of blocks) {
    const content = block?.content;
    if (typeof content === "string" && content.trim()) {
      lines.push(content.trim());
      continue;
    }
    if (content && typeof content === "object") {
      for (const key of ["title", "body", "text", "label"]) {
        const value = content[key];
        if (typeof value === "string" && value.trim()) lines.push(value.trim());
      }
    }
  }

  if (!lines.length) {
    for (const block of blocks) {
      const t = blockType(block);
      if (!["title", "subtitle", "body", "list", "quote", "icon_text", "text"].includes(t)) continue;
      const text = htmlToMultilineText(blockText(block));
      if (!text) continue;
      for (const line of text.split("\n")) {
        const cleaned = String(line || "").trim();
        if (cleaned) lines.push(cleaned);
      }
    }
  }
  return Array.from(new Set(lines)).slice(0, 6);
}

function buildBentoRenderSlide(pageNumber, sourceSlide, title, bullets, templateFamily = "bento_2x2_dark") {
  const gridName = normalizeKey(String(sourceSlide?.layout_grid || "")) || "grid_2";
  const safeBullets = (bullets.length ? bullets : [title]).slice(0, 6);
  const templateProfiles = getTemplateProfiles(templateFamily);
  return {
    ...renderIdentity(pageNumber, sourceSlide),
    page_number: pageNumber,
    slide_type: gridName,
    template_family: templateFamily,
    ...templateProfiles,
    svg_mode: svgModeEnabled ? "on" : "off",
    markdown: `# ${mdEscape(title)}\n${safeBullets.map((b) => `- ${mdEscape(b)}`).join("\n")}`,
    script: asScriptLine(sourceSlide, title),
    actions: [{ type: "appear_items", items: safeBullets.slice(0, 4), startFrame: 20 }],
    narration_audio_url: asNarrationAudio(sourceSlide),
    duration: asDuration(sourceSlide, 6),
  };
}

function shouldAttemptBentoSlide(sourceSlide, templateFamily = "dashboard_dark") {
  if (!canRenderBentoSlide(sourceSlide)) return false;
  const explicitType = normalizeKey(
    pick(sourceSlide || {}, ["page_type", "pageType", "slide_type", "slideType", "subtype"], ""),
  );
  if (["cover", "toc", "summary", "divider", "section", "hero_1"].includes(explicitType)) {
    return false;
  }
  const family = normalizeTemplateFamily(templateFamily, "content", sourceSlide?.layout_grid || "split_2");
  const locked = asBool(sourceSlide?.template_lock, false);
  const preferTemplateRenderer = hasTemplateContentRenderer(family);
  const forceBento = asBool(sourceSlide?.force_bento, sourceSlide?.render_mode === "bento", false);
  if (forceBento) return true;
  if (locked && preferTemplateRenderer) return false;
  if (preferTemplateRenderer && !locked) return false;
  return true;
}

function tryRenderBentoSlide(pres, sourceSlide, pageNumber, theme, style, templateFamily = "bento_2x2_dark") {
  if (!shouldAttemptBentoSlide(sourceSlide, templateFamily)) return null;
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };
  maybeAddSvgLayer(slide, sourceSlide, theme, sourceSlide?.layout_grid || "grid_4");
  const ok = renderBentoSlide({
    pptx: pptxgen,
    slide,
    sourceSlide,
    theme,
    style,
  });
  if (!ok) return null;
  addPageBadge(slide, pageNumber, theme, style);

  const title = htmlToText(String(pick(sourceSlide, ["title"], `Slide ${pageNumber}`))) || `Slide ${pageNumber}`;
  const bullets = collectBentoBlockTexts(sourceSlide);
  return buildBentoRenderSlide(pageNumber, sourceSlide, title, bullets, templateFamily);
}

function buildDeck() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.author = deckAuthor;
  pres.title = deckTitle;
  pres.subject = "MiniMax PPTX Generator";
  pres.company = "AutoViralVid";
  const originalAddSlide = pres.addSlide.bind(pres);
  pres.addSlide = (...args) => {
    const slide = originalAddSlide(...args);
    const originalAddText = slide.addText.bind(slide);
    slide.addText = (text, options = {}) => {
      const merged = { ...options };
      if (!Number.isFinite(Number(merged.margin)) || Number(merged.margin) < 0.05) merged.margin = 0.05;
      if (merged.fit === undefined && Number(merged.fontSize || 0) >= 10) {
        merged.fit = "shrink";
      }
      if (Number.isFinite(merged.x) && Number.isFinite(merged.w)) {
        if (merged.x < 0.34) {
          const dx = 0.34 - merged.x;
          merged.x = 0.34;
          merged.w = Math.max(0.2, Number(merged.w) - dx);
        }
        const maxRight = 9.66;
        if (merged.x + merged.w > maxRight) {
          merged.w = Math.max(0.2, maxRight - merged.x);
        }
      }
      if (Number.isFinite(merged.y) && Number.isFinite(merged.h)) {
        if (merged.y < 0.08) {
          const dy = 0.08 - merged.y;
          merged.y = 0.08;
          merged.h = Math.max(0.2, Number(merged.h) - dy);
        }
        const maxBottom = 5.5;
        if (merged.y + merged.h > maxBottom) {
          merged.h = Math.max(0.2, maxBottom - merged.y);
        }
      }
      return originalAddText(text, merged);
    };
    return slide;
  };

  const topicText = `${deckTitle} ${slides.map((s) => htmlToText(String(s?.title || ""))).join(" ")}`;
  const visualConfig = resolveVisualConfig(topicText);
  const style = visualConfig.enabled
    ? (
      visualConfig.enforcePreset && normalizeKey(requestedStyle) === "auto"
        ? visualConfig.styleOverride
        : selectStyle(requestedStyle, deckStyleHint, topicText, disableLocalStyleRewrite)
    )
    : selectStyle(requestedStyle, deckStyleHint, topicText, disableLocalStyleRewrite);
  const paletteKey = visualConfig.enabled
    ? (
      visualConfig.enforcePreset && normalizeKey(requestedPalette) === "auto"
        ? visualConfig.paletteOverride
        : selectPalette(requestedPalette, topicText, disableLocalStyleRewrite)
    )
    : selectPalette(requestedPalette, topicText, disableLocalStyleRewrite);
  const deckTemplateFamily = normalizeTemplateFamily(
    normalizeKey(requestedTemplateFamily) === "auto" ? "" : requestedTemplateFamily,
    "content",
    "dashboard_dark",
  );
  const theme = buildTheme(paletteKey, deckTemplateFamily);
  const renderSlides = [];
  const isPatchMode = retryScope !== "deck";
  const renderMode = isPatchMode
    ? "minimax_presentation_patch"
    : (generatorMode === "official"
      ? "minimax_presentation_official"
      : "minimax_presentation");

  if (slides.length === 0) {
    addCover(pres, deckTitle, "", theme, style, visualConfig, undefined, "hero_tech_cover");
    renderSlides.push(
      buildCoverRenderSlide(1, deckTitle, "", style, paletteKey, undefined, "hero_tech_cover"),
    );
    return { pres, style, paletteKey, renderSlides, renderMode, visualConfig };
  }

  if (isPatchMode) {
    for (let i = 0; i < slides.length; i += 1) {
      const sourceSlide = slides[i];
      if (!isSlideInRetryScope(sourceSlide, i)) continue;
      const pageNumber = i + 1;
      const templateFamily = resolveSlideTemplateFamily(sourceSlide);
      const slideTheme = buildTheme(paletteKey, templateFamily);
      const bentoRenderSlide = tryRenderBentoSlide(
        pres,
        sourceSlide,
        pageNumber,
        slideTheme,
        style,
        templateFamily,
      );
      if (bentoRenderSlide) {
        renderSlides.push(bentoRenderSlide);
        continue;
      }
      const explicitType = normalizeKey(
        pick(sourceSlide, ["page_type", "pageType", "slide_type", "slideType", "subtype"], ""),
      );
      const title = htmlToText(String(pick(sourceSlide, ["title"], `Slide ${pageNumber}`))) || `Slide ${pageNumber}`;
      const narration = htmlToText(String(pick(sourceSlide, ["narration", "speaker_notes", "speakerNotes"], "")));
      const bullets = collectBullets(sourceSlide, narration);

      if (explicitType === "cover") {
        const coverLines = Array.from(
          new Set([narration, ...bullets].map((line) => String(line || "").trim()).filter(Boolean)),
        );
        const subtitle = coverLines.slice(0, 3).join("\n");
        const coverTemplate = normalizeTemplateFamily(resolveSlideTemplateFamily(sourceSlide), "cover", "hero_1");
        const coverTheme = buildTheme(paletteKey, coverTemplate);
        addCover(pres, title, subtitle, coverTheme, style, visualConfig, sourceSlide, coverTemplate);
        renderSlides.push(
          buildCoverRenderSlide(pageNumber, title, subtitle, style, paletteKey, sourceSlide, coverTemplate),
        );
        continue;
      }

      if (explicitType === "toc") {
        const tocSections = bullets.length
          ? bullets
          : slides.map((s, idx) => htmlToText(String(pick(s, ["title"], `Section ${idx + 1}`)))).filter(Boolean).slice(0, 6);
        addToc(pres, tocSections, theme, style, visualConfig, pageNumber, sourceSlide);
        renderSlides.push(buildTocRenderSlide(pageNumber, tocSections, sourceSlide));
        continue;
      }

      if (explicitType === "summary") {
        const summaryBullets = (bullets.length ? bullets : [narration || title]).slice(0, 5);
        addSummarySlide(pres, title, summaryBullets, pageNumber, theme, style, visualConfig, sourceSlide);
        renderSlides.push(buildSummaryRenderSlide(pageNumber, title, summaryBullets, sourceSlide, "hero_dark"));
        continue;
      }

      if (effectiveVerbatimContent) {
        const lines = collectTextLines(sourceSlide, narration || title);
        addVerbatimContentSlide(pres, sourceSlide, pageNumber, slideTheme, style, visualConfig, templateFamily);
        renderSlides.push(
          buildContentRenderSlide(
            pageNumber,
            sourceSlide,
            "content",
            title,
            lines.length ? lines : bullets,
            templateFamily,
          ),
        );
        continue;
      }

      const subtype = inferSubtype(sourceSlide);
      addContentSlide(pres, sourceSlide, pageNumber, slideTheme, style, visualConfig, subtype, templateFamily);
      renderSlides.push(buildContentRenderSlide(pageNumber, sourceSlide, subtype, title, bullets, templateFamily));
    }
    if (renderSlides.length === 0) {
      addCover(pres, deckTitle, "", theme, style, visualConfig, undefined, "hero_tech_cover");
      renderSlides.push(buildCoverRenderSlide(1, deckTitle, "", style, paletteKey, undefined, "hero_tech_cover"));
    }
    return { pres, style, paletteKey, renderSlides, renderMode, visualConfig };
  }

  const explicitTypeSet = new Set(
    slides
      .map((sourceSlide) =>
        normalizeKey(
          pick(sourceSlide, ["page_type", "pageType", "slide_type", "slideType", "subtype"], ""),
        ),
      )
      .filter(Boolean),
  );
  const hasExplicitStructure = explicitTypeSet.size > 0;
  if (hasExplicitStructure) {
    const explicitContentCandidates = [];
    for (let i = 0; i < slides.length; i += 1) {
      const sourceSlide = slides[i];
      const explicitType = normalizeKey(
        pick(sourceSlide, ["page_type", "pageType", "slide_type", "slideType", "subtype"], ""),
      );
      if (!explicitType || explicitType === "content") {
        explicitContentCandidates.push({ index: i, slide: sourceSlide });
      }
    }
    const explicitPlannedSubtypes = planDeckSubtypes(explicitContentCandidates.map((item) => item.slide));
    const explicitSubtypeByIndex = new Map();
    explicitContentCandidates.forEach((item, idx) => {
      explicitSubtypeByIndex.set(item.index, explicitPlannedSubtypes[idx] || "content");
    });

    for (let i = 0; i < slides.length; i += 1) {
      const sourceSlide = slides[i];
      const pageNumber = i + 1;
      const templateFamily = resolveSlideTemplateFamily(sourceSlide);
      const slideTheme = buildTheme(paletteKey, templateFamily);
      const bentoRenderSlide = tryRenderBentoSlide(
        pres,
        sourceSlide,
        pageNumber,
        slideTheme,
        style,
        templateFamily,
      );
      if (bentoRenderSlide) {
        renderSlides.push(bentoRenderSlide);
        continue;
      }
      const explicitType = normalizeKey(
        pick(sourceSlide, ["page_type", "pageType", "slide_type", "slideType", "subtype"], ""),
      );
      const title = htmlToText(String(pick(sourceSlide, ["title"], `Slide ${pageNumber}`))) || `Slide ${pageNumber}`;
      const narration = htmlToText(String(pick(sourceSlide, ["narration", "speaker_notes", "speakerNotes"], "")));
      const bullets = collectBullets(sourceSlide, narration);

      if (explicitType === "cover") {
        const coverLines = Array.from(
          new Set([narration, ...bullets].map((line) => String(line || "").trim()).filter(Boolean)),
        );
        const subtitle = coverLines.slice(0, 3).join("\n");
        const coverTemplate = normalizeTemplateFamily(resolveSlideTemplateFamily(sourceSlide), "cover", "hero_1");
        const coverTheme = buildTheme(paletteKey, coverTemplate);
        addCover(pres, title, subtitle, coverTheme, style, visualConfig, sourceSlide, coverTemplate);
        renderSlides.push(
          buildCoverRenderSlide(pageNumber, title, subtitle, style, paletteKey, sourceSlide, coverTemplate),
        );
        continue;
      }
      if (explicitType === "toc") {
        const tocSections = bullets.length
          ? bullets
          : slides
            .map((s, idx) => htmlToText(String(pick(s, ["title"], `Section ${idx + 1}`))))
            .filter(Boolean)
            .slice(0, 6);
        addToc(pres, tocSections, theme, style, visualConfig, pageNumber, sourceSlide);
        renderSlides.push(buildTocRenderSlide(pageNumber, tocSections, sourceSlide));
        continue;
      }
      if (explicitType === "summary") {
        const summaryBullets = (bullets.length ? bullets : [narration || title]).slice(0, 5);
        addSummarySlide(pres, title, summaryBullets, pageNumber, theme, style, visualConfig, sourceSlide);
        renderSlides.push(buildSummaryRenderSlide(pageNumber, title, summaryBullets, sourceSlide, "hero_dark"));
        continue;
      }

      if (effectiveVerbatimContent) {
        const lines = collectTextLines(sourceSlide, narration || title);
        addVerbatimContentSlide(pres, sourceSlide, pageNumber, slideTheme, style, visualConfig, templateFamily);
        renderSlides.push(
          buildContentRenderSlide(
            pageNumber,
            sourceSlide,
            "content",
            title,
            lines.length ? lines : bullets,
            templateFamily,
          ),
        );
        continue;
      }

      const subtype =
        explicitType && explicitType !== "content"
          ? explicitType
          : (explicitSubtypeByIndex.get(i) || inferSubtype(sourceSlide) || "content");
      addContentSlide(pres, sourceSlide, pageNumber, slideTheme, style, visualConfig, subtype, templateFamily);
      renderSlides.push(buildContentRenderSlide(pageNumber, sourceSlide, subtype, title, bullets, templateFamily));
    }
    return { pres, style, paletteKey, renderSlides, renderMode, visualConfig };
  }

  const firstTitle = htmlToText(String(pick(slides[0], ["title"], deckTitle)));
  const coverSubtitle = firstTitle && firstTitle !== deckTitle ? firstTitle : "";
  const firstCoverTemplate = normalizeTemplateFamily(resolveSlideTemplateFamily(slides[0]), "cover", "hero_1");
  const firstCoverTheme = buildTheme(paletteKey, firstCoverTemplate);
  addCover(pres, deckTitle, coverSubtitle, firstCoverTheme, style, visualConfig, slides[0], firstCoverTemplate);
  renderSlides.push(
    buildCoverRenderSlide(1, deckTitle, coverSubtitle, style, paletteKey, slides[0], firstCoverTemplate),
  );

  const contentCandidates = slides.slice(1, Math.max(2, slides.length - 1));
  const tocTitles = contentCandidates
    .map((s, idx) => htmlToText(String(pick(s, ["title"], `Section ${idx + 1}`))))
    .filter(Boolean);
  const tocSections = tocTitles.length ? tocTitles : ["Overview", "Core Content", "Summary"];
  addToc(pres, tocSections, theme, style, visualConfig, 2, slides[1] || slides[0]);
  renderSlides.push(buildTocRenderSlide(2, tocSections, slides[1] || slides[0]));

  const middleSlides = slides.slice(1, Math.max(1, slides.length - 1));
  const plannedSubtypes = planDeckSubtypes(middleSlides);

  for (let i = 1; i < slides.length - 1; i += 1) {
    const sourceSlide = slides[i];
    const templateFamily = resolveSlideTemplateFamily(sourceSlide);
    const slideTheme = buildTheme(paletteKey, templateFamily);
    const bentoRenderSlide = tryRenderBentoSlide(
      pres,
      sourceSlide,
      i + 2,
      slideTheme,
      style,
      templateFamily,
    );
    if (bentoRenderSlide) {
      renderSlides.push(bentoRenderSlide);
      continue;
    }

    const title = htmlToText(String(pick(sourceSlide, ["title"], `Slide ${i + 1}`))) || `Slide ${i + 1}`;
    const narration = htmlToText(String(pick(sourceSlide, ["narration", "speaker_notes", "speakerNotes"], "")));
    const bullets = collectBullets(sourceSlide, narration);
    const subtype = plannedSubtypes[i - 1] || inferSubtype(sourceSlide);
    addContentSlide(pres, sourceSlide, i + 2, slideTheme, style, visualConfig, subtype, templateFamily);
    renderSlides.push(buildContentRenderSlide(i + 2, sourceSlide, subtype, title, bullets, templateFamily));
  }

  const lastSlide = slides[slides.length - 1];
  const summaryTitle = htmlToText(String(pick(lastSlide, ["title"], "Summary"))) || "Summary";
  const allBullets = slides.flatMap((s) => collectBullets(s, ""));
  const summaryBullets = Array.from(new Set(allBullets)).slice(0, 5);
  addSummarySlide(
    pres,
    summaryTitle,
    summaryBullets.length ? summaryBullets : [summaryTitle],
    Math.max(3, slides.length + 1),
    theme,
    style,
    visualConfig,
    lastSlide,
  );
  renderSlides.push(
    buildSummaryRenderSlide(
      Math.max(3, slides.length + 1),
      summaryTitle,
      summaryBullets,
      lastSlide,
      "hero_dark",
    ),
  );

  return { pres, style, paletteKey, renderSlides, renderMode, visualConfig };
}

async function main() {
  const { pres, style, paletteKey, renderSlides, renderMode, visualConfig } = buildDeck();
  const effectiveDeckTemplate = normalizeTemplateFamily(
    normalizeKey(requestedTemplateFamily) === "auto" ? "" : requestedTemplateFamily,
    "content",
    "dashboard_dark",
  );
  const deckTemplateProfiles = getTemplateProfiles(effectiveDeckTemplate);
  const officialOutput = fromOfficialOutput({
    deck_id: deckId || undefined,
    generator_mode: generatorMode,
    retry_scope: retryScope,
    slides: renderSlides,
  });
  const buffer = await pres.write({ outputType: "nodebuffer" });
  writeFileSync(values.output, buffer);
  if (renderOutputPath) {
    writeFileSync(
      renderOutputPath,
      JSON.stringify(
        {
          mode: renderMode,
          skill: "minimax_pptx_generator",
          generator_mode: generatorMode,
          style_variant: style,
          palette_key: paletteKey,
          svg_mode: svgModeEnabled ? "on" : "off",
          template_family: effectiveDeckTemplate,
          ...deckTemplateProfiles,
          visual_priority: visualPriority,
          visual_preset: visualConfig?.preset || undefined,
          visual_density: visualConfig?.density || undefined,
          constraint_hardness: visualConfig?.constraintHardness || undefined,
          verbatim_content: effectiveVerbatimContent,
          deck_id: deckId || undefined,
          retry_scope: retryScope,
          target_slide_ids: Array.from(targetSlideIdSet),
          target_block_ids: Array.from(targetBlockIdSet),
          retry_hint: retryHint || undefined,
          idempotency_key: idempotencyKey || undefined,
          original_style: originalStyle,
          disable_local_style_rewrite: disableLocalStyleRewrite,
          official_input: officialPlan.officialInput,
          official_output: officialOutput,
          slides: renderSlides,
        },
        null,
        2,
      ),
      "utf-8",
    );
  }
  console.log(
    JSON.stringify({
      success: true,
      output: values.output,
      engine: "minimax_pptx_generator",
      generator_mode: generatorMode,
      style_variant: style,
      palette_key: paletteKey,
      svg_mode: svgModeEnabled ? "on" : "off",
      template_family: effectiveDeckTemplate,
      ...deckTemplateProfiles,
      visual_priority: visualPriority,
      visual_preset: visualConfig?.preset || undefined,
      visual_density: visualConfig?.density || undefined,
      constraint_hardness: visualConfig?.constraintHardness || undefined,
      verbatim_content: effectiveVerbatimContent,
      mode: renderMode,
      deck_id: deckId || undefined,
      retry_scope: retryScope,
      target_slide_ids: Array.from(targetSlideIdSet),
      target_block_ids: Array.from(targetBlockIdSet),
      original_style: originalStyle,
      disable_local_style_rewrite: disableLocalStyleRewrite,
      render_output: renderOutputPath || undefined,
      render_slides: Array.isArray(renderSlides) ? renderSlides.length : 0,
      official_slides: Array.isArray(officialOutput?.slides) ? officialOutput.slides.length : 0,
    }),
  );
}

main().catch((err) => {
  console.error(JSON.stringify({ success: false, error: String(err?.message || err) }));
  process.exit(1);
});


