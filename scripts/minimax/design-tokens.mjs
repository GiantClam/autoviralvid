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
];

const LIGHT_TEMPLATE_FAMILIES = new Set([
  "neural_blueprint_light",
  "ops_lifecycle_light",
  "consulting_warm_light",
]);

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

export function normalizeTemplateFamily(input, slideType, layoutGrid) {
  const requested = String(input || "").trim().toLowerCase();
  if (TEMPLATE_FAMILIES.includes(requested)) return requested;

  const st = String(slideType || "").trim().toLowerCase();
  const grid = String(layoutGrid || "").trim().toLowerCase();

  if (st === "cover" || grid === "hero_1") return "hero_tech_cover";
  if (st === "summary") return "hero_dark";
  if (grid === "split_2" || grid === "asymmetric_2") return "architecture_dark_panel";
  if (grid === "grid_4") return "neural_blueprint_light";
  if (grid === "timeline") return "ops_lifecycle_light";
  if (grid === "bento_5") return "bento_mosaic_dark";
  if (grid === "bento_6") return "dashboard_dark";
  return "dashboard_dark";
}

export function buildDarkTheme(baseTheme = {}, templateFamily = "dashboard_dark") {
  const t = DARK_VISUAL_TOKENS;
  if (LIGHT_TEMPLATE_FAMILIES.has(templateFamily)) {
    const isWarm = templateFamily === "consulting_warm_light";
    return {
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
    };
  }

  if (templateFamily === "ecosystem_orange_dark") {
    return {
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
    };
  }

  if (templateFamily === "hero_tech_cover") {
    return {
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
    };
  }

  if (templateFamily === "bento_mosaic_dark") {
    return {
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
    };
  }

  const blended = {
    ...baseTheme,
    bg: t.colors.bg,
    primary: baseTheme.primary || t.colors.primary,
    secondary: baseTheme.secondary || t.colors.secondary,
    accent: baseTheme.accent || t.colors.accent,
    accentStrong: baseTheme.accentStrong || t.colors.secondary,
    accentSoft: baseTheme.accentSoft || t.colors.surfaceAlt,
    light: t.colors.border,
    white: t.colors.surfaceAlt,
    darkText: t.colors.text,
    mutedText: t.colors.textMuted,
    cardBg: t.colors.surface,
    cardAltBg: t.colors.surfaceAlt,
    borderColor: t.colors.border,
    success: t.colors.success,
    danger: t.colors.danger,
    template_family: templateFamily,
  };
  return blended;
}
