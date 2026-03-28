import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const CATALOG_PATH = path.join(__dirname, "template-catalog.json");

let _cachedCatalog = null;

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
    keyword_rules: Array.isArray(parsed.keyword_rules) ? parsed.keyword_rules : [],
    contract_profiles: normalizeObject(parsed.contract_profiles),
    quality_profiles: normalizeObject(parsed.quality_profiles),
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
