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
import { resolveDisableLocalStyleRewritePolicy } from "./minimax/design-decision-policy.mjs";
import { canRenderBentoSlide, renderBentoSlide } from "./minimax/card-renderers.mjs";
import { normalizeRenderInput, validateRenderInput } from "./minimax/render-contract.mjs";
import { fromOfficialOutput } from "./minimax/official_skill_adapter.mjs";
import { resolveOfficialPlan } from "./minimax/official_orchestrator.mjs";
import { buildDarkTheme, normalizeTemplateFamily } from "./minimax/design-tokens.mjs";
import { addSvgOverlay, buildSlideSvg, buildTerminalPageSvg } from "./minimax/svg-slide.mjs";
import { renderSvgSlideToPptx, resolveSlideSvgMarkup } from "./minimax/svg-slide-renderer.mjs";
import { getTemplateProfiles } from "./minimax/templates/template-profiles.mjs";
import {
  assessTemplateCapabilityForSlide,
  resolveSubtypeByTemplate as resolveSubtypeByTemplateRegistry,
  resolveTemplateFamilyForSlide,
} from "./minimax/templates/template-registry.mjs";
import {
  hasTemplateContentRenderer,
  renderTemplateContent,
} from "./minimax/templates/template-renderers.mjs";
import {
  canonicalizePaletteKey as canonicalizePaletteFromCatalog,
  canonicalizeThemeRecipe as canonicalizeThemeRecipeFromCatalog,
  getThemeRecipe as getThemeRecipeFromCatalog,
  getTemplateCatalog,
  getTemplateField,
  getTemplatePreferredLayout,
} from "./minimax/templates/template-catalog.mjs";

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
    "theme-recipe": { type: "string" },
    tone: { type: "string" },
  },
});

