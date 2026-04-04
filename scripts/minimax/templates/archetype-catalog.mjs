import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ARCHETYPE_CATALOG_PATH = path.join(__dirname, "archetype-catalog.json");

let _cached = null;

function normalizeKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function normalizeObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function normalizeList(value) {
  const list = Array.isArray(value) ? value : [];
  const out = [];
  const seen = new Set();
  for (const item of list) {
    const key = normalizeKey(item);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(key);
  }
  return out;
}

function loadCatalog() {
  if (_cached) return _cached;
  const raw = readFileSync(ARCHETYPE_CATALOG_PATH, "utf-8");
  const parsed = JSON.parse(raw);
  _cached = {
    version: String(parsed?.version || "v2").trim() || "v2",
    archetypes: normalizeList(parsed?.archetypes),
    role_defaults: normalizeObject(parsed?.role_defaults),
    layout_overrides: normalizeObject(parsed?.layout_overrides),
    semantic_overrides: normalizeObject(parsed?.semantic_overrides),
  };
  return _cached;
}

export function getArchetypeCatalog() {
  return loadCatalog();
}

export function listArchetypes() {
  return [...loadCatalog().archetypes];
}

export function resolveSlideArchetype({
  pageRole = "content",
  layoutGrid = "",
  semanticType = "",
} = {}) {
  const catalog = loadCatalog();
  const role = normalizeKey(pageRole) || "content";
  const layout = normalizeKey(layoutGrid);
  const semantic = normalizeKey(semanticType);

  const semanticOverride = normalizeKey(catalog.semantic_overrides?.[semantic]);
  if (semanticOverride && catalog.archetypes.includes(semanticOverride)) return semanticOverride;

  const layoutOverride = normalizeKey(catalog.layout_overrides?.[layout]);
  if (layoutOverride && catalog.archetypes.includes(layoutOverride)) return layoutOverride;

  const roleDefault = normalizeKey(catalog.role_defaults?.[role] || catalog.role_defaults?.content);
  if (roleDefault && catalog.archetypes.includes(roleDefault)) return roleDefault;

  return "thesis_assertion";
}
