import { defaultTemplateId, getTemplateCatalog } from "./templates/template-catalog.mjs";

export const TEMPLATE_FAMILIES = [
  "hero_dark",
  "hero_tech_cover",
  "bento_2x2_dark",
  "bento_mosaic_dark",
  "split_media_dark",
  "dashboard_dark",
  "architecture_dark_panel",
  "ecosystem_orange_dark",
  "neural_blueprint_light",
  "ops_lifecycle_light",
  "consulting_warm_light",
  "kpi_dashboard_dark",
  "image_showcase_light",
  "process_flow_dark",
  "comparison_cards_light",
  "quote_hero_dark",
];

const LIGHT_TEMPLATE_FAMILIES = new Set([
  "neural_blueprint_light",
  "ops_lifecycle_light",
  "consulting_warm_light",
  "image_showcase_light",
  "comparison_cards_light",
]);

function defaultTemplateFamilyForLayout(layoutGrid = "") {
  const catalog = getTemplateCatalog();
  const grid = String(layoutGrid || "").trim().toLowerCase();
  const candidate = String(catalog.layout_defaults?.[grid] || defaultTemplateId()).trim().toLowerCase();
  if (TEMPLATE_FAMILIES.includes(candidate)) return candidate;
  const fallback = String(defaultTemplateId() || "").trim().toLowerCase();
  return TEMPLATE_FAMILIES.includes(fallback) ? fallback : "consulting_warm_light";
}

export const DARK_VISUAL_TOKENS = {
  colors: {
    bg: "060B17",
    surface: "0D1630",
    surfaceAlt: "121F3D",
    border: "1E335E",
    primary: "2F7BFF",
    secondary: "12B6F5",
    accent: "18E0D1",
    text: "E8F0FF",
    textMuted: "95A8CC",
    success: "22C55E",
    danger: "EF4444",
  },
  glow: {
    soft: 0.08,
    medium: 0.14,
  },
  radius: {
    sm: 0.06,
    md: 0.12,
    lg: 0.2,
  },
  border: {
    thin: 0.6,
    strong: 1,
  },
  spacing: {
    xs: 0.08,
    sm: 0.15,
    md: 0.25,
    lg: 0.35,
    xl: 0.5,
  },
};

function cleanHex(value, fallback = "000000") {
  const v = String(value || "").replace("#", "").trim();
  return /^[0-9a-fA-F]{6}$/.test(v) ? v.toUpperCase() : fallback;
}

function hexToRgb(hex) {
  const normalized = cleanHex(hex, "000000");
  return {
    r: parseInt(normalized.slice(0, 2), 16),
    g: parseInt(normalized.slice(2, 4), 16),
    b: parseInt(normalized.slice(4, 6), 16),
  };
}