if (!values.input || !values.output) {
  console.error("Usage: node generate-pptx-minimax.mjs --input <json_file> --output <pptx_file> [--style <variant>] [--palette <key>] [--render-output <json_file>] [--generator-mode official|legacy] [--visual-priority] [--visual-preset <name>] [--theme-recipe <name>] [--tone auto|light|dark] [--constraint-hardness minimal|balanced|strict]");
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
const rawRequestedStyle = String(values.style || payload.minimax_style_variant || "auto");
const rawRequestedPalette = String(values.palette || payload.minimax_palette_key || "auto");
const renderOutputPath = values["render-output"] ? String(values["render-output"]) : "";
const deckStyleHint = String(payload.deck_style || payload.style || "").toLowerCase();
const deckId = String(values["deck-id"] || payload.deck_id || "").trim();
const idempotencyKey = String(values["idempotency-key"] || payload.idempotency_key || "").trim();
const retryScope = normalizeKey(values["retry-scope"] || payload.retry_scope || "deck") || "deck";
const retryHint = String(values["retry-hint"] || payload.retry_hint || "").trim();
const designSpec = payload?.design_spec && typeof payload.design_spec === "object" ? payload.design_spec : {};
const designDecision = payload?.design_decision_v1 && typeof payload.design_decision_v1 === "object"
  ? payload.design_decision_v1
  : {};
const deckDecision = designDecision?.deck && typeof designDecision.deck === "object"
  ? designDecision.deck
  : {};
const deckArchetypeProfile = String(payload.deck_archetype_profile || payload.deckArchetypeProfile || "").trim().toLowerCase();
const slideDecisionsRaw = Array.isArray(designDecision?.slides) ? designDecision.slides : [];

function normalizeAutoText(value) {
  const text = String(value || "").trim();
  const normalized = normalizeKey(text);
  if (!text) return "";
  if (normalized === "auto" || normalized === "none" || normalized === "null" || normalized === "undefined") return "";
  return text;
}

function deckDecisionValue(key) {
  return normalizeAutoText(deckDecision?.[key]);
}

const requestedStyle = deckDecisionValue("style_variant") || normalizeAutoText(rawRequestedStyle) || "auto";
const requestedPalette = deckDecisionValue("palette_key") || normalizeAutoText(rawRequestedPalette) || "auto";
const effectiveRequestedPalette = (
  deckArchetypeProfile === "education_textbook"
  && ["", "auto", "education_charts"].includes(normalizeKey(requestedPalette || ""))
)
  ? "education_office_classic"
  : requestedPalette;

function parseCsv(rawValue) {
  return String(rawValue || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

const targetSlideIds = parseCsv(values["target-slide-ids"] || payload.target_slide_ids || "");
const targetBlockIds = parseCsv(values["target-block-ids"] || payload.target_block_ids || "");
const originalStyle = asBool(values["original-style"], payload.original_style, false);
const requestedDisableLocalStyleRewrite = asBool(
  values["disable-local-style-rewrite"],
  payload.disable_local_style_rewrite,
  false,
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

function preferZhText(...parts) {
  const joined = parts
    .flatMap((item) => Array.isArray(item) ? item : [item])
    .map((item) => String(item || ""))
    .join(" ");
  return /[\u4e00-\u9fff]/.test(joined);
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
const disableLocalStyleRewrite = resolveDisableLocalStyleRewritePolicy({
  requestedDisableLocalStyleRewrite: officialPlan.disableLocalStyleRewrite,
  deckDecision,
});
const effectiveVerbatimContent = verbatimContent;
const requestedVisualPreset = String(values["visual-preset"] || payload.visual_preset || "auto");
const requestedVisualDensity = String(values["visual-density"] || payload.visual_density || "balanced");
const requestedThemeRecipe = String(
  deckDecisionValue("theme_recipe")
  || values["theme-recipe"]
  || payload.theme_recipe
  || payload?.theme?.theme_recipe
  || payload?.design_spec?.visual?.theme_recipe
  || "auto",
);
const requestedTone = String(
  deckDecisionValue("tone")
  || values.tone
  || payload.tone
  || payload.theme_tone
  || payload?.theme?.tone
  || payload?.design_spec?.visual?.tone
  || "auto",
);
const requestedConstraintHardness = String(
  values["constraint-hardness"] || payload.constraint_hardness || "minimal",
);

const requestedSvgMode = String(values["svg-mode"] || payload.svg_mode || "auto");
const rawRequestedTemplateFamily = String(values["template-family"] || parsedInput.template_family || "auto");
const requestedTemplateFamily = normalizeAutoText(rawRequestedTemplateFamily)
  || deckDecisionValue("template_family")
  || "auto";
const visualPriority = asBool(
  values["visual-priority"],
  payload.visual_priority,
  true,
);
const normalizedSvgModeRaw = normalizeKey(requestedSvgMode || "auto");
const normalizedSvgMode = (
  normalizedSvgModeRaw === "force"
    ? "force"
    : normalizedSvgModeRaw === "on"
      ? "on"
      : normalizedSvgModeRaw === "off"
        ? "off"
        : "auto"
);
const svgModeEnabled = normalizedSvgMode !== "off";

function normalizeConstraintHardness(input) {
  const normalized = normalizeKey(input || "");
  if (normalized === "strict") return "strict";
  if (normalized === "balanced") return "balanced";
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

function shouldIgnoreEncodingPath(path) {
  const p = String(path || "");
  if (!p) return false;
  return (
    p.includes(".image_keywords[") ||
    p.endsWith(".content_strategy.data_anchor") ||
    p.includes(".content_strategy.evidence[")
  );
}

function detectEncodingIssues(node, path = "$", issues = []) {
  if (typeof node === "string") {
    if (shouldIgnoreEncodingPath(path)) {
      return issues;
    }
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

const TEMPLATE_CATALOG = getTemplateCatalog();
const PALETTES = (() => {
  const raw = TEMPLATE_CATALOG?.palettes && typeof TEMPLATE_CATALOG.palettes === "object"
    ? TEMPLATE_CATALOG.palettes
    : {};
  const out = {};
  for (const [key, value] of Object.entries(raw)) {
    const normalizedKey = normalizeKey(key);
    const colors = Array.isArray(value)
      ? value.map((item) => String(item || "").replace("#", "").trim()).filter(Boolean).slice(0, 5)
      : [];
    if (normalizedKey && colors.length >= 5) out[normalizedKey] = colors;
  }
  return out;
})();

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

let FONT_BY_STYLE = {
  sharp: { enTitle: "Bahnschrift SemiBold", enBody: "Segoe UI" },
  soft: { enTitle: "Aptos Display", enBody: "Aptos" },
  rounded: { enTitle: "Trebuchet MS", enBody: "Segoe UI" },
  pill: { enTitle: "Gill Sans MT", enBody: "Segoe UI" },
};
let FONT_ZH = "Microsoft YaHei";
const ARCHETYPE_FONT_OVERRIDES = {
  education_textbook: {
    zh: "Calibri",
    styles: {
      sharp: { enTitle: "Arial", enBody: "Calibri" },
      soft: { enTitle: "Arial", enBody: "Calibri" },
      rounded: { enTitle: "Arial", enBody: "Calibri" },
      pill: { enTitle: "Arial", enBody: "Calibri" },
    },
  },
};
if (deckArchetypeProfile && ARCHETYPE_FONT_OVERRIDES[deckArchetypeProfile]) {
  const override = ARCHETYPE_FONT_OVERRIDES[deckArchetypeProfile];
  FONT_BY_STYLE = { ...FONT_BY_STYLE, ...override.styles };
  FONT_ZH = override.zh || FONT_ZH;
}
const SLIDE_WIDTH = 10;
const SLIDE_HEIGHT = 5.625;
const DECOR_INSET = 0.12;

const VISUAL_PRESETS = {
  education_office_classic: {
    themeRecipe: "classroom_soft",
    palette: "education_office_classic",
    maxBullets: 5,
    backdrop: "minimal-grid",
    tone: "light",
  },
  tech_cinematic: {
    themeRecipe: "tech_cinematic",
    palette: "pure_tech_blue",
    maxBullets: 4,
    backdrop: "high-contrast",
    tone: "dark",
  },
  executive_brief: {
    themeRecipe: "consulting_clean",
    palette: "business_authority",
    maxBullets: 4,
    backdrop: "minimal-grid",
    tone: "light",
  },
  premium_light: {
    themeRecipe: "classroom_soft",
    palette: "platinum_white_gold",
    maxBullets: 5,
    backdrop: "soft-gradient",
    tone: "light",
  },
  energetic: {
    themeRecipe: "energetic_campaign",
    palette: "vibrant_orange_mint",
    maxBullets: 4,
    backdrop: "color-block",
    tone: "light",
  },
};

const BACKDROP_VARIANTS = [
  "high-contrast",
  "color-block",
  "soft-gradient",
  "minimal-grid",
  "corner-accent",
  "side-panel",
  "bottom-wave",
  "dot-grid",
  "diagonal-split",
];
let backdropRenderCounter = 0;

function normalizeVisualPreset(input, topicText = "", archetype = "") {
  const normalized = normalizeKey(input || "");
  if (normalized && normalized !== "auto" && VISUAL_PRESETS[normalized]) return normalized;
  if (String(archetype || "").toLowerCase() === "education_textbook") {
    return "education_office_classic";
  }
  const topic = String(topicText || "").toLowerCase();
  if (/(education|teaching|training|classroom|lesson|school|学生|课堂|教学|教育|培训)/.test(topic)) {
    return "education_office_classic";
  }
  if (/(ai|cloud|tech|科技|数字|智能|digital)/.test(topic)) return "tech_cinematic";
  if (/(premium|高端|luxury|investor|融资)/.test(topic)) return "premium_light";
  if (/(brand|campaign|marketing|增长|转化)/.test(topic)) return "energetic";
  return "executive_brief";
}

const slideDecisionById = new Map();
for (const row of slideDecisionsRaw) {
  if (!row || typeof row !== "object") continue;
  const sid = String(row.slide_id || row.id || "").trim();
  if (!sid || slideDecisionById.has(sid)) continue;
  slideDecisionById.set(sid, row);
}

function resolveSlideDecision(sourceSlide = {}, index = -1) {
  const keys = [
    String(sourceSlide?.slide_id || "").trim(),
    String(sourceSlide?.id || "").trim(),
    String(sourceSlide?.page_number || "").trim(),
    Number.isFinite(Number(index)) && Number(index) >= 0 ? String(Number(index) + 1) : "",
  ].filter(Boolean);
  for (const key of keys) {
    const row = slideDecisionById.get(key);
    if (row && typeof row === "object") return row;
  }
  return {};
}

function resolveSlideTemplateFamily(sourceSlide) {
  const slideDecision = resolveSlideDecision(sourceSlide);
  const deckArchetype = String(sourceSlide?.deck_archetype_profile || deckArchetypeProfile || "").trim().toLowerCase();
  const explicitType = normalizeKey(
    pick(sourceSlide || {}, ["page_type", "pageType", "slide_type", "slideType", "subtype"], ""),
  ) || "content";
  if (deckArchetype === "education_textbook") {
    if (["cover", "toc", "summary", "divider", "section", "hero_1"].includes(explicitType)) {
      return "hero_dark";
    }
    return "education_textbook_light";
  }
  const layoutGrid = normalizeKey(String(sourceSlide?.layout_grid || sourceSlide?.layout || "")) || "split_2";
  const perSlideTemplate = String(
    pick(sourceSlide || {}, ["template_family", "template_id"], ""),
  ).trim();
  const decisionTemplate = String(
    pick(slideDecision, ["template_family", "template_id"], ""),
  ).trim();
  const requestedTemplate = perSlideTemplate && normalizeKey(perSlideTemplate) !== "auto"
    ? perSlideTemplate
    : (decisionTemplate && normalizeKey(decisionTemplate) !== "auto")
      ? decisionTemplate
    : requestedTemplateFamily;
  const toneFromSlide = normalizeKey(
    pick(sourceSlide || {}, ["theme_tone", "tone", "preferred_tone"], ""),
  );
  const toneFromDeck = normalizeKey(
    normalizeAutoText(requestedTone)
    || deckDecisionValue("tone")
    || pick(payload || {}, ["tone", "theme_tone"], ""),
  );
  const preferredTone = (toneFromSlide === "light" || toneFromSlide === "dark")
    ? toneFromSlide
    : (toneFromDeck === "light" || toneFromDeck === "dark")
      ? toneFromDeck
      : "";
  return resolveTemplateFamilyForSlide({
    sourceSlide,
    requestedTemplateFamily: requestedTemplate,
    explicitType,
    layoutGrid,
    desiredDensity: requestedVisualDensity,
    preferredTone,
    normalizeTemplateFamily,
  });
}

const TERMINAL_SLIDE_TYPES = new Set(["cover", "toc", "divider", "summary", "hero_1", "section"]);

function resolveExplicitSlideType(sourceSlide = {}) {
  return normalizeKey(
    pick(sourceSlide || {}, ["page_type", "pageType", "slide_type", "slideType", "subtype"], ""),
  ) || "content";
}

function deckPrefersLightTheme(topicText = "") {
  const blob = String(topicText || "").toLowerCase();
  if (!blob.trim()) return false;
  return /(education|teaching|training|classroom|lesson|school|student|curriculum|课堂|教学|教育|课程|培训|高中|学生)/.test(blob);
}

function inferDeckTemplateFamily(sourceSlides = []) {
  const explicitDeckTemplate = normalizeAutoText(requestedTemplateFamily);
  const sourceRows = Array.isArray(sourceSlides) ? sourceSlides : [];
  const contentSlides = sourceRows.filter((slide) => !TERMINAL_SLIDE_TYPES.has(resolveExplicitSlideType(slide)));
  const firstContentSlide = (
    contentSlides[0]
    || sourceRows[0]
    || null
  );
  const deckTopicBlob = [
    deckTitle,
    String(payload?.topic || ""),
    String(payload?.audience || ""),
    String(payload?.purpose || ""),
    ...sourceRows.slice(0, 16).map((slide) => String(slide?.title || "")),
  ].join(" ");
  const explicitTone = normalizeToneValue(
    normalizeAutoText(requestedTone)
    || deckDecisionValue("tone")
    || pick(payload || {}, ["tone", "theme_tone"], ""),
  );
  const preferLightDeck = explicitTone === "light"
    ? true
    : explicitTone === "dark"
      ? false
      : deckPrefersLightTheme(deckTopicBlob);
  const deckTonePreference = explicitTone === "light" || explicitTone === "dark"
    ? explicitTone
    : (preferLightDeck ? "light" : "");
  const lightFallbackFamily = "consulting_warm_light";
  const darkFallbackFamily = "dashboard_dark";
  const normalizeDeckFamily = (familyName) =>
    normalizeTemplateFamily(familyName, "content", layoutHint);
  const normalizeDeckFamilyIfNeeded = (familyName) => {
    const normalized = normalizeDeckFamily(familyName);
    if (!normalized) return deckTonePreference === "dark" ? darkFallbackFamily : lightFallbackFamily;
    if (deckTonePreference === "light" && normalized.endsWith("_dark")) return lightFallbackFamily;
    if (deckTonePreference === "dark" && normalized.endsWith("_light")) return darkFallbackFamily;
    return normalized;
  };

  const layoutHint = normalizeKey(
    String(firstContentSlide?.layout_grid || firstContentSlide?.layout || ""),
  ) || "split_2";
  if (explicitDeckTemplate) {
    return normalizeDeckFamilyIfNeeded(explicitDeckTemplate);
  }

  const familyCounts = new Map();
  const familyOrder = new Map();
  const sampleSlides = (contentSlides.length > 0 ? contentSlides : sourceRows).slice(0, 16);
  sampleSlides.forEach((slide, idx) => {
    const family = normalizeKey(resolveSlideTemplateFamily(slide));
    if (!family || family === "auto") return;
    familyCounts.set(family, (familyCounts.get(family) || 0) + 1);
    if (!familyOrder.has(family)) familyOrder.set(family, idx);
  });

  if (familyCounts.size > 0) {
    const sorted = Array.from(familyCounts.entries()).sort((a, b) => {
      if (b[1] !== a[1]) return b[1] - a[1];
      return (familyOrder.get(a[0]) || 0) - (familyOrder.get(b[0]) || 0);
    });
    if (preferLightDeck) {
      const lightCandidate = sorted.find(([family]) => String(family || "").endsWith("_light"));
      if (lightCandidate?.[0]) return normalizeDeckFamilyIfNeeded(lightCandidate[0]);
    }
    return normalizeDeckFamilyIfNeeded(
      sorted[0]?.[0] || (deckTonePreference === "dark" ? darkFallbackFamily : lightFallbackFamily),
    );
  }

  return normalizeDeckFamilyIfNeeded(resolveTemplateFamilyForSlide({
    sourceSlide: firstContentSlide || {},
    requestedTemplateFamily: "auto",
    explicitType: "content",
    layoutGrid: layoutHint,
    desiredDensity: requestedVisualDensity,
    preferredTone: deckTonePreference,
    normalizeTemplateFamily,
  }));
}

function setSlideThemeContext(slide, slideTheme = {}) {
  if (slide && typeof slide === "object" && slideTheme && typeof slideTheme === "object") {
    slide.__theme = { ...slideTheme };
  }
  return slide;
}

function resolveRenderPath(sourceSlide) {
  const slideDecision = resolveSlideDecision(sourceSlide);
  const decisionPath = normalizeKey(String(slideDecision?.render_path || ""));
  if (decisionPath === "svg") return "svg";
  if (decisionPath === "png_fallback") return "png_fallback";
  const normalized = normalizeKey(String(sourceSlide?.render_path || ""));
  if (normalized === "svg") return "svg";
  if (normalized === "png_fallback") return "png_fallback";
  return "pptxgenjs";
}

function maybeAddSvgLayer(slide, sourceSlide, theme, fallbackLayout = "split_2") {
  if (!slide) return false;
  if (
    deckArchetypeProfile === "education_textbook"
    && !["cover", "toc", "summary", "divider", "section", "hero_1"].includes(
      String(sourceSlide?.slide_type || "content").trim().toLowerCase(),
    )
  ) {
    return false;
  }
  const renderPath = resolveRenderPath(sourceSlide || {});
  const svgMarkup = resolveSlideSvgMarkup(sourceSlide || {});
  if (svgModeEnabled && renderPath === "svg" && svgMarkup) {
    const nativeResult = renderSvgSlideToPptx({
      slide,
      pptx: pptxgen,
      sourceSlide,
      theme,
      designSpec,
    });
    if (nativeResult?.applied) {
      if (sourceSlide && typeof sourceSlide === "object") {
        sourceSlide.__svg_render_mode = nativeResult.mode || "custgeom";
      }
      return true;
    }
  }
  if (!svgModeEnabled && renderPath !== "png_fallback") return false;
  const explicitSvgFlag = asBool(
    sourceSlide?.svg_overlay,
    sourceSlide?.force_svg_overlay,
    sourceSlide?.use_svg_overlay,
    false,
  );
  const blocks = Array.isArray(sourceSlide?.blocks) ? sourceSlide.blocks : [];
  const hasSvgBlock = blocks.some((block) => blockType(block) === "svg");
  const shouldInject =
    normalizedSvgMode === "force" || explicitSvgFlag || hasSvgBlock || renderPath === "svg" || renderPath === "png_fallback";
  if (!shouldInject) return false;
  const svgSource = {
    ...(sourceSlide || {}),
    title: pick(sourceSlide || {}, ["title"], deckTitle),
    narration: pick(sourceSlide || {}, ["narration", "speaker_notes", "speakerNotes"], ""),
    layout_grid: pick(sourceSlide || {}, ["layout_grid", "layout"], fallbackLayout),
  };
  const svg = svgMarkup || buildSlideSvg(svgSource, theme);
  const ok = addSvgOverlay(slide, svg, { x: 0, y: 0, w: 10, h: 5.625 }, {
    preferPng: renderPath === "png_fallback",
  });
  if (ok && sourceSlide && typeof sourceSlide === "object") {
    sourceSlide.__svg_render_mode = renderPath === "png_fallback" ? "overlay_png_fallback" : "overlay_svg";
  }
  return ok;
}

function resolveVisualConfig(topicText = "") {
  const presetKey = normalizeVisualPreset(requestedVisualPreset, topicText, deckArchetypeProfile);
  const preset = VISUAL_PRESETS[presetKey] || VISUAL_PRESETS.executive_brief;
  const recipeFromPreset = canonicalizeThemeRecipeFromCatalog(preset.themeRecipe || "auto");
  const requestedRecipe = normalizeAutoText(requestedThemeRecipe) || deckDecisionValue("theme_recipe") || "auto";
  const normalizedRecipe = canonicalizeThemeRecipeFromCatalog(requestedRecipe);
  const resolvedThemeRecipe = normalizedRecipe === "auto" ? recipeFromPreset : normalizedRecipe;
  const recipeConfig = getThemeRecipeFromCatalog(resolvedThemeRecipe);
  const requestedToneValue = normalizeKey(
    normalizeAutoText(requestedTone)
      || deckDecisionValue("tone")
      || "",
  );
  const resolvedTone = requestedToneValue === "light" || requestedToneValue === "dark"
    ? requestedToneValue
    : (
      String(recipeConfig?.tone || preset.tone || "auto").toLowerCase() === "light"
        ? "light"
        : String(recipeConfig?.tone || preset.tone || "auto").toLowerCase() === "dark"
          ? "dark"
          : "auto"
    );
  const density = normalizeKey(requestedVisualDensity || "balanced");
  const densityMaxBullets = density === "sparse" ? 4 : density === "dense" ? 7 : preset.maxBullets;
  let maxBullets = densityMaxBullets;
  if (constraintHardness === "minimal") maxBullets = Math.max(6, maxBullets);
  else if (constraintHardness === "strict") maxBullets = Math.min(4, maxBullets);
  else maxBullets = Math.min(5, maxBullets);
  return {
    enabled: Boolean(visualPriority),
    preset: presetKey,
    styleOverride: recipeConfig?.style_variant || "soft",
    paletteOverride: preset.palette,
    themeRecipe: resolvedThemeRecipe,
    tone: resolvedTone,
    surfaceProfile: String(recipeConfig?.surface_profile || "clean"),
    enforcePreset: deckArchetypeProfile === "education_textbook",
    showDecorations: !(
      constraintHardness === "minimal" || constraintHardness === "strict" || density === "sparse"
    ),
    maxBullets: Math.max(4, Math.min(7, maxBullets)),
    backdrop: String(recipeConfig?.backdrop || preset.backdrop || "minimal-grid"),
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

function pickReadableTextColorForFill(fillHex, theme = {}) {
  const bg = cleanHex(fillHex, "FFFFFF");
  const lightCandidate = cleanHex(theme?.darkText || "F8FAFC", "F8FAFC");
  const darkCandidate = "111827";
  const candidate = pickReadableTextColor(bg, lightCandidate, darkCandidate);
  if (contrastRatio(candidate, bg) >= 4.5) return candidate;
  return pickReadableTextColor(bg, "F8FAFC", darkCandidate);
}

function ensureReadableTextColor(preferredHex, bgHex, theme = {}, minContrast = 4.5) {
  const preferred = cleanHex(preferredHex, "");
  const bg = cleanHex(bgHex, "FFFFFF");
  if (preferred && contrastRatio(preferred, bg) >= minContrast) return preferred;
  return pickReadableTextColorForFill(bg, theme);
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

function normalizeSubtype(value) {
  const key = normalizeKey(value || "");
  if (key === "data") return "data_visualization";
  if (key === "mixed") return "mixed_media";
  if (key === "image_showcase" || key === "showcase") return "image_showcase";
  if (key === "data_visualization") return "data_visualization";
  if (key === "mixed_media") return "mixed_media";
  return key || "content";
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

function normalizeImageDataForPptx(rawInput) {
  const raw = String(rawInput || "").trim();
  const base64Match = raw.match(/^data:(image\/[a-zA-Z0-9+.-]+);base64,(.+)$/i);
  if (base64Match) return `${base64Match[1]};base64,${base64Match[2]}`;
  const dataUriMatch = raw.match(/^data:(image\/[a-zA-Z0-9+.-]+)(;[^,]*)?,([\s\S]+)$/i);
  if (dataUriMatch) {
    const mime = String(dataUriMatch[1] || "image/png").toLowerCase();
    const meta = String(dataUriMatch[2] || "").toLowerCase();
    const payload = String(dataUriMatch[3] || "");
    if (meta.includes(";base64")) return `${mime};base64,${payload}`;
    try {
      const decoded = decodeURIComponent(payload);
      return `${mime};base64,${Buffer.from(decoded, "utf-8").toString("base64")}`;
    } catch {
      try {
        return `${mime};base64,${Buffer.from(payload, "utf-8").toString("base64")}`;
      } catch {
        return "";
      }
    }
  }
  if (/^image\/[a-zA-Z0-9+.-]+;base64,/.test(raw)) return raw;
  return "";
}

function pickSlideImageData(slide) {
  const blocks = Array.isArray(slide?.blocks) ? slide.blocks : [];
  const imageBlock = blocks.find((block) => blockType(block) === "image");
  if (!imageBlock || typeof imageBlock !== "object") return "";
  const content = imageBlock.content && typeof imageBlock.content === "object" ? imageBlock.content : {};
  const data = imageBlock.data && typeof imageBlock.data === "object" ? imageBlock.data : {};
  const candidates = [
    content.url,
    content.src,
    content.imageUrl,
    data.url,
    data.src,
    data.imageUrl,
    imageBlock.url,
    imageBlock.src,
    imageBlock.imageUrl,
  ];
  for (const candidate of candidates) {
    const normalized = normalizeImageDataForPptx(candidate);
    if (normalized) return normalized;
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
  const compactLine = (value) => {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    if (!text) return "";
    const hasCjk = /[\u4e00-\u9fff]/.test(text);
    const maxLen = hasCjk ? 34 : 72;
    if (text.length <= maxLen) return text;
    return `${text.slice(0, Math.max(1, maxLen - 1))}…`;
  };
  const appendLines = (rawText) => {
    const plain = htmlToMultilineText(rawText);
    if (!plain) return;
    const lineChunks = plain
      .split(/\r?\n/)
      .map((line) => line.replace(bulletPrefix, "").trim())
      .filter(Boolean);
    if (lineChunks.length > 1) {
      for (const line of lineChunks) {
        if (line.length >= 4) lines.push(compactLine(line));
      }
      return;
    }
    for (const line of plain.split(sentenceSplit)) {
      const t = line.replace(bulletPrefix, "").trim();
      if (t.length < 4) continue;
      lines.push(compactLine(t));
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
        if (line.length >= 4) lines.push(compactLine(line));
      }
    } else {
      for (const line of String(fallbackText).split(sentenceSplit)) {
        const t = line.replace(bulletPrefix, "").trim();
        if (t.length >= 4) lines.push(compactLine(t));
      }
    }
  } else if (lines.length > 0 && lines.length < 4 && fallbackText) {
    for (const line of String(fallbackText).split(sentenceSplit)) {
      const t = line.replace(bulletPrefix, "").trim();
      if (t.length >= 6) lines.push(compactLine(t));
      if (lines.length >= 6) break;
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
    if (dedup.length >= 6) break;
  }
  return dedup;
}

function filterLinesAgainstTitle(lines, title) {
  const titleKey = normalizeTextKey(title);
  const out = [];
  const seen = new Set();
  for (const raw of Array.isArray(lines) ? lines : []) {
    const text = String(raw || "").trim();
    if (!text) continue;
    const key = normalizeTextKey(text);
    if (!key || seen.has(key)) continue;
    if (titleKey && (key === titleKey || key.includes(titleKey) || titleKey.includes(key))) continue;
    seen.add(key);
    out.push(text);
  }
  return out;
}

function resolveCoverSubtitle(title, sourceSlide, bullets = [], narration = "") {
  const candidates = filterLinesAgainstTitle([
    narration,
    ...(Array.isArray(bullets) ? bullets : []),
    String(pick(sourceSlide || {}, ["narration", "speaker_notes", "speakerNotes"], "")).trim(),
  ], title);
  return candidates.slice(0, 2).join("\n").trim();
}

function resolveTocSections(sourceSlide, allSlides, fallbackBullets = []) {
  const fallback = Array.isArray(fallbackBullets) ? fallbackBullets : [];
  const downstreamTitles = (Array.isArray(allSlides) ? allSlides : [])
    .filter((slide) => {
      const type = resolveExplicitSlideType(slide);
      return !["cover", "toc", "summary", "divider"].includes(type);
    })
    .map((slide, idx) => htmlToText(String(pick(slide, ["title"], `Section ${idx + 1}`))).trim())
    .filter(Boolean)
    .slice(0, 7);
  const merged = [];
  const seen = new Set();
  for (const item of [...downstreamTitles, ...fallback]) {
    const text = String(item || "").trim();
    const key = normalizeTextKey(text);
    if (!text || !key || seen.has(key)) continue;
    seen.add(key);
    merged.push(text);
    if (merged.length >= 7) break;
  }
  return merged.length ? merged : ["Overview", "Core Content", "Summary"];
}

function extractSupportNoteFromSlide(sourceSlide = {}, fallback = "") {
  const blocks = Array.isArray(sourceSlide?.blocks) ? sourceSlide.blocks : [];
  const texts = [];
  for (const block of blocks) {
    const type = String(block?.block_type || block?.type || "").trim().toLowerCase();
    if (!["subtitle", "body", "quote", "list", "icon_text"].includes(type)) continue;
    const text = blockText(block);
    if (text) texts.push(htmlToText(text).trim());
  }
  const merged = texts.filter(Boolean).join(" ").trim();
  return merged || String(fallback || "").trim();
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
  const hasImage =
    elements.some((el) => String(el?.type || "").toLowerCase() === "image")
    || blocks.some((block) => blockType(block) === "image");
  const hasChart =
    elements.some((el) => String(el?.type || "").toLowerCase() === "chart")
    || blocks.some((block) => ["chart", "kpi"].includes(blockType(block)));
  const hasWorkflow = blocks.some((block) => ["workflow", "diagram"].includes(blockType(block)));
  const candidates = [];

  const push = (value) => {
    const key = normalizeSubtype(value || "");
    if (!["content", "comparison", "timeline", "data_visualization", "table", "section", "mixed_media", "image_showcase"].includes(key)) return;
    if (!candidates.includes(key)) candidates.push(key);
  };

  const normalizedInferred = normalizeSubtype(inferred);
  if (normalizedInferred && normalizedInferred !== "content") push(normalizedInferred);
  if (hasTable) push("table");
  if (hasChart || hasNumericSignal(bullets)) push("data_visualization");
  if (hasImage && hasChart) push("mixed_media");
  if (hasImage && /(\u5c55\u793a|\u6848\u4f8b|showcase|gallery|before|after)/.test(title)) push("image_showcase");
  if (hasImage) push("mixed_media");
  if (hasWorkflow) push("mixed_media");
  if (/(\u5bf9\u6bd4|\u6bd4\u8f83|vs|versus|\u4f18\u52bf|\u5dee\u5f02)/.test(title)) push("comparison");
  if (/(\u8def\u7ebf|\u91cc\u7a0b\u7891|roadmap|timeline|\u9636\u6bb5|\u6b65\u9aa4|\u5b9e\u65bd)/.test(title)) push("timeline");
  if (/(\u7ae0\u8282|\u90e8\u5206|part|section)/.test(title)) push("section");
  if (/(\u6848\u4f8b|\u65b9\u6848|\u573a\u666f|\u5ba2\u6237)/.test(title)) push("comparison");
  if (index === total - 1 && hasNumericSignal(bullets)) push("data_visualization");
  if (normalizedInferred === "content") push("content");
  push("content");
  if (candidates.length === 1 && candidates[0] === "content") {
    // Keep minimum visual diversity when source signal is weak.
    const rotation = ["comparison", "mixed_media", "data_visualization", "table", "content"];
    push(rotation[index % rotation.length]);
    push(rotation[(index + 2) % rotation.length]);
  }
  return candidates.length ? candidates : ["content"];
}

function planDeckSubtypes(deckSlides) {
  const total = Array.isArray(deckSlides) ? deckSlides.length : 0;
  if (total <= 0) return [];

  const typeCounts = new Map();
  const maxTypeRatio = total >= 8 ? 0.35 : 0.45;
  const maxTop2Ratio = total >= 8 ? 0.65 : 0.75;
  const maxPerType = Math.max(2, Math.floor(total * maxTypeRatio));
  const maxAdjacentRepeat = 1;
  let prevType = "";
  let runLength = 0;
  const selectedTypes = [];

  return deckSlides.map((slide, idx) => {
    const candidates = buildSubtypeCandidates(slide, idx, total);
    let selected = candidates[0] || "content";

    for (const candidate of candidates) {
      const used = Number(typeCounts.get(candidate) || 0);
      const exceedsRatio = used >= maxPerType && candidates.length > 1;
      const exceedsAdjacent =
        candidate === prevType && runLength >= maxAdjacentRepeat && candidates.length > 1;
      const top2Projected = (() => {
        const projected = new Map(typeCounts);
        projected.set(candidate, used + 1);
        const counts = [...projected.values()].sort((a, b) => b - a);
        const top2 = (counts[0] || 0) + (counts[1] || 0);
        const nextTotal = idx + 1;
        return top2 > Math.max(2, Math.floor(nextTotal * maxTop2Ratio)) && candidates.length > 1;
      })();
      const ababPattern =
        selectedTypes.length >= 3
        && selectedTypes[selectedTypes.length - 3] === selectedTypes[selectedTypes.length - 1]
        && selectedTypes[selectedTypes.length - 2] === candidate
        && selectedTypes[selectedTypes.length - 2] !== selectedTypes[selectedTypes.length - 1]
        && candidates.length > 1;
      if (exceedsRatio || exceedsAdjacent || top2Projected || ababPattern) continue;
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
    selectedTypes.push(selected);
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
  return normalizeSubtype(inferSubtypeHeuristic(slide));
}

function resolveSubtypeByTemplate(subtype, templateFamily) {
  return normalizeSubtype(resolveSubtypeByTemplateRegistry(normalizeSubtype(subtype), templateFamily));
}

function selectStyle(styleInput, styleHint, topicText, preserveOriginal = false) {
  return selectStyleHeuristic(styleInput, styleHint, topicText, preserveOriginal);
}

function selectPalette(paletteInput, topicText, preserveOriginal = false) {
  const suggested = selectPaletteHeuristic(paletteInput, topicText, preserveOriginal);
  const canonical = canonicalizePaletteFromCatalog(suggested, topicText);
  if (canonical && canonical !== "auto") return canonical;
  const fallback = normalizeKey(TEMPLATE_CATALOG?.default_palette_key || "business_authority");
  return PALETTES[fallback] ? fallback : "business_authority";
}

function applyThemeRecipe(baseTheme, recipeId = "consulting_clean", surfaceProfile = "clean") {
  const recipe = String(recipeId || "consulting_clean").toLowerCase();
  const profile = String(surfaceProfile || "clean").toLowerCase();
  const next = { ...baseTheme };
  if (recipe === "classroom_soft") {
    next.accentSoft = blendHex(next.accentSoft || next.accent || next.bg, next.bg, 0.78);
    next.accent = blendHex(next.accent || next.secondary, next.bg, 0.62);
    next.secondary = blendHex(next.secondary || next.primary, "EAF3FF", 0.48);
  } else if (recipe === "editorial_magazine") {
    next.accentStrong = blendHex(next.accentStrong || next.primary, "B45309", 0.35);
    next.accent = blendHex(next.accent || next.secondary, next.accentStrong || next.primary, 0.45);
    next.primary = blendHex(next.primary || next.secondary, "111827", 0.38);
  } else if (recipe === "tech_cinematic") {
    next.primary = blendHex(next.primary || next.secondary, "0B1F4A", 0.34);
    next.secondary = blendHex(next.secondary || next.primary, "0EA5E9", 0.46);
    next.accentStrong = blendHex(next.accentStrong || next.accent || next.secondary, "22D3EE", 0.5);
    next.accentSoft = blendHex(next.accentSoft || next.accent || next.bg, "0B1F4A", 0.32);
  } else if (recipe === "energetic_campaign") {
    next.accentStrong = blendHex(next.accentStrong || next.accent || next.primary, "FF7A18", 0.56);
    next.accent = blendHex(next.accent || next.secondary, "FDBA74", 0.52);
    next.secondary = blendHex(next.secondary || next.primary, "14B8A6", 0.48);
  } else {
    // consulting_clean (default): keep palette stable, reduce over-saturation.
    next.accent = blendHex(next.accent || next.secondary, next.bg, 0.58);
    next.accentSoft = blendHex(next.accentSoft || next.accent || next.bg, next.bg, 0.75);
  }
  if (profile === "cinematic") {
    next.bg = blendHex(next.bg, "0A0F1E", 0.35);
  } else if (profile === "soft") {
    next.bg = blendHex(next.bg, "F8FAFC", 0.3);
  } else if (profile === "editorial") {
    next.bg = blendHex(next.bg, "F8F5F0", 0.36);
  } else if (profile === "vivid") {
    next.bg = blendHex(next.bg, "FFF8F2", 0.22);
  }
  return next;
}

function normalizeToneValue(value) {
  const normalized = normalizeKey(value || "");
  if (normalized === "light" || normalized === "dark") return normalized;
  return "auto";
}

function buildTheme({
  paletteKey,
  themeRecipe = "consulting_clean",
  tone = "auto",
  surfaceProfile = "clean",
} = {}) {
  const normalized = canonicalizePaletteFromCatalog(paletteKey, deckTitle) || normalizeKey(paletteKey || "");
  const fallback = normalizeKey(TEMPLATE_CATALOG?.default_palette_key || "business_authority");
  const colors = PALETTES[normalized]
    || PALETTES[fallback]
    || Object.values(PALETTES)[0]
    || ["2B2D42", "8D99AE", "EDF2F4", "EF233C", "D90429"];

  const withLuma = colors.map((hex) => {
    const cleaned = cleanHex(hex, "FFFFFF");
    const r = parseInt(cleaned.slice(0, 2), 16);
    const g = parseInt(cleaned.slice(2, 4), 16);
    const b = parseInt(cleaned.slice(4, 6), 16);
    const luma = (0.2126 * r + 0.7152 * g + 0.0722 * b);
    return { hex: cleaned, luma };
  }).sort((a, b) => a.luma - b.luma);

  const primary = withLuma[0]?.hex || "22223B";
  const secondary = withLuma[1]?.hex || "4A4E69";
  const accentStrong = withLuma[2]?.hex || "C9ADA7";
  const light = withLuma[3]?.hex || "DCE7F5";
  const bg = withLuma[4]?.hex || "F2E9E4";
  const accent = blendHex(accentStrong, bg, 0.55);
  const accentSoft = blendHex(accentStrong, bg, 0.72);
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
  const recipeTheme = applyThemeRecipe(baseTheme, themeRecipe, surfaceProfile);
  const normalizedTone = normalizeToneValue(tone);
  const toneTemplate = normalizedTone === "light"
    ? "consulting_warm_light"
    : normalizedTone === "dark"
      ? "dashboard_dark"
      : (isDark(recipeTheme.bg) ? "dashboard_dark" : "consulting_warm_light");
  const resolved = buildDarkTheme(recipeTheme, toneTemplate);
  return {
    ...resolved,
    tone: normalizedTone === "auto" ? (toneTemplate.endsWith("_light") ? "light" : "dark") : normalizedTone,
    theme_recipe: String(themeRecipe || "consulting_clean"),
  };
}

function addPageBadge(slide, index, theme, style) {
  const y = 5.14;
  const w = style === "pill" ? 0.7 : 0.55;
  const x = 9.85 - w;
  const badgeFill = cleanHex(theme.accentStrong || theme.accent || theme.secondary || "2563EB", "2563EB");
  const badgeTextColor = pickReadableTextColorForFill(badgeFill, theme);
  slide.addShape("roundRect", {
    x,
    y,
    w,
    h: 0.35,
    rectRadius: STYLE_RECIPES[style].badgeRadius,
    fill: { color: badgeFill },
    line: { color: badgeFill, pt: 0 },
  });
  slide.addText(String(index).padStart(2, "0"), {
    x,
    y,
    w,
    h: 0.35,
    fontFace: FONT_BY_STYLE[style].enBody,
    fontSize: 11,
    bold: true,
    color: badgeTextColor,
    fill: { color: badgeFill, transparency: 0 },
    align: "center",
    valign: "mid",
    margin: 0,
  });
}

function addVisualBackdrop(slide, theme, visualConfig, mode = "content") {
  if (!visualConfig?.enabled) return;
  const baseBackdrop = normalizeKey(visualConfig.backdrop || "minimal-grid") || "minimal-grid";
  const rotation = [baseBackdrop, ...BACKDROP_VARIANTS.filter((item) => item !== baseBackdrop)];
  const selectedBackdrop = mode === "cover"
    ? baseBackdrop
    : rotation[backdropRenderCounter % Math.max(1, rotation.length)];
  if (mode !== "cover") backdropRenderCounter += 1;
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
  if (selectedBackdrop === "high-contrast") {
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
  if (selectedBackdrop === "color-block") {
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
  if (selectedBackdrop === "soft-gradient") {
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
  if (selectedBackdrop === "corner-accent") {
    slide.addShape("roundRect", {
      ...clampRectToSlide(7.3, 0.18, 2.46, 1.06, DECOR_INSET),
      rectRadius: 0.28,
      fill: { color: theme.accentStrong || theme.accent, transparency: transparencyBase + 4 },
      line: { color: theme.accentStrong || theme.accent, pt: 0 },
    });
    slide.addShape("line", {
      x: 0.42,
      y: 4.86,
      w: 3.12,
      h: 0,
      line: { color: theme.light, pt: 0.65, transparency: 50 },
    });
    return;
  }
  if (selectedBackdrop === "side-panel") {
    slide.addShape("rect", {
      x: 0,
      y: 0.86,
      w: 1.42,
      h: 4.76,
      fill: { color: theme.accentSoft || theme.accent, transparency: 88 },
      line: { color: theme.accentSoft || theme.accent, pt: 0 },
    });
    slide.addShape("line", {
      x: 1.42,
      y: 0.86,
      w: 0,
      h: 4.76,
      line: { color: theme.light, pt: 0.52, transparency: 56 },
    });
    return;
  }
  if (selectedBackdrop === "bottom-wave") {
    slide.addShape("roundRect", {
      ...clampRectToSlide(0, 4.74, 10, 0.94, 0),
      rectRadius: 0.45,
      fill: { color: theme.accentSoft || theme.accent, transparency: 88 },
      line: { color: theme.accentSoft || theme.accent, pt: 0 },
    });
    return;
  }
  if (selectedBackdrop === "dot-grid") {
    const startX = 7.6;
    const startY = 0.96;
    for (let row = 0; row < 5; row += 1) {
      for (let col = 0; col < 4; col += 1) {
        slide.addShape("ellipse", {
          x: startX + col * 0.3,
          y: startY + row * 0.28,
          w: 0.05,
          h: 0.05,
          fill: { color: theme.light, transparency: 48 },
          line: { color: theme.light, pt: 0 },
        });
      }
    }
    return;
  }
  if (selectedBackdrop === "diagonal-split") {
    slide.addShape("line", {
      x: 0,
      y: 5.26,
      w: 10,
      h: -4.6,
      line: { color: theme.light, pt: 0.72, transparency: 52 },
    });
    slide.addShape("rect", {
      x: 6.5,
      y: 0,
      w: 3.5,
      h: 5.62,
      fill: { color: theme.accentSoft || theme.accent, transparency: 93 },
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

function toBoundedInt(value, fallback, minValue, maxValue) {
  const raw = Number(value);
  const safe = Number.isFinite(raw) ? Math.round(raw) : fallback;
  return Math.max(minValue, Math.min(maxValue, safe));
}

function resolveSlideTextConstraints(sourceSlide = {}, slideSubtype = "content", fallbackMaxItems = 5) {
  const raw =
    sourceSlide && typeof sourceSlide === "object" && sourceSlide.text_constraints && typeof sourceSlide.text_constraints === "object"
      ? sourceSlide.text_constraints
      : {};
  const subtype = normalizeKey(slideSubtype || "content") || "content";
  const layout = normalizeKey(sourceSlide?.layout_grid || sourceSlide?.layout || "");
  const compactLayout = layout === "split_2" || layout === "asymmetric_2";
  const timelineLayout = subtype === "timeline" || layout === "timeline";
  const summaryLike = subtype === "summary" || subtype === "toc" || subtype === "divider";
  const defaultBulletMaxItems = summaryLike ? 5 : compactLayout ? 4 : 5;
  const defaultBulletMaxChars = timelineLayout ? 24 : compactLayout ? 26 : 30;
  return {
    bullet_max_items: toBoundedInt(raw.bullet_max_items, Math.max(3, fallbackMaxItems || defaultBulletMaxItems), 2, 8),
    bullet_max_chars_cjk: toBoundedInt(raw.bullet_max_chars_cjk, defaultBulletMaxChars, 14, 72),
    min_body_font_pt: toBoundedInt(raw.min_body_font_pt, 11, 9, 24),
    min_title_font_pt: toBoundedInt(raw.min_title_font_pt, summaryLike ? 24 : 20, 16, 42),
    subtitle_max_lines: toBoundedInt(raw.subtitle_max_lines, 2, 1, 4),
    subtitle_max_chars_cjk: toBoundedInt(raw.subtitle_max_chars_cjk, 80, 24, 160),
    subtitle_min_font_pt: toBoundedInt(raw.subtitle_min_font_pt, 13, 10, 24),
    bullet_auto_split: raw.bullet_auto_split !== false,
  };
}

function sanitizeSubtitleText(text, constraints) {
  const raw = htmlToMultilineText(String(text || "")).trim();
  if (!raw) return "";
  const maxLines = toBoundedInt(constraints?.subtitle_max_lines, 2, 1, 4);
  const maxChars = toBoundedInt(constraints?.subtitle_max_chars_cjk, 80, 24, 160);
  const lines = raw
    .split(/\r?\n/)
    .map((line) => String(line || "").replace(/\s+/g, " ").trim())
    .filter(Boolean);
  const flattened = lines.length > 0 ? lines : [raw];
  const clipped = [];
  for (const line of flattened) {
    if (clipped.length >= maxLines) break;
    if (line.length <= maxChars) {
      clipped.push(line);
      continue;
    }
    const chunks = line.split(/[；;。.!?！？]/).map((item) => item.trim()).filter(Boolean);
    if (chunks.length > 1) {
      for (const chunk of chunks) {
        if (clipped.length >= maxLines) break;
        const safeChunk = chunk.length > maxChars ? `${chunk.slice(0, maxChars - 1).trim()}…` : chunk;
        clipped.push(safeChunk);
      }
      continue;
    }
    clipped.push(`${line.slice(0, maxChars - 1).trim()}…`);
  }
  return clipped.slice(0, maxLines).join("\n");
}

function addCover(pres, title, subtitle, theme, style, visualConfig, sourceSlide = undefined) {
  const textConstraints = resolveSlideTextConstraints(sourceSlide || {}, "cover", 5);
  const safeSubtitle = sanitizeSubtitleText(subtitle, textConstraints);
  const slide = setSlideThemeContext(pres.addSlide(), theme);
  slide.background = { color: theme.bg };
  const useEducationClassic = deckArchetypeProfile === "education_textbook";
  if (!useEducationClassic) {
    const svg = buildTerminalPageSvg("cover", {
      title,
      subtitle: safeSubtitle,
      pageLabel: "01",
    }, theme, 1280, 720);
    addSvgOverlay(slide, svg, { x: 0, y: 0, w: 10, h: 5.625 });
  } else {
    slide.addShape("line", { x: 0.62, y: 0.92, w: 1.1, h: 0, line: { color: "1F497D", pt: 2.5 } });
    slide.addShape("line", { x: 0.62, y: 0.99, w: 0.58, h: 0, line: { color: "4F81BD", pt: 1.4 } });
  }
  const titleCardBg = cleanHex(theme.white || theme.cardBg || theme.bg || "FFFFFF", "FFFFFF");
  const coverTitleColor = ensureReadableTextColor(theme.primary, titleCardBg, theme, 4.8);
  const coverSubtitleColor = ensureReadableTextColor(
    theme.secondary || theme.mutedText || theme.darkText,
    titleCardBg,
    theme,
    4.8,
  );

  const titleText = String(title || "Presentation").trim();
  const titleParts = titleText.split(/[：:]/).map((item) => item.trim()).filter(Boolean);
  const line1 = titleParts[0] || titleText;
  const line2 = titleParts.length > 1 ? titleParts.slice(1).join("：") : "";
  const mergedSubtitle = [safeSubtitle]
    .flatMap((item) => String(item || "").split(/\r?\n/))
    .map((item) => String(item || "").trim())
    .filter(Boolean)
    .filter((item) => item !== line1 && item !== line2)
    .filter((item, idx, arr) => arr.findIndex((x) => x === item) === idx)
    .join("\n");
  const coverMinTitleFont = toBoundedInt(textConstraints.min_title_font_pt, 30, 20, 56);
  const titleSizeBase = titleText.length > 22 ? 32 : 40;
  const titleSize = Math.max(coverMinTitleFont, titleSizeBase);
  const renderLine2AsTitle = !useEducationClassic && Boolean(line2);
  slide.addText(line1, {
    x: 0.48,
    y: 1.75,
    w: 5.9,
    h: 0.7,
    fontFace: FONT_ZH,
    fontSize: titleSize,
    bold: true,
    color: coverTitleColor,
    margin: 0,
  });
  if (renderLine2AsTitle) {
    slide.addText(line2, {
      x: 0.48,
      y: 2.28,
      w: 5.9,
      h: 0.7,
      fontFace: FONT_ZH,
      fontSize: titleSize,
      bold: true,
      color: coverTitleColor,
      margin: 0,
    });
  }
  const subtitleText = [
    useEducationClassic ? line2 : "",
    mergedSubtitle,
  ].map((item) => String(item || "").trim()).filter(Boolean).filter((item, idx, arr) => arr.findIndex((x) => x === item) === idx).join("\n");
  if (subtitleText) {
    slide.addText(subtitleText, {
      x: 0.48,
      y: 3.08,
      w: 5.4,
      h: 0.75,
      fontFace: FONT_BY_STYLE[style].enBody,
      fontSize: Math.max(13, toBoundedInt(textConstraints.subtitle_min_font_pt, 13, 10, 24)),
      color: coverSubtitleColor,
      margin: 0,
      valign: "top",
    });
  }
}

function addToc(pres, sectionTitles, theme, style, visualConfig, pageNumber = 2, sourceSlide = undefined) {
  const slide = setSlideThemeContext(pres.addSlide(), theme);
  slide.background = { color: theme.bg };
  const tocTitle = htmlToText(String(pick(sourceSlide || {}, ["title"], ""))).trim()
    || (preferZhText(sourceSlide?.title, sectionTitles) ? "内容导航" : "Table of Contents");
  const useEducationClassic = deckArchetypeProfile === "education_textbook";
  if (!useEducationClassic) {
    const svg = buildTerminalPageSvg("toc", {
      title: tocTitle,
      sections: sectionTitles,
      focus: htmlToText(String(pick(sourceSlide || {}, ["narration", "speaker_notes"], ""))).trim(),
    }, theme, 1280, 720);
    addSvgOverlay(slide, svg, { x: 0, y: 0, w: 10, h: 5.625 });
    slide.addText(tocTitle, {
      x: 0.52,
      y: 1.58,
      w: 2.2,
      h: 0.42,
      fontFace: FONT_ZH,
      fontSize: 26,
      bold: true,
      color: "FFFFFF",
      margin: 0,
    });
  } else {
    slide.addShape("line", { x: 0.64, y: 0.9, w: 1.1, h: 0, line: { color: "1F497D", pt: 2.5 } });
    slide.addText(tocTitle, {
      x: 0.78,
      y: 1.02,
      w: 3.2,
      h: 0.42,
      fontFace: FONT_ZH,
      fontSize: 24,
      bold: true,
      color: "1F1F1F",
      margin: 0,
    });
    const tocSupport = extractSupportNoteFromSlide(
      sourceSlide,
      htmlToText(String(pick(sourceSlide || {}, ["narration", "speaker_notes"], ""))).trim(),
    );
    if (tocSupport) {
      const tocSupportText = String(tocSupport).length > 68 ? `${String(tocSupport).slice(0, 67).trim()}…` : String(tocSupport);
      slide.addText(tocSupportText, {
        x: 5.42,
        y: 1.03,
        w: 3.55,
        h: 0.42,
        fontFace: FONT_ZH,
        fontSize: 12,
        color: "5F6B7A",
        margin: 0,
        fit: "shrink",
      });
    }
  }
  const tocItems = sectionTitles.slice(0, 7);
  const tocColumns = useEducationClassic
    ? [tocItems.slice(0, 4), tocItems.slice(4, 7)]
    : [tocItems, []];
  tocColumns.forEach((column, columnIndex) => {
    column.forEach((name, rowIndex) => {
      const itemIndex = (columnIndex === 0 ? rowIndex : rowIndex + tocColumns[0].length);
      const baseX = useEducationClassic ? (columnIndex === 0 ? 0.92 : 5.3) : 3.63;
      const textX = useEducationClassic ? (columnIndex === 0 ? 1.52 : 5.9) : 4.3;
      const y = useEducationClassic ? (1.46 + rowIndex * 0.62) : (1.47 + itemIndex * 0.86);
      slide.addText(String(itemIndex + 1).padStart(2, "0"), {
        x: baseX,
        y,
        w: useEducationClassic ? 0.42 : 0.38,
        h: 0.30,
        fontFace: FONT_BY_STYLE[style].enBody,
        fontSize: useEducationClassic ? 12 : 15,
        bold: true,
        color: useEducationClassic ? "1F497D" : (itemIndex % 2 === 0 ? theme.primary : "FFFFFF"),
        align: "center",
        valign: "mid",
        margin: 0,
      });
      slide.addText(name, {
        x: textX,
        y: y - 0.01,
        w: useEducationClassic ? 3.55 : 4.8,
        h: 0.34,
        fontFace: FONT_ZH,
        fontSize: useEducationClassic ? 14 : 17,
        color: useEducationClassic ? "1F1F1F" : theme.darkText,
        margin: 0,
        fit: "shrink",
      });
    });
  });

  if (!useEducationClassic) {
    addPageBadge(slide, pageNumber, theme, style);
  }
}

function addHeader(slide, title, theme, style, visualConfig, templateFamily = "dashboard_dark", textConstraints = undefined) {
  const recipe = STYLE_RECIPES[style];
  const isLightTemplate = String(templateFamily || "").endsWith("_light");
  const headerStyle = String(
    getTemplateField(
      templateFamily,
      "header_style",
      isLightTemplate ? "underline-light" : "solid",
    ),
  ).toLowerCase();
  const lightBg = templateFamily === "consulting_warm_light" ? "F7F3EE" : "F4F7FC";
  const bgColor = isLightTemplate ? lightBg : theme.bg;
  const borderColor = isLightTemplate ? (templateFamily === "consulting_warm_light" ? "D8BFAA" : "CFDAEC") : theme.borderColor;
  const darkHeaderBg = headerStyle === "line" ? blendHex(theme.primary, theme.bg, 0.72) : theme.primary;
  const titleColor = isLightTemplate
    ? (templateFamily === "consulting_warm_light" ? "3A2A23" : "0F1E35")
    : pickReadableTextColor(darkHeaderBg, theme.white || "FFFFFF", theme.darkText || "111827");
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
    fill: { color: isLightTemplate ? bgColor : darkHeaderBg },
    line: { color: isLightTemplate ? borderColor : darkHeaderBg, pt: isLightTemplate ? 0.5 : 0 },
  });
  if (!isLightTemplate) {
    if (headerStyle === "gradient") {
      slide.addShape("rect", {
        x: 0,
        y: 0,
        w: 10,
        h: recipe.headerHeight,
        fill: { color: theme.accentSoft || theme.accent, transparency: 82 },
        line: { color: theme.accentSoft || theme.accent, pt: 0 },
      });
      slide.addShape("line", {
        x: 0.4,
        y: recipe.headerHeight - 0.01,
        w: 9.2,
        h: 0,
        line: { color: theme.light, pt: 1.2, transparency: 24 },
      });
    } else if (headerStyle === "band") {
      slide.addShape("rect", {
        x: 0,
        y: recipe.headerHeight - 0.09,
        w: 10,
        h: 0.09,
        fill: { color: theme.accentStrong || theme.accent, transparency: 18 },
        line: { color: theme.accentStrong || theme.accent, pt: 0 },
      });
    } else if (headerStyle === "line") {
      slide.addShape("line", {
        x: 0.56,
        y: recipe.headerHeight - 0.03,
        w: 8.8,
        h: 0,
        line: { color: theme.accentStrong || theme.accent, pt: 1.5, transparency: 16 },
      });
    }
  }
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
  const dynamicTitleSize = (
    titleLen > 42 ? baseTitleSize - 7
      : titleLen > 34 ? baseTitleSize - 5
        : titleLen > 28 ? baseTitleSize - 3
          : titleLen > 20 ? baseTitleSize - 1
            : baseTitleSize
  );
  const titleFloor = toBoundedInt(textConstraints?.min_title_font_pt, 18, 16, 42);
  slide.addText(title, {
    x: isLightTemplate ? recipe.pageMargin + 0.12 : recipe.pageMargin,
    y: 0.08,
    w: visualConfig?.enabled ? 7.6 : 8.8,
    h: 0.42,
    fontFace: FONT_ZH,
    fontSize: Math.max(titleFloor, dynamicTitleSize),
    bold: true,
    color: titleColor,
    fit: "shrink",
    breakLine: false,
    margin: 0,
  });
}

function sanitizeBulletText(text) {
  return String(text || "")
    .replace(/^[\s\-*+•·●○◆▶✓]+\s*/g, "")
    .replace(/^(?:补充要点|Supporting point)\s*[:：-]\s*/i, "")
    .replace(/\s+/g, " ")
    .trim();
}

function splitBulletByPunctuation(text, maxChars) {
  const cleaned = sanitizeBulletText(text);
  if (!cleaned) return [];
  if (cleaned.length <= maxChars) return [cleaned];
  const chunks = cleaned
    .split(/[；;。.!?！？]/)
    .map((item) => item.trim())
    .filter(Boolean);
  if (chunks.length > 1) {
    return chunks.flatMap((chunk) => splitBulletByPunctuation(chunk, maxChars));
  }
  const out = [];
  for (let i = 0; i < cleaned.length; i += maxChars) {
    const slice = cleaned.slice(i, i + maxChars).trim();
    if (slice) out.push(slice);
    if (out.length >= 3) break;
  }
  return out;
}

function clampBulletText(text, width, style, maxCharsOverride = undefined) {
  const raw = sanitizeBulletText(text);
  if (!raw) return "";
  const widthSafe = Math.max(1, Number(width) || 1);
  const base = Math.floor(widthSafe * (style === "sharp" ? 10 : 11));
  const localLimit = Math.max(18, Math.min(64, base));
  const maxChars = toBoundedInt(maxCharsOverride, localLimit, 14, 72);
  if (raw.length <= maxChars) return raw;
  return `${raw.slice(0, Math.max(6, maxChars - 1)).trim()}…`;
}

function prepareBulletsForList(bullets, maxItems, maxChars, autoSplit = true) {
  const source = Array.isArray(bullets) ? bullets : [];
  const out = [];
  const seen = new Set();
  for (const item of source) {
    const text = sanitizeBulletText(item);
    if (!text) continue;
    const units = autoSplit ? splitBulletByPunctuation(text, maxChars) : [text];
    for (const unit of units) {
      const normalized = normalizeTextKey(unit);
      if (!normalized || seen.has(normalized)) continue;
      seen.add(normalized);
      out.push(unit);
      if (out.length >= maxItems) return out;
    }
  }
  return out;
}

function addBulletList(slide, bullets, x, y, w, h, theme, style, maxItems = 5, options = {}) {
  const recipe = STYLE_RECIPES[style];
  const textConstraints =
    options && typeof options === "object" && options.textConstraints && typeof options.textConstraints === "object"
      ? options.textConstraints
      : {};
  const minBodyFont = toBoundedInt(textConstraints.min_body_font_pt, 11, 9, 24);
  const maxChars = toBoundedInt(textConstraints.bullet_max_chars_cjk, 30, 14, 72);
  const limitByConstraint = toBoundedInt(textConstraints.bullet_max_items, maxItems, 2, 8);
  const autoSplit = textConstraints.bullet_auto_split !== false;
  const effectiveMaxItems = Math.max(1, Math.min(Math.max(1, maxItems), limitByConstraint));
  const prepared = prepareBulletsForList(bullets, effectiveMaxItems, maxChars, autoSplit);
  prepared.forEach((item, i) => {
    const text = clampBulletText(item, w, style, maxChars);
    if (!text) return;
    const sizeBase = text.length > 40 ? recipe.bodySize - 2 : recipe.bodySize;
    const size = Math.max(minBodyFont, sizeBase);
    const rowH = text.length > 40 ? 0.44 : 0.40;
    const yy = y + i * Math.max(recipe.bulletStep, rowH + 0.06);
    if (yy + rowH > y + h) return;
    slide.addText(`• ${text}`, {
      x: x + 0.02,
      y: yy,
      w: Math.max(0.6, w - 0.04),
      h: rowH,
      fontFace: FONT_ZH,
      fontSize: size,
      bold: false,
      color: theme.darkText,
      fit: "shrink",
      breakLine: false,
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
  const useEducationClassic = deckArchetypeProfile === "education_textbook";
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
  if (!useEducationClassic) {
    addPageBadge(slide, pageNumber, theme, style);
  }
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
  const useEducationClassic = deckArchetypeProfile === "education_textbook";
  const recipe = STYLE_RECIPES[style];
  const title = htmlToText(String(pick(slideData, ["title"], `Slide ${pageNumber}`))) || `Slide ${pageNumber}`;
  const narration = htmlToText(String(pick(slideData, ["narration", "speaker_notes", "speakerNotes"], "")));
  const bullets = collectBullets(slideData, narration);
  let subtype = resolveSubtypeByTemplate(
    normalizeKey(forcedSubtype || "") || inferSubtype(slideData),
    templateFamily,
  );
  if (deckArchetypeProfile === 'education_textbook' && templateFamily === 'education_textbook_light') {
    const archetypeKey = String(slideData?.archetype || slideData?.archetype_plan?.selected || '').trim().toLowerCase();
    if (archetypeKey === 'chart_dual_compare') subtype = 'comparison';
    else if (archetypeKey === 'chart_single_focus') subtype = 'content';
    else if (archetypeKey === 'process_flow_4step' || normalizeKey(slideData?.layout_grid || '') === 'timeline') subtype = 'timeline';
    else if (['mixed_media', 'image_showcase', 'data', 'data_visualization'].includes(subtype)) subtype = 'content';
  }
  const maxBullets = Math.max(3, visualConfig?.maxBullets || 5);
  const textConstraints = resolveSlideTextConstraints(slideData || {}, subtype, maxBullets);
  const constrainedMaxBullets = Math.max(
    2,
    Math.min(maxBullets, toBoundedInt(textConstraints.bullet_max_items, maxBullets, 2, 8)),
  );

  const slide = setSlideThemeContext(pres.addSlide(), theme);
  maybeAddSvgLayer(slide, slideData, theme, pick(slideData, ["layout_grid", "layout"], "split_2"));
  if (subtype === "section") {
    addSectionDivider(slide, title, pageNumber, theme, style);
    return;
  }

  const templateCapability = assessTemplateCapabilityForSlide({
    sourceSlide: slideData,
    templateFamily,
    slideType: pick(
      slideData,
      ["page_type", "pageType", "slide_type", "slideType", "subtype"],
      subtype,
    ),
    layoutGrid: pick(slideData, ["layout_grid", "layout"], ""),
  });
  const skipTemplateRenderer = !templateCapability.compatible;
  if (slideData && typeof slideData === "object") {
    slideData.__template_capability = templateCapability;
    slideData.__template_renderer_skipped = skipTemplateRenderer;
    slideData.__template_renderer_skip_reason = skipTemplateRenderer
      ? (
        templateCapability.missing_required_image_asset
          ? "missing_required_image_asset"
          : templateCapability.unsupported_layout
            ? "unsupported_layout"
            : templateCapability.unsupported_slide_type
              ? "unsupported_slide_type"
          : "unsupported_block_types"
      )
      : "";
  }

  const templateContentCandidate = !["mixed_media", "image_showcase"].includes(subtype) && !skipTemplateRenderer;
  if (process.env.DEBUG_EDU_TEMPLATE === '1') {
    console.error('[addContentSlide]', JSON.stringify({
      title,
      templateFamily,
      subtype,
      templateContentCandidate,
      skipTemplateRenderer,
      capability: templateCapability,
    }));
  }
  if (templateContentCandidate) {
    const isLightTemplate = String(templateFamily || "").endsWith("_light");
    const lightBg = templateFamily === "consulting_warm_light" ? "F7F3EE" : "F4F7FC";
    slide.background = { color: isLightTemplate ? lightBg : theme.bg };
    if (!isLightTemplate) addVisualBackdrop(slide, theme, visualConfig, "content");
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
          addBulletList: (
            tplSlide,
            tplBullets,
            x,
            y,
            w,
            h,
            tplTheme,
            tplStyle,
            tplMaxItems = 5,
          ) =>
            addBulletList(
              tplSlide,
              tplBullets,
              x,
              y,
              w,
              h,
              tplTheme,
              tplStyle,
              tplMaxItems,
              { textConstraints },
            ),
          pptx: pptxgen,
        },
      })
    ) {
      return;
    }
  }

  addHeader(slide, title, theme, style, visualConfig, templateFamily, textConstraints);
  const bodyTop = recipe.headerHeight + recipe.gap;
  const contentLoad = Math.min(1, (bullets.join(" ").length / 360) + (bullets.length / 8));
  const bodyHeight = Math.min(4.25, Math.max(3.5, 3.0 + contentLoad * 1.1));
  const bodyBottom = Math.min(5.22, bodyTop + bodyHeight);

  if (subtype === "table") {
    const rows = buildTableRows(slideData, bullets);
    renderEnhancedTable(slide, {
      x: recipe.pageMargin,
      y: bodyTop,
      w: 9.2,
      h: bodyBottom - bodyTop,
    }, rows, theme);
  } else if (subtype === "mixed_media") {
    const leftW = 4.45;
    const rightX = recipe.pageMargin + leftW + recipe.gap;
    const rightW = 9.2 - leftW - recipe.gap;
    const imageData = pickSlideImageData(slideData);
    slide.addShape("roundRect", {
      x: recipe.pageMargin,
      y: bodyTop,
      w: leftW,
      h: bodyBottom - bodyTop,
      rectRadius: recipe.cardRadius,
      fill: { color: theme.white, transparency: 4 },
      line: { color: theme.light, pt: 1 },
    });
    addBulletList(
      slide,
      bullets.length ? bullets : [narration || title],
      recipe.pageMargin + 0.18,
      bodyTop + 0.2,
      leftW - 0.34,
      bodyBottom - bodyTop - 0.26,
      theme,
      style,
      constrainedMaxBullets,
      { textConstraints },
    );
    slide.addShape("roundRect", {
      x: rightX,
      y: bodyTop,
      w: rightW,
      h: bodyBottom - bodyTop,
      rectRadius: recipe.cardRadius,
      fill: { color: theme.white, transparency: 6 },
      line: { color: theme.light, pt: 1 },
    });
    if (imageData) {
      slide.addImage({
        data: imageData,
        ...clampRectToSlide(rightX + 0.14, bodyTop + 0.14, rightW - 0.28, bodyBottom - bodyTop - 0.28, 0.02),
      });
    } else {
      const focal = (bullets[0] || title).slice(0, 48);
      slide.addText(focal, {
        x: rightX + 0.2,
        y: bodyTop + 0.65,
        w: rightW - 0.4,
        h: 0.8,
        fontFace: FONT_ZH,
        fontSize: 16,
        bold: true,
        color: theme.secondary,
        align: "center",
        valign: "mid",
        margin: 0,
      });
    }
  } else if (subtype === "image_showcase") {
    const imageData = pickSlideImageData(slideData);
    const visualH = Math.max(1.9, bodyBottom - bodyTop - 1.1);
    slide.addShape("roundRect", {
      x: recipe.pageMargin,
      y: bodyTop,
      w: 9.2,
      h: visualH,
      rectRadius: recipe.cardRadius,
      fill: { color: theme.white, transparency: 4 },
      line: { color: theme.light, pt: 1 },
    });
    if (imageData) {
      slide.addImage({
        data: imageData,
        ...clampRectToSlide(recipe.pageMargin + 0.1, bodyTop + 0.1, 9.0, visualH - 0.2, 0.02),
      });
    } else {
      slide.addText((bullets[0] || title).slice(0, 56), {
        x: recipe.pageMargin + 0.2,
        y: bodyTop + 0.65,
        w: 8.8,
        h: 0.8,
        fontFace: FONT_ZH,
        fontSize: 18,
        bold: true,
        color: theme.secondary,
        align: "center",
        valign: "mid",
        margin: 0,
      });
    }
    addBulletList(
      slide,
      bullets.slice(0, 3),
      recipe.pageMargin + 0.12,
      bodyTop + visualH + 0.14,
      8.95,
      bodyBottom - (bodyTop + visualH) - 0.18,
      theme,
      style,
      3,
      { textConstraints },
    );
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
    addBulletList(
      slide,
      left,
      recipe.pageMargin + 0.2,
      bodyTop + 0.45,
      colW - 0.34,
      bodyBottom - bodyTop - 0.5,
      theme,
      style,
      constrainedMaxBullets,
      { textConstraints },
    );
    addBulletList(
      slide,
      right,
      recipe.pageMargin + colW + recipe.gap + 0.2,
      bodyTop + 0.45,
      colW - 0.34,
      bodyBottom - bodyTop - 0.5,
      theme,
      style,
      constrainedMaxBullets,
      { textConstraints },
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
        constrainedMaxBullets,
        { textConstraints },
      );
      addPageBadge(slide, pageNumber, theme, style);
      return;
    }
    addBulletList(
      slide,
      safeBullets,
      recipe.pageMargin,
      bodyTop,
      leftW,
      bodyBottom - bodyTop,
      theme,
      style,
      constrainedMaxBullets,
      { textConstraints },
    );

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

    if (subtype === "data" || subtype === "data_visualization") {
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

  if (!useEducationClassic) {
    addPageBadge(slide, pageNumber, theme, style);
  }
}

function collectTextLines(slideData, fallbackText = "") {
  const elements = Array.isArray(slideData?.elements) ? slideData.elements : [];
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
  const textConstraints = resolveSlideTextConstraints(slideData || {}, "content", visualConfig?.maxBullets || 5);

  const slide = setSlideThemeContext(pres.addSlide(), theme);
  addHeader(slide, title, theme, style, visualConfig, templateFamily, textConstraints);

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
  fontSize = Math.max(fontSize, toBoundedInt(textConstraints.min_body_font_pt, 11, 9, 24));

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
  const maxBullets = Math.max(3, visualConfig?.maxBullets || 5);
  const textConstraints = resolveSlideTextConstraints(sourceSlide || {}, "summary", maxBullets);
  const constrainedMaxBullets = Math.max(
    2,
    Math.min(maxBullets, toBoundedInt(textConstraints.bullet_max_items, maxBullets, 2, 8)),
  );
  const slide = setSlideThemeContext(pres.addSlide(), theme);
  slide.background = { color: theme.bg };
  const summaryTitle = title || (preferZhText(title, bullets) ? "总结与启示" : "Summary & Takeaways");
  const summarySubtitle = htmlToText(String(pick(sourceSlide || {}, ["narration", "speaker_notes"], ""))).trim();
  const useEducationClassic = deckArchetypeProfile === "education_textbook";
  if (!useEducationClassic) {
    const svg = buildTerminalPageSvg("summary", {
      title: summaryTitle,
      subtitle: summarySubtitle,
      bullets,
      footerLabel: "THANK YOU",
    }, theme, 1280, 720);
    addSvgOverlay(slide, svg, { x: 0, y: 0, w: 10, h: 5.625 });
  } else {
    slide.addShape("line", { x: 0.64, y: 0.9, w: 1.1, h: 0, line: { color: "1F497D", pt: 2.5 } });
  }
  slide.addText(title || "Summary", {
    x: 2.6,
    y: 1.95,
    w: 4.8,
    h: 0.6,
    fontFace: FONT_ZH,
    fontSize: Math.max(32, toBoundedInt(textConstraints.min_title_font_pt, 24, 16, 42)),
    bold: true,
    color: theme.darkText,
    margin: 0,
    align: "center",
  });

  addBulletList(
    slide,
    bullets,
    3.35,
    3.62,
    3.3,
    1.28,
    theme,
    style,
    constrainedMaxBullets,
    { textConstraints },
  );
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
  const existingScript = sourceSlide?.script;
  if (Array.isArray(existingScript)) {
    const normalized = existingScript
      .map((item) => ({
        role: String(item?.role || "host"),
        text: htmlToText(String(item?.text || "")),
      }))
      .filter((item) => item.text);
    if (normalized.length > 0) return normalized.slice(0, 4);
  } else if (existingScript && typeof existingScript === "object") {
    const text = htmlToText(String(existingScript?.text || ""));
    if (text) return [{ role: String(existingScript?.role || "host"), text }];
  }
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

function summarizeTemplateRendererDiagnostics(renderSlides = []) {
  const slides = Array.isArray(renderSlides) ? renderSlides : [];
  const evaluatedSlides = slides
    .map((slide) => slide?.template_renderer)
    .filter((item) => item && typeof item === "object");
  const summary = {
    evaluated_slides: evaluatedSlides.length,
    skipped_slides: 0,
    skipped_ratio: 0,
    mode_counts: {},
    reason_counts: {},
    reason_ratios: {},
  };
  if (!evaluatedSlides.length) return summary;

  for (const item of evaluatedSlides) {
    const mode = String(item.mode || "").trim().toLowerCase() || "unknown";
    summary.mode_counts[mode] = (summary.mode_counts[mode] || 0) + 1;
    if (Boolean(item.skipped)) {
      summary.skipped_slides += 1;
      const reason = String(item.reason || "").trim().toLowerCase() || "unknown";
      summary.reason_counts[reason] = (summary.reason_counts[reason] || 0) + 1;
    }
  }
  const safeRound = (value) => Math.round((Number(value) || 0) * 10000) / 10000;
  summary.skipped_ratio = safeRound(summary.skipped_slides / Math.max(1, summary.evaluated_slides));
  const skippedBase = Math.max(1, summary.skipped_slides);
  for (const [reason, count] of Object.entries(summary.reason_counts)) {
    summary.reason_ratios[reason] = safeRound(count / skippedBase);
  }
  return summary;
}

function buildTemplateRendererDiagnostics(sourceSlide) {
  if (!sourceSlide || typeof sourceSlide !== "object") return undefined;
  const skipped = asBool(sourceSlide.__template_renderer_skipped, false);
  const reason = String(sourceSlide.__template_renderer_skip_reason || "").trim();
  const capability =
    sourceSlide.__template_capability && typeof sourceSlide.__template_capability === "object"
      ? sourceSlide.__template_capability
      : null;
  if (!skipped && !capability) return undefined;
  const unsupportedBlockTypes = Array.isArray(capability?.unsupported_block_types)
    ? capability.unsupported_block_types.filter(Boolean)
    : [];
  return {
    mode: skipped ? "fallback_generic" : "local_template",
    skipped,
    reason: reason || undefined,
    unsupported_block_types: unsupportedBlockTypes.length ? unsupportedBlockTypes : undefined,
    unsupported_slide_type: Boolean(capability?.unsupported_slide_type),
    unsupported_layout: Boolean(capability?.unsupported_layout),
    missing_required_image_asset: Boolean(capability?.missing_required_image_asset),
  };
}

function renderIdentity(pageNumber, sourceSlide) {
  const renderPath = resolveRenderPath(sourceSlide || {});
  const svgRenderMode = String(sourceSlide?.__svg_render_mode || "").trim();
  const templateRenderer = buildTemplateRendererDiagnostics(sourceSlide);
  const resolvedTitle = htmlToText(String(pick(sourceSlide || {}, ["title"], `Slide ${pageNumber}`))) || `Slide ${pageNumber}`;
  const resolvedThemeRecipe = String(
    canonicalizeThemeRecipeFromCatalog(
      pick(sourceSlide || {}, ["theme_recipe", "themeRecipe"], "")
      || requestedThemeRecipe
      || payload.theme_recipe
      || "auto",
    ),
  ) || "auto";
  const resolvedTone = normalizeToneValue(
    pick(sourceSlide || {}, ["tone", "theme_tone", "preferred_tone"], "")
    || requestedTone
    || payload.tone
    || "auto",
  );
  return {
    deck_id: deckId || undefined,
    slide_id: stableSlideId(sourceSlide || {}, Math.max(pageNumber - 1, 0)),
    title: resolvedTitle,
    theme_recipe: resolvedThemeRecipe,
    tone: resolvedTone,
    render_path: renderPath,
    svg_render_mode: svgRenderMode || (renderPath === "svg" ? "pending_svg" : ""),
    ...(templateRenderer ? { template_renderer: templateRenderer } : {}),
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
  const tocTitle = htmlToText(String(pick(sourceSlide || {}, ["title"], ""))).trim()
    || (preferZhText(sourceSlide?.title, sectionTitles) ? "内容导航" : "Table of Contents");
  const tocMark = preferZhText(sourceSlide?.title, sectionTitles) ? "目录" : "Agenda";
  return {
    ...renderIdentity(pageNumber, sourceSlide),
    page_number: pageNumber,
    slide_type: "toc",
    template_family: templateFamily,
    ...templateProfiles,
    markdown: `# ${mdEscape(tocTitle)}\n${list.join("\n")}\n\n<mark>${mdEscape(tocMark)}</mark>`,
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

function resolveContentRenderSlideType(sourceSlide, subtype) {
  const layoutGrid = normalizeKey(String(sourceSlide?.layout_grid || sourceSlide?.layout || ""));
  const normalizedSubtype = normalizeSubtype(subtype || "content");
  const validLayoutTypes = new Set([
    "split_2",
    "asymmetric_2",
    "grid_2",
    "grid_3",
    "grid_4",
    "bento_5",
    "bento_6",
    "timeline",
  ]);
  if (normalizedSubtype === "timeline") return "timeline";
  if (normalizedSubtype === "image_showcase") return "image_showcase";
  if (validLayoutTypes.has(layoutGrid)) return layoutGrid;
  if (normalizedSubtype === "comparison" || normalizedSubtype === "mixed_media" || normalizedSubtype === "table") {
    return "grid_2";
  }
  if (normalizedSubtype === "data" || normalizedSubtype === "data_visualization") return "grid_3";
  return "grid_3";
}

function resolveRenderSlideTypeByTemplate(templateFamily) {
  const family = normalizeKey(String(templateFamily || ""));
  if (!family) return "";
  return normalizeKey(getTemplatePreferredLayout(family, "")) || "";
}

function buildContentRenderSlide(pageNumber, sourceSlide, subtype, title, bullets, templateFamily = "dashboard_dark") {
  let resolvedSubtype = subtype;
  if (deckArchetypeProfile === 'education_textbook' && templateFamily === 'education_textbook_light') {
    const archetypeKey = String(sourceSlide?.archetype || sourceSlide?.archetype_plan?.selected || '').trim().toLowerCase();
    if (archetypeKey === 'chart_dual_compare') resolvedSubtype = 'comparison';
    else if (archetypeKey === 'chart_single_focus') resolvedSubtype = 'content';
    else if (archetypeKey === 'process_flow_4step' || normalizeKey(sourceSlide?.layout_grid || '') === 'timeline') resolvedSubtype = 'timeline';
    else if (['mixed_media', 'image_showcase', 'data', 'data_visualization'].includes(resolvedSubtype)) resolvedSubtype = 'content';
  }
  const safeBullets = (bullets.length ? bullets : [title]).slice(0, 6);
  const actions = [];
  const templateProfiles = getTemplateProfiles(templateFamily);
  const prefersTemplateRenderer = hasTemplateContentRenderer(templateFamily);
  const lockTemplate = asBool(sourceSlide?.template_lock, false);
  const skipTemplateRenderer = asBool(sourceSlide?.__template_renderer_skipped, false);
  const layoutSource =
    prefersTemplateRenderer && lockTemplate && !skipTemplateRenderer
      ? { ...(sourceSlide || {}), layout_grid: "", layout: "" }
      : sourceSlide;
  const renderSlideType =
    (skipTemplateRenderer ? "" : resolveRenderSlideTypeByTemplate(templateFamily))
    || resolveContentRenderSlideType(layoutSource, resolvedSubtype);
  if (safeBullets.length) {
    actions.push({ type: "appear_items", items: safeBullets.slice(0, 4), startFrame: 24 });
  }
  const keyword = pickHighlightKeyword([title, ...safeBullets]);
  if (keyword) {
    actions.push({ type: "highlight", keyword, startFrame: 36 });
  }

  if (resolvedSubtype === "section") {
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

  if (resolvedSubtype === "timeline") {
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

  if (resolvedSubtype === "table") {
    const rows = buildTableRows(sourceSlide, safeBullets);
    return {
      ...renderIdentity(pageNumber, sourceSlide),
      page_number: pageNumber,
      slide_type: renderSlideType,
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

  if (resolvedSubtype === "comparison") {
    const { left, right } = splitComparison(safeBullets);
    return {
      ...renderIdentity(pageNumber, sourceSlide),
      page_number: pageNumber,
      slide_type: renderSlideType,
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

  if (resolvedSubtype === "mixed_media") {
    const lead = safeBullets[0] || title;
    const rest = safeBullets.slice(1);
    return {
      ...renderIdentity(pageNumber, sourceSlide),
      page_number: pageNumber,
      slide_type: renderSlideType,
      template_family: templateFamily,
      ...templateProfiles,
      svg_mode: svgModeEnabled ? "on" : "off",
      markdown: `# ${mdEscape(title)}\n<div class="grid-2">\n<div>\n- ${mdEscape(lead)}\n${rest.map((b) => `- ${mdEscape(b)}`).join("\n")}\n</div>\n<div class="card accent">\n<mark>Visual Focus</mark>\n</div>\n</div>`,
      script: asScriptLine(sourceSlide, title),
      actions: [
        { type: "appear_items", items: safeBullets.slice(0, 4), startFrame: 24 },
        { type: "zoom_in", region: "right", startFrame: 42 },
      ],
      narration_audio_url: asNarrationAudio(sourceSlide),
      duration: asDuration(sourceSlide, 7),
    };
  }

  if (resolvedSubtype === "image_showcase") {
    return {
      ...renderIdentity(pageNumber, sourceSlide),
      page_number: pageNumber,
      slide_type: "image_showcase",
      template_family: templateFamily,
      ...templateProfiles,
      svg_mode: svgModeEnabled ? "on" : "off",
      markdown: `# ${mdEscape(title)}\n<mark>${mdEscape(safeBullets[0] || title)}</mark>\n${safeBullets.slice(1).map((b) => `- ${mdEscape(b)}`).join("\n")}`,
      script: asScriptLine(sourceSlide, title),
      actions: [
        { type: "zoom_in", region: "center", startFrame: 20 },
        { type: "highlight", keyword, startFrame: 40 },
      ],
      narration_audio_url: asNarrationAudio(sourceSlide),
      duration: asDuration(sourceSlide, 7),
    };
  }

  if (resolvedSubtype === "data" || resolvedSubtype === "data_visualization") {
    const bars = extractChartSeries(sourceSlide);
    const dataLines = bars && bars.length
      ? bars.map((b) => `- ${mdEscape(b.label)}: <mark>${b.value}</mark>`)
      : safeBullets.map((b) => `- ${mdEscape(b)}`);
    return {
      ...renderIdentity(pageNumber, sourceSlide),
      page_number: pageNumber,
      slide_type: renderSlideType,
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
    slide_type: renderSlideType,
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
  if (String(sourceSlide?.deck_archetype_profile || "").trim().toLowerCase() === "education_textbook") {
    return false;
  }
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
  const slide = setSlideThemeContext(pres.addSlide(), theme);
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
      const activeTheme = slide?.__theme && typeof slide.__theme === "object" ? slide.__theme : theme;
      if (!Number.isFinite(Number(merged.margin)) || Number(merged.margin) < 0.05) merged.margin = 0.05;
      if (merged.fit === undefined && Number(merged.fontSize || 0) >= 10) {
        merged.fit = "shrink";
      }
      const fillColor = cleanHex(merged?.fill?.color || "", "");
      const bgColor = fillColor || cleanHex(activeTheme?.bg || "FFFFFF", "FFFFFF");
      if (!merged.color) {
        merged.color = fillColor
          ? pickReadableTextColorForFill(fillColor, activeTheme)
          : pickReadableTextColor(bgColor, "F8FAFC", "111827");
      } else {
        const chosenColor = cleanHex(merged.color, "");
        if (chosenColor && contrastRatio(chosenColor, bgColor) < 4.5) {
          merged.color = pickReadableTextColorForFill(bgColor, activeTheme);
        }
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
      normalizeKey(requestedStyle) === "auto"
        ? visualConfig.styleOverride
        : selectStyle(requestedStyle, deckStyleHint, topicText, disableLocalStyleRewrite)
    )
    : selectStyle(requestedStyle, deckStyleHint, topicText, disableLocalStyleRewrite);
  const paletteKey = visualConfig.enabled
    ? (
      visualConfig.enforcePreset && normalizeKey(effectiveRequestedPalette) === "auto"
        ? visualConfig.paletteOverride
        : selectPalette(effectiveRequestedPalette, topicText, disableLocalStyleRewrite)
    )
    : selectPalette(effectiveRequestedPalette, topicText, disableLocalStyleRewrite);
  const deckThemeRecipe = String(
    canonicalizeThemeRecipeFromCatalog(visualConfig.themeRecipe || requestedThemeRecipe || "auto"),
  ) || "consulting_clean";
  const deckTone = normalizeToneValue(visualConfig.tone || requestedTone || "auto");
  const resolveSlideThemeContext = (sourceSlide = {}) => {
    const slideRecipe = String(
      canonicalizeThemeRecipeFromCatalog(
        pick(sourceSlide || {}, ["theme_recipe", "themeRecipe"], "")
        || deckThemeRecipe,
      ),
    ) || deckThemeRecipe;
    const slideTone = normalizeToneValue(
      pick(sourceSlide || {}, ["tone", "theme_tone", "preferred_tone"], "")
      || deckTone,
    );
    return {
      paletteKey,
      themeRecipe: slideRecipe,
      tone: slideTone,
      surfaceProfile: visualConfig.surfaceProfile,
    };
  };
  const theme = buildTheme(resolveSlideThemeContext());
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
    return {
      pres,
      style,
      paletteKey,
      renderSlides,
      renderMode,
      visualConfig,
      themeRecipe: deckThemeRecipe,
      tone: String(theme?.tone || deckTone || "auto"),
    };
  }

  if (isPatchMode) {
    for (let i = 0; i < slides.length; i += 1) {
      const sourceSlide = slides[i];
      if (!isSlideInRetryScope(sourceSlide, i)) continue;
      const pageNumber = i + 1;
      const templateFamily = resolveSlideTemplateFamily(sourceSlide);
      const slideTheme = buildTheme(resolveSlideThemeContext(sourceSlide));
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
        const subtitle = resolveCoverSubtitle(title, sourceSlide, bullets, narration);
        const coverTemplate = normalizeTemplateFamily(resolveSlideTemplateFamily(sourceSlide), "cover", "hero_1");
        const coverTheme = buildTheme(resolveSlideThemeContext(sourceSlide));
        addCover(pres, title, subtitle, coverTheme, style, visualConfig, sourceSlide, coverTemplate);
        renderSlides.push(
          buildCoverRenderSlide(pageNumber, title, subtitle, style, paletteKey, sourceSlide, coverTemplate),
        );
        continue;
      }

      if (explicitType === "toc") {
        const tocTheme = buildTheme(resolveSlideThemeContext(sourceSlide));
        const tocSections = resolveTocSections(sourceSlide, slides, bullets);
        addToc(pres, tocSections, tocTheme, style, visualConfig, pageNumber, sourceSlide);
        renderSlides.push(buildTocRenderSlide(pageNumber, tocSections, sourceSlide));
        continue;
      }

      if (explicitType === "summary") {
        const summaryTemplate = normalizeTemplateFamily(
          resolveSlideTemplateFamily(sourceSlide),
          "summary",
          sourceSlide?.layout_grid || "hero_1",
        );
        const summaryTheme = buildTheme(resolveSlideThemeContext(sourceSlide));
        const summaryBullets = (bullets.length ? bullets : [narration || title]).slice(0, 5);
        addSummarySlide(pres, title, summaryBullets, pageNumber, summaryTheme, style, visualConfig, sourceSlide);
        renderSlides.push(buildSummaryRenderSlide(pageNumber, title, summaryBullets, sourceSlide, summaryTemplate));
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
    return {
      pres,
      style,
      paletteKey,
      renderSlides,
      renderMode,
      visualConfig,
      themeRecipe: deckThemeRecipe,
      tone: String(theme?.tone || deckTone || "auto"),
    };
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
    const layoutHintTypes = new Set(["split_2", "asymmetric_2", "grid_2", "grid_3", "grid_4", "bento_5", "bento_6"]);
    const explicitContentCandidates = [];
    for (let i = 0; i < slides.length; i += 1) {
      const sourceSlide = slides[i];
      const explicitType = normalizeKey(
        pick(sourceSlide, ["page_type", "pageType", "slide_type", "slideType", "subtype"], ""),
      );
      if (!explicitType || explicitType === "content" || layoutHintTypes.has(explicitType)) {
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
      const slideTheme = buildTheme(resolveSlideThemeContext(sourceSlide));
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
        const subtitle = resolveCoverSubtitle(title, sourceSlide, bullets, narration);
        const coverTemplate = normalizeTemplateFamily(resolveSlideTemplateFamily(sourceSlide), "cover", "hero_1");
        const coverTheme = buildTheme(resolveSlideThemeContext(sourceSlide));
        addCover(pres, title, subtitle, coverTheme, style, visualConfig, sourceSlide, coverTemplate);
        renderSlides.push(
          buildCoverRenderSlide(pageNumber, title, subtitle, style, paletteKey, sourceSlide, coverTemplate),
        );
        continue;
      }
      if (explicitType === "toc") {
        const tocTheme = buildTheme(resolveSlideThemeContext(sourceSlide));
        const tocSections = resolveTocSections(sourceSlide, slides, bullets);
        addToc(pres, tocSections, tocTheme, style, visualConfig, pageNumber, sourceSlide);
        renderSlides.push(buildTocRenderSlide(pageNumber, tocSections, sourceSlide));
        continue;
      }
      if (explicitType === "summary") {
        const summaryBullets = (bullets.length ? bullets : [narration || title]).slice(0, 5);
        const summaryTemplate = normalizeTemplateFamily(
          resolveSlideTemplateFamily(sourceSlide),
          "summary",
          sourceSlide?.layout_grid || "hero_1",
        );
        const summaryTheme = buildTheme(resolveSlideThemeContext(sourceSlide));
        addSummarySlide(pres, title, summaryBullets, pageNumber, summaryTheme, style, visualConfig, sourceSlide);
        renderSlides.push(buildSummaryRenderSlide(pageNumber, title, summaryBullets, sourceSlide, summaryTemplate));
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
        explicitType && explicitType !== "content" && !layoutHintTypes.has(explicitType)
          ? normalizeSubtype(explicitType)
          : (explicitSubtypeByIndex.get(i) || inferSubtype(sourceSlide) || "content");
      addContentSlide(pres, sourceSlide, pageNumber, slideTheme, style, visualConfig, subtype, templateFamily);
      renderSlides.push(buildContentRenderSlide(pageNumber, sourceSlide, subtype, title, bullets, templateFamily));
    }
    return {
      pres,
      style,
      paletteKey,
      renderSlides,
      renderMode,
      visualConfig,
      themeRecipe: deckThemeRecipe,
      tone: String(theme?.tone || deckTone || "auto"),
    };
  }

  const firstTitle = htmlToText(String(pick(slides[0], ["title"], deckTitle)));
  const coverSubtitle = resolveCoverSubtitle(deckTitle, slides[0], collectBullets(slides[0], ""), firstTitle);
  const firstCoverTemplate = normalizeTemplateFamily(resolveSlideTemplateFamily(slides[0]), "cover", "hero_1");
  const firstCoverTheme = buildTheme(resolveSlideThemeContext(slides[0]));
  addCover(pres, deckTitle, coverSubtitle, firstCoverTheme, style, visualConfig, slides[0], firstCoverTemplate);
  renderSlides.push(
    buildCoverRenderSlide(1, deckTitle, coverSubtitle, style, paletteKey, slides[0], firstCoverTemplate),
  );

  const explicitTocSlide = slides.length > 1 && resolveExplicitSlideType(slides[1]) === "toc" ? slides[1] : null;
  const explicitSummarySlide = slides.length > 1 && resolveExplicitSlideType(slides[slides.length - 1]) === "summary"
    ? slides[slides.length - 1]
    : null;
  const insertedTocCount = explicitTocSlide ? 0 : 1;
  const contentCandidates = slides.filter((slide, idx) => {
    if (idx === 0) return false;
    if (explicitSummarySlide && idx === slides.length - 1) return false;
    const slideType = resolveExplicitSlideType(slide);
    return !["toc", "summary"].includes(slideType);
  });
  const tocSourceSlide = explicitTocSlide || slides[1] || slides[0];
  const tocSections = resolveTocSections(tocSourceSlide || slides[0], contentCandidates, collectBullets(tocSourceSlide || {}, ""));
  const tocTheme = buildTheme(resolveSlideThemeContext(tocSourceSlide || slides[0]));
  addToc(pres, tocSections, tocTheme, style, visualConfig, 2, tocSourceSlide);
  renderSlides.push(buildTocRenderSlide(2, tocSections, slides[1] || slides[0]));

  const middleStartIndex = explicitTocSlide ? 2 : 1;
  const middleEndIndex = explicitSummarySlide ? slides.length - 1 : slides.length;
  const middleSlides = slides.slice(middleStartIndex, Math.max(middleStartIndex, middleEndIndex));
  const plannedSubtypes = planDeckSubtypes(middleSlides);

  for (let i = middleStartIndex; i < middleEndIndex; i += 1) {
    const sourceSlide = slides[i];
    const templateFamily = resolveSlideTemplateFamily(sourceSlide);
    const slideTheme = buildTheme(resolveSlideThemeContext(sourceSlide));
    const pageNumber = i + 1 + insertedTocCount;
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

    const title = htmlToText(String(pick(sourceSlide, ["title"], `Slide ${i + 1}`))) || `Slide ${i + 1}`;
    const narration = htmlToText(String(pick(sourceSlide, ["narration", "speaker_notes", "speakerNotes"], "")));
    const bullets = collectBullets(sourceSlide, narration);
    const subtype = plannedSubtypes[i - middleStartIndex] || inferSubtype(sourceSlide);
    addContentSlide(pres, sourceSlide, pageNumber, slideTheme, style, visualConfig, subtype, templateFamily);
    renderSlides.push(buildContentRenderSlide(pageNumber, sourceSlide, subtype, title, bullets, templateFamily));
  }

  const lastSlide = explicitSummarySlide || slides[slides.length - 1];
  const summaryTitle = htmlToText(String(pick(lastSlide, ["title"], "Summary"))) || "Summary";
  const explicitSummaryBullets = collectBullets(lastSlide, "");
  const allBullets = slides.flatMap((s) => collectBullets(s, ""));
  const summaryBullets = (explicitSummaryBullets.length
    ? explicitSummaryBullets
    : Array.from(new Set(allBullets))).slice(0, 5);
  const lastSummaryTemplate = normalizeTemplateFamily(
    resolveSlideTemplateFamily(lastSlide),
    "summary",
    lastSlide?.layout_grid || "hero_1",
  );
  const lastSummaryTheme = buildTheme(resolveSlideThemeContext(lastSlide));
  addSummarySlide(
    pres,
    summaryTitle,
    summaryBullets.length ? summaryBullets : [summaryTitle],
    (explicitSummarySlide ? slides.length + insertedTocCount : slides.length + insertedTocCount + 1),
    lastSummaryTheme,
    style,
    visualConfig,
    lastSlide,
  );
  renderSlides.push(
    buildSummaryRenderSlide(
      (explicitSummarySlide ? slides.length + insertedTocCount : slides.length + insertedTocCount + 1),
      summaryTitle,
      summaryBullets,
      lastSlide,
      lastSummaryTemplate,
    ),
  );

  return {
    pres,
    style,
    paletteKey,
    renderSlides,
    renderMode,
    visualConfig,
    themeRecipe: deckThemeRecipe,
    tone: String(theme?.tone || deckTone || "auto"),
  };
}

async function main() {
  const {
    pres,
    style,
    paletteKey,
    renderSlides,
    renderMode,
    visualConfig,
    themeRecipe,
    tone,
  } = buildDeck();
  const templateRendererSummary = summarizeTemplateRendererDiagnostics(renderSlides);
  const effectiveDeckTemplate = inferDeckTemplateFamily(slides);
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
          theme_recipe: String(themeRecipe || visualConfig?.themeRecipe || "auto"),
          tone: String(tone || visualConfig?.tone || "auto"),
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
          design_spec: designSpec,
          design_decision_v1: designDecision,
          template_renderer_summary: templateRendererSummary,
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
      theme_recipe: String(themeRecipe || visualConfig?.themeRecipe || "auto"),
      tone: String(tone || visualConfig?.tone || "auto"),
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
      design_decision_attached: Boolean(designDecision && Object.keys(designDecision).length > 0),
      template_renderer_summary: templateRendererSummary,
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
