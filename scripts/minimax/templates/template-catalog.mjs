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

function loadCatalog() {
  if (_cachedCatalog) return _cachedCatalog;
  const raw = readFileSync(CATALOG_PATH, "utf-8");
  const parsed = JSON.parse(raw);
  _cachedCatalog = {
    layout_defaults: normalizeObject(parsed.layout_defaults),
    subtype_overrides: normalizeObject(parsed.subtype_overrides),
    palette_keywords: normalizeObject(parsed.palette_keywords),
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

export function listTemplateIds() {
  return Object.keys(loadCatalog().templates);
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
