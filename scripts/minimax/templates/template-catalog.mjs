import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const CATALOG_PATH = path.join(__dirname, "template-catalog.json");

let _cachedCatalog = null;
const LAYOUT_KEYS = new Set([
  "hero_1",
  "split_2",
  "asymmetric_2",
  "grid_2",
  "grid_3",
  "grid_4",
  "bento_5",
  "bento_6",
  "timeline",
]);

const SKILL_LAYOUT_PREFERENCES = {
  cover_default: ["hero_1"],
  cover_storytelling: ["hero_1"],
  bento_general: ["grid_4", "grid_3", "bento_5", "bento_6"],
  bento_showcase: ["bento_5", "bento_6", "grid_4"],
  workflow_blueprint: ["grid_4", "split_2", "asymmetric_2"],
  ops_lifecycle: ["timeline", "grid_3", "split_2"],
  dashboard_data: ["grid_3", "grid_4", "bento_6"],
  comparison_general: ["split_2", "asymmetric_2", "grid_3"],
  architecture_explainer: ["split_2", "asymmetric_2", "grid_3"],
  ecosystem_diagram: ["grid_3", "grid_4", "split_2"],
  consulting_recommendation: ["split_2", "grid_3", "asymmetric_2"],
};

function normalizeKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function normalizeLayoutList(value) {
  const list = Array.isArray(value) ? value : [];
  const out = [];
  const seen = new Set();
  for (const item of list) {
    const key = normalizeKey(item);
    if (!key || seen.has(key) || !LAYOUT_KEYS.has(key)) continue;
    seen.add(key);
    out.push(key);
  }
  return out;
}

function normalizeObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function normalizeThemeRecipes(value) {
  const raw = normalizeObject(value);
  const out = {};
  for (const [key, item] of Object.entries(raw)) {
    const normalizedKey = normalizeKey(key);
    if (!normalizedKey) continue;
    const recipe = normalizeObject(item);
    out[normalizedKey] = {
      style_variant: normalizeKey(recipe.style_variant || "soft") || "soft",
      backdrop: normalizeKey(recipe.backdrop || "minimal-grid") || "minimal-grid",
      tone: normalizeKey(recipe.tone || "auto"),
      surface_profile: normalizeKey(recipe.surface_profile || "clean") || "clean",
    };
  }
  return out;
}

function loadCatalog() {
  if (_cachedCatalog) return _cachedCatalog;
  const raw = readFileSync(CATALOG_PATH, "utf-8");
  const parsed = JSON.parse(raw);
  _cachedCatalog = {
    default_template_id: normalizeKey(parsed.default_template_id || "consulting_warm_light") || "consulting_warm_light",
    default_palette_key: normalizeKey(parsed.default_palette_key || "business_authority") || "business_authority",
    default_theme_recipe: normalizeKey(parsed.default_theme_recipe || "consulting_clean") || "consulting_clean",
    layout_defaults: normalizeObject(parsed.layout_defaults),
    subtype_overrides: normalizeObject(parsed.subtype_overrides),
    palettes: normalizeObject(parsed.palettes),
    palette_aliases: normalizeObject(parsed.palette_aliases),
    palette_keywords: normalizeObject(parsed.palette_keywords),
    theme_recipes: normalizeThemeRecipes(parsed.theme_recipes),
    keyword_rules: Array.isArray(parsed.keyword_rules) ? parsed.keyword_rules : [],
    contract_profiles: normalizeObject(parsed.contract_profiles),
    quality_profiles: normalizeObject(parsed.quality_profiles),
    route_policies: normalizeObject(parsed.route_policies),
    templates: normalizeObject(parsed.templates),
  };
  return _cachedCatalog;
}

export function getTemplateCatalog() {
  return loadCatalog();
}

export function listPaletteKeys() {
  return Object.keys(loadCatalog().palettes || {})
    .map((item) => normalizeKey(item))
    .filter(Boolean);
}

