/**
 * Canonical contract primitives for MiniMax official PPTX skill compatibility.
 */

export const OFFICIAL_PAGE_TYPES = Object.freeze([
  "cover",
  "toc",
  "section-divider",
  "content",
  "summary",
]);

export const OFFICIAL_GENERATOR_MODES = Object.freeze([
  "official",
  "legacy",
]);

export const OFFICIAL_RETRY_SCOPES = Object.freeze([
  "deck",
  "slide",
  "block",
]);

export const OFFICIAL_BLOCK_TYPES = Object.freeze([
  "text",
  "title",
  "subtitle",
  "body",
  "list",
  "quote",
  "icon_text",
  "image",
  "chart",
  "table",
  "kpi",
  "workflow",
  "diagram",
  "shape",
]);

export const OFFICIAL_LAYOUT_GRIDS = Object.freeze([
  "split_2",
  "asymmetric_2",
  "grid_2",
  "grid_3",
  "grid_4",
  "bento_5",
  "bento_6",
  "timeline",
  "hero_1",
]);

export const DEFAULT_OFFICIAL_THEME = Object.freeze({
  primary: "2B2D42",
  secondary: "8D99AE",
  accent: "EF233C",
  light: "EDF2F4",
  bg: "FFFFFF",
});

export function normalizeHexNoHash(value, fallback) {
  const raw = String(value || "").replace(/^#/, "").trim();
  if (/^[0-9a-fA-F]{6}$/.test(raw)) return raw.toUpperCase();
  return String(fallback || "FFFFFF").replace(/^#/, "").toUpperCase();
}

export function normalizeGeneratorMode(value, fallback = "official") {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "legacy") return "legacy";
  if (normalized === "official") return "official";
  return normalizeGeneratorMode(fallback, "official");
}

export function normalizeRetryScope(value, fallback = "deck") {
  const normalized = String(value || "").trim().toLowerCase().replace(/[_\s]+/g, "-");
  if (OFFICIAL_RETRY_SCOPES.includes(normalized)) return normalized;
  const fallbackNormalized = String(fallback || "deck").trim().toLowerCase();
  return OFFICIAL_RETRY_SCOPES.includes(fallbackNormalized) ? fallbackNormalized : "deck";
}

export function normalizePageType(value, fallback = "content") {
  const normalized = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[_\s]+/g, "-");
  if (OFFICIAL_PAGE_TYPES.includes(normalized)) return normalized;
  if (normalized === "section" || normalized === "divider") return "section-divider";
  if (normalized === "table-of-contents") return "toc";
  return fallback;
}

export function normalizeTheme(theme) {
  const source = theme && typeof theme === "object" ? theme : {};
  return {
    primary: normalizeHexNoHash(source.primary, DEFAULT_OFFICIAL_THEME.primary),
    secondary: normalizeHexNoHash(source.secondary, DEFAULT_OFFICIAL_THEME.secondary),
    accent: normalizeHexNoHash(source.accent, DEFAULT_OFFICIAL_THEME.accent),
    light: normalizeHexNoHash(source.light, DEFAULT_OFFICIAL_THEME.light),
    bg: normalizeHexNoHash(source.bg, DEFAULT_OFFICIAL_THEME.bg),
  };
}

export function normalizeLayoutGrid(value, fallback = "") {
  const normalized = String(value || "").trim().toLowerCase().replace(/[\s-]+/g, "_");
  if (OFFICIAL_LAYOUT_GRIDS.includes(normalized)) return normalized;
  return String(fallback || "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function normalizeBlockType(value, fallback = "text") {
  const normalized = String(value || "").trim().toLowerCase().replace(/[_\s]+/g, "_");
  if (OFFICIAL_BLOCK_TYPES.includes(normalized)) return normalized;
  const fallbackType = String(fallback || "text").trim().toLowerCase();
  return OFFICIAL_BLOCK_TYPES.includes(fallbackType) ? fallbackType : "text";
}

function normalizeText(value, fallback = "") {
  const text = String(value ?? fallback ?? "").trim();
  return text;
}

function sanitizeBlocks(blocks, slideId) {
  const source = Array.isArray(blocks) ? blocks : [];
  const out = [];
  for (let i = 0; i < source.length; i += 1) {
    const block = source[i];
    if (!block || typeof block !== "object") continue;
    const content = normalizeText(block.content);
    if (!content) continue;
    const blockId = normalizeText(block.block_id || block.id || `${slideId}-block-${i + 1}`);
    out.push({
      block_id: blockId || `${slideId}-block-${i + 1}`,
      type: normalizeBlockType(block.type, "text"),
      content,
      ...(block.data && typeof block.data === "object" ? { data: block.data } : {}),
    });
  }
  return out;
}

export function validateOfficialInputContract(input, options = {}) {
  const strict = Boolean(options?.strict);
  const errors = [];
  const source = input && typeof input === "object" ? input : {};
  const slides = Array.isArray(source.slides) ? source.slides : [];

  const normalized = {
    deck_id: normalizeText(source.deck_id) || undefined,
    title: normalizeText(source.title, "Presentation") || "Presentation",
    author: normalizeText(source.author, "AutoViralVid") || "AutoViralVid",
    generator_mode: normalizeGeneratorMode(source.generator_mode, "official"),
    retry_scope: normalizeRetryScope(source.retry_scope, "deck"),
    original_style: Boolean(source.original_style ?? false),
    disable_local_style_rewrite: Boolean(source.disable_local_style_rewrite ?? false),
    theme: normalizeTheme(source.theme || {}),
    slides: [],
  };

  if (!slides.length) errors.push("slides must contain at least one slide");
  if (!normalized.title) errors.push("title is required");
  if (!normalized.author) errors.push("author is required");

  for (let index = 0; index < slides.length; index += 1) {
    const slide = slides[index];
    if (!slide || typeof slide !== "object") {
      errors.push(`slides[${index}] must be an object`);
      continue;
    }
    const slideId = normalizeText(slide.slide_id || slide.id || `slide-${index + 1}`) || `slide-${index + 1}`;
    const pageType = normalizePageType(slide.page_type || slide.slide_type || "", "");
    const layoutGrid = normalizeLayoutGrid(slide.layout_grid || slide.layout || "", "");
    const subtype = normalizeText(slide.subtype || slide.slide_type || "", "");
    const title = normalizeText(slide.title || `Slide ${index + 1}`) || `Slide ${index + 1}`;
    const retryScope = normalizeRetryScope(slide.retry_scope || normalized.retry_scope, "slide");
    const blocks = sanitizeBlocks(slide.blocks, slideId);

    if (!pageType) errors.push(`slides[${index}].page_type is required`);
    if (!title) errors.push(`slides[${index}].title is required`);
    if (strict && blocks.length === 0 && pageType === "content") {
      errors.push(`slides[${index}] content slide must contain at least one block`);
    }

    normalized.slides.push({
      slide_id: slideId,
      page_type: pageType || "content",
      ...(layoutGrid ? { layout_grid: layoutGrid } : {}),
      ...(subtype ? { subtype } : {}),
      title,
      blocks,
      retry_scope: retryScope,
    });
  }

  return {
    ok: errors.length === 0,
    errors,
    normalized,
  };
}
