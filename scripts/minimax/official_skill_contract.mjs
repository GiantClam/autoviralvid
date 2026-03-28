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