export function canonicalizePaletteKey(value, topicText = "") {
  const catalog = loadCatalog();
  const normalized = normalizeKey(value || "");
  const palettes = catalog.palettes || {};
  const aliases = catalog.palette_aliases || {};
  const hasPalette = (key) => Boolean(key && Object.prototype.hasOwnProperty.call(palettes, key));
  if (!normalized || normalized === "auto") return "auto";
  if (hasPalette(normalized)) return normalized;
  const aliasTarget = normalizeKey(aliases?.[normalized] || "");
  if (hasPalette(aliasTarget)) return aliasTarget;

  const blob = String(topicText || "").toLowerCase();
  for (const [pattern, palette] of Object.entries(catalog.palette_keywords || {})) {
    if (!pattern || !palette) continue;
    try {
      if (new RegExp(String(pattern), "i").test(blob)) {
        const normalizedPalette = normalizeKey(palette);
        if (hasPalette(normalizedPalette)) return normalizedPalette;
      }
    } catch {
      // ignore invalid regex in user-customized catalog
    }
  }
  const fallback = normalizeKey(catalog.default_palette_key || "business_authority");
  return hasPalette(fallback) ? fallback : "business_authority";
}

export function listThemeRecipeKeys() {
  return Object.keys(loadCatalog().theme_recipes || {})
    .map((item) => normalizeKey(item))
    .filter(Boolean);
}

export function canonicalizeThemeRecipe(value) {
  const catalog = loadCatalog();
  const recipes = catalog.theme_recipes || {};
  const normalized = normalizeKey(value || "");
  if (!normalized || normalized === "auto") return "auto";
  if (Object.prototype.hasOwnProperty.call(recipes, normalized)) return normalized;
  const aliases = {
    classroom: "classroom_soft",
    education: "classroom_soft",
    consulting: "consulting_clean",
    executive_brief: "consulting_clean",
    premium_light: "consulting_clean",
    editorial: "editorial_magazine",
    magazine: "editorial_magazine",
    tech: "tech_cinematic",
    tech_cinematic: "tech_cinematic",
    energetic: "energetic_campaign",
    campaign: "energetic_campaign",
  };
  const alias = normalizeKey(aliases[normalized] || "");
  if (alias && Object.prototype.hasOwnProperty.call(recipes, alias)) return alias;
  const fallback = normalizeKey(catalog.default_theme_recipe || "consulting_clean");
  return Object.prototype.hasOwnProperty.call(recipes, fallback) ? fallback : "consulting_clean";
}

export function getThemeRecipe(recipeKey) {
  const catalog = loadCatalog();
  const recipes = catalog.theme_recipes || {};
  const key = canonicalizeThemeRecipe(recipeKey);
  const resolved = key === "auto"
    ? canonicalizeThemeRecipe(catalog.default_theme_recipe || "consulting_clean")
    : key;
  return {
    id: resolved,
    ...(recipes[resolved] || {
      style_variant: "soft",
      backdrop: "minimal-grid",
      tone: "auto",
      surface_profile: "clean",
    }),
  };
}

export function listTemplateIds() {
  return Object.keys(loadCatalog().templates);
}

export function defaultTemplateId() {
  const catalog = loadCatalog();
  const templateIds = Object.keys(catalog.templates || {});
  const requested = normalizeKey(catalog.default_template_id || "");
  if (requested && templateIds.includes(requested)) return requested;
  if (templateIds.includes("consulting_warm_light")) return "consulting_warm_light";
  if (templateIds.includes("dashboard_dark")) return "dashboard_dark";
  return templateIds[0] || "consulting_warm_light";
}

export function getTemplateField(templateId, field, fallback = "") {
  const templates = loadCatalog().templates || {};
  const key = String(templateId || "").trim().toLowerCase();
  const template = key && typeof templates[key] === "object" ? templates[key] : {};
  const value = template?.[field];
  return value === undefined || value === null || value === "" ? fallback : value;
}

export function getTemplateSupportedLayouts(templateId) {
  const capabilities = getTemplateField(templateId, "capabilities", {});
  return normalizeLayoutList(capabilities?.supported_layouts);
}

export function getTemplatePreferredLayout(templateId, fallback = "split_2") {
  const supportedLayouts = getTemplateSupportedLayouts(templateId);
  if (!supportedLayouts.length) return normalizeKey(fallback) || "split_2";

  const skillProfile = normalizeKey(getTemplateField(templateId, "skill_profile", ""));
  const preferredBySkill = normalizeLayoutList(SKILL_LAYOUT_PREFERENCES[skillProfile] || []);
  for (const candidate of preferredBySkill) {
    if (supportedLayouts.includes(candidate)) return candidate;
  }

  return supportedLayouts[0] || normalizeKey(fallback) || "split_2";
}