function relativeLuminance(hex) {
  const { r, g, b } = hexToRgb(hex);
  const convert = (v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  const lr = convert(r);
  const lg = convert(g);
  const lb = convert(b);
  return (0.2126 * lr) + (0.7152 * lg) + (0.0722 * lb);
}

function contrastRatio(fgHex, bgHex) {
  const l1 = relativeLuminance(fgHex);
  const l2 = relativeLuminance(bgHex);
  const bright = Math.max(l1, l2);
  const dark = Math.min(l1, l2);
  return (bright + 0.05) / (dark + 0.05);
}

function pickReadableTextColor(preferredHex, bgHex, minContrast = 4.5) {
  const preferred = cleanHex(preferredHex, "FFFFFF");
  const bg = cleanHex(bgHex, "000000");
  if (contrastRatio(preferred, bg) >= minContrast) return preferred;
  const darkCandidate = "0F172A";
  const lightCandidate = "F8FAFC";
  const darkRatio = contrastRatio(darkCandidate, bg);
  const lightRatio = contrastRatio(lightCandidate, bg);
  return darkRatio >= lightRatio ? darkCandidate : lightCandidate;
}

function mixHex(baseHex, overlayHex, ratio = 0.5) {
  const base = cleanHex(baseHex, "000000");
  const mix = cleanHex(overlayHex, "000000");
  const alpha = Math.max(0, Math.min(1, Number(ratio) || 0));
  const toChannel = (offset) => {
    const a = parseInt(base.slice(offset, offset + 2), 16);
    const b = parseInt(mix.slice(offset, offset + 2), 16);
    return Math.round(a * (1 - alpha) + b * alpha).toString(16).padStart(2, "0").toUpperCase();
  };
  return `${toChannel(0)}${toChannel(2)}${toChannel(4)}`;
}

function applyContrastGuards(theme = {}) {
  const next = { ...theme };
  const bgCandidates = [next.cardBg, next.cardAltBg, next.bg].filter(Boolean).map((v) => cleanHex(v, "FFFFFF"));
  const allBackgrounds = bgCandidates.length ? bgCandidates : [cleanHex(next.bg, "FFFFFF")];
  const evaluateCandidate = (candidateHex, minContrast) => {
    const candidate = cleanHex(candidateHex, "0F172A");
    const ratios = allBackgrounds.map((bg) => contrastRatio(candidate, bg));
    const worst = ratios.length ? Math.min(...ratios) : 0;
    const pass = ratios.every((ratio) => ratio >= minContrast);
    return { candidate, worst, pass };
  };
  const pickBestAcrossBackgrounds = (preferredHex, minContrast, fallbackPool) => {
    const pool = [preferredHex, ...fallbackPool].map((v) => cleanHex(v, "0F172A"));
    let best = evaluateCandidate(pool[0], minContrast);
    for (const item of pool) {
      const result = evaluateCandidate(item, minContrast);
      if (result.pass && !best.pass) {
        best = result;
        continue;
      }
      if (result.pass === best.pass && result.worst > best.worst) {
        best = result;
      }
    }
    return best.candidate;
  };

  next.darkText = pickBestAcrossBackgrounds(
    next.darkText || "0F172A",
    4.5,
    ["0F172A", "17243D", "F8FAFC", "E8F0FF"],
  );
  next.mutedText = pickBestAcrossBackgrounds(
    next.mutedText || next.darkText || "475569",
    4.5,
    ["475569", "64748B", "6B7C96", next.darkText || "0F172A", "F8FAFC"],
  );
  // Accent/primary are frequently reused as heading colors in templates.
  // Keep them AA-safe across card/background surfaces to prevent subtle low-contrast text.
  next.primary = pickBestAcrossBackgrounds(
    next.primary || next.darkText || "2F67E8",
    4.5,
    [next.darkText || "0F172A", "2F67E8", "F8FAFC", "17243D"],
  );
  next.accent = pickBestAcrossBackgrounds(
    next.accent || next.primary || next.darkText || "2F67E8",
    4.5,
    [next.primary || "2F67E8", next.darkText || "0F172A", "F8FAFC", "17243D"],
  );
  next.accentStrong = pickBestAcrossBackgrounds(
    next.accentStrong || next.accent || next.primary || next.darkText || "2F67E8",
    4.5,
    [next.accent || "2F67E8", next.primary || "2F67E8", next.darkText || "0F172A", "F8FAFC"],
  );
  return next;
}

export function normalizeTemplateFamily(input, slideType, layoutGrid) {
  const requested = String(input || "").trim().toLowerCase();
  if (TEMPLATE_FAMILIES.includes(requested)) return requested;

  const st = String(slideType || "").trim().toLowerCase();
  const grid = String(layoutGrid || "").trim().toLowerCase();

  if (st === "cover" || st === "hero_1") return "hero_tech_cover";
  if (st === "toc") return "hero_dark";
  if (st === "summary" || st === "divider") return "quote_hero_dark";
  if (grid === "hero_1") return "hero_dark";
  if (grid) return defaultTemplateFamilyForLayout(grid);
  return "consulting_warm_light";
}

export function buildDarkTheme(baseTheme = {}, templateFamily = "dashboard_dark") {
  const t = DARK_VISUAL_TOKENS;
  const allowTemplateChroma = String(process.env.PPT_TEMPLATE_CHROMA_ENABLED || "false").trim().toLowerCase()
    === "true";
  if (LIGHT_TEMPLATE_FAMILIES.has(templateFamily)) {
    const isWarm = templateFamily === "consulting_warm_light";
    return applyContrastGuards({
      ...baseTheme,
      bg: isWarm ? "F7F3EE" : "F4F7FC",
      primary: isWarm ? "7A2E1F" : (baseTheme.primary || "2F67E8"),
      secondary: isWarm ? "A14A32" : (baseTheme.secondary || "4A84FF"),
      accent: isWarm ? "D9B08C" : (baseTheme.accent || "5E9BFF"),
      accentStrong: isWarm ? "9B3B2E" : (baseTheme.accentStrong || "2F67E8"),
      accentSoft: isWarm ? "EFE3D7" : (baseTheme.accentSoft || "E9F0FC"),
      light: isWarm ? "DEC9B7" : "CFDAEC",
      white: "FFFFFF",
      darkText: isWarm ? "3A2A23" : "0F1E35",
      mutedText: isWarm ? "7F6B5D" : "6B7C96",
      cardBg: "FFFFFF",
      cardAltBg: isWarm ? "F6ECE2" : "EEF3FB",
      borderColor: isWarm ? "D8BFAA" : "CFDAEC",
      success: "22C55E",
      danger: "EF4444",
      template_family: templateFamily,
    });
  }

  if (allowTemplateChroma && templateFamily === "ecosystem_orange_dark") {
    return applyContrastGuards({
      ...baseTheme,
      bg: "090C13",
      primary: "FF8A00",
      secondary: "FFB347",
      accent: "FF8A00",
      accentStrong: "FF8A00",
      accentSoft: "3A250B",
      light: "4C2E11",
      white: "111722",
      darkText: "F8FAFC",
      mutedText: "C9D2E3",
      cardBg: "101621",
      cardAltBg: "161D2B",
      borderColor: "3E2A12",
      success: "22C55E",
      danger: "EF4444",
      template_family: templateFamily,
    });
  }

  if (allowTemplateChroma && templateFamily === "hero_tech_cover") {
    return applyContrastGuards({
      ...baseTheme,
      bg: "070B1A",
      primary: "2B5FE8",
      secondary: "4A84FF",
      accent: "7CB5FF",
      accentStrong: "6CA3FF",
      accentSoft: "1A2748",
      light: "273A66",
      white: "101A33",
      darkText: "F2F7FF",
      mutedText: "A6B8D8",
      cardBg: "0E1630",
      cardAltBg: "121E3D",
      borderColor: "2A3F6E",
      success: "22C55E",
      danger: "EF4444",
      template_family: templateFamily,
    });
  }

  if (allowTemplateChroma && templateFamily === "bento_mosaic_dark") {
    return applyContrastGuards({
      ...baseTheme,
      bg: "06070A",
      primary: "6E7BFF",
      secondary: "8E9BFF",
      accent: "E88DFF",
      accentStrong: "58E0FF",
      accentSoft: "1A1D2C",
      light: "2A2D3F",
      white: "0F1118",
      darkText: "F8FAFC",
      mutedText: "B8C3D9",
      cardBg: "10131C",
      cardAltBg: "151A28",
      borderColor: "2A2F3F",
      success: "22C55E",
      danger: "EF4444",
      template_family: templateFamily,
    });
  }

  const blended = {
    ...baseTheme,
    // Keep palette hue while darkening, instead of flattening all dark families to one black.
    bg: mixHex(baseTheme.bg || t.colors.bg, t.colors.bg, 0.42),
    primary: baseTheme.primary || t.colors.primary,
    secondary: baseTheme.secondary || t.colors.secondary,
    accent: baseTheme.accent || t.colors.accent,
    accentStrong: baseTheme.accentStrong || t.colors.secondary,
    accentSoft: mixHex(baseTheme.accentSoft || baseTheme.accent || t.colors.surfaceAlt, t.colors.bg, 0.35),
    light: t.colors.border,
    white: mixHex(baseTheme.white || t.colors.surfaceAlt, t.colors.bg, 0.18),
    darkText: t.colors.text,
    mutedText: t.colors.textMuted,
    cardBg: mixHex(baseTheme.bg || t.colors.surface, t.colors.surface, 0.55),
    cardAltBg: mixHex(baseTheme.bg || t.colors.surfaceAlt, t.colors.surfaceAlt, 0.45),
    borderColor: t.colors.border,
    success: t.colors.success,
    danger: t.colors.danger,
    template_family: templateFamily,
  };
  return applyContrastGuards(blended);
}
