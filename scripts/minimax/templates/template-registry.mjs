import { defaultTemplateId, getTemplateCatalog } from "./template-catalog.mjs";
import { getContractProfile, getTemplateCapabilities, getTemplateProfiles } from "./template-profiles.mjs";

const DENSITY_ORDER = { sparse: 0, balanced: 1, dense: 2 };
const VISUAL_BLOCK_TYPES = new Set(["image", "chart", "kpi", "workflow", "diagram"]);
const DATA_BLOCK_TYPES = new Set(["chart", "kpi", "table"]);
const CONSTRAINED_BLOCK_TYPES = new Set(["image", "chart", "kpi", "table", "workflow", "diagram", "icon_text", "svg"]);
const LAYOUT_HINT_TYPES = new Set(["split_2", "asymmetric_2", "grid_2", "grid_3", "grid_4", "bento_5", "bento_6", "hero_1"]);
const TERMINAL_TEMPLATE_IDS = new Set(["hero_dark", "hero_tech_cover", "quote_hero_dark"]);
const LIGHT_THEME_HINTS = [
  "education",
  "teaching",
  "training",
  "classroom",
  "student",
  "school",
  "curriculum",
  "lesson",
  "academic",
  "\u6559\u5b66",
  "\u8bfe\u5802",
  "\u6559\u80b2",
  "\u57f9\u8bad",
  "\u5b66\u6821",
  "\u8bfe\u7a0b",
  "\u9ad8\u6821",
];

function normalizeKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_\u4e00-\u9fff]+/g, "_");
}

function normalizeTemplateWhitelist(raw) {
  const out = [];
  const seen = new Set();
  const pushToken = (value) => {
    const token = normalizeKey(value || "");
    if (!token || seen.has(token)) return;
    if (!listTemplateIds().includes(token)) return;
    seen.add(token);
    out.push(token);
  };
  if (Array.isArray(raw)) {
    for (const item of raw) pushToken(item);
    return out;
  }
  const text = String(raw || "").trim();
  if (!text) return out;
  for (const part of text.split(",")) pushToken(part);
  return out;
}

function normalizeDensity(value) {
  const normalized = normalizeKey(value || "balanced");
  if (Object.prototype.hasOwnProperty.call(DENSITY_ORDER, normalized)) return normalized;
  return "balanced";
}

function normalizeTone(value) {
  const normalized = normalizeKey(value || "");
  if (normalized === "light" || normalized === "dark") return normalized;
  return "";
}

function pick(obj, keys, fallback = "") {
  for (const key of keys) {
    if (obj && obj[key] !== undefined && obj[key] !== null) return obj[key];
  }
  return fallback;
}

function buildSearchBlob(sourceSlide) {
  const textParts = [];
  textParts.push(String(pick(sourceSlide || {}, ["title", "narration", "speaker_notes", "speakerNotes"], "")));
  const blocks = Array.isArray(sourceSlide?.blocks) ? sourceSlide.blocks : [];
  for (const block of blocks) {
    const content = block?.content;
    if (typeof content === "string") textParts.push(content);
    if (content && typeof content === "object") {
      for (const key of ["title", "body", "text", "label", "caption", "description"]) {
        if (typeof content[key] === "string") textParts.push(content[key]);
      }
    }
  }
  return textParts.join(" ").toLowerCase();
}

function getSlideBlockTypes(sourceSlide) {
  const out = new Set();
  const blocks = Array.isArray(sourceSlide?.blocks) ? sourceSlide.blocks : [];
  for (const block of blocks) {
    const t = normalizeKey(block?.block_type ?? block?.type ?? "");
    if (t) out.add(t);
  }
  const elements = Array.isArray(sourceSlide?.elements) ? sourceSlide.elements : [];
  for (const el of elements) {
    const t = normalizeKey(el?.type ?? "");
    if (t) out.add(t);
  }
  return out;
}

function normalizeBlockTypeAlias(blockType) {
  const normalized = normalizeKey(blockType || "");
  if (normalized === "subtitle" || normalized === "text") return "body";
  return normalized;
}

function normalizeSlideTypeAlias(slideType) {
  const normalized = normalizeKey(slideType || "");
  if (normalized === "data_visualization") return "data";
  if (normalized === "mixed_media") return "content";
  if (normalized === "image_showcase") return "showcase";
  if (LAYOUT_HINT_TYPES.has(normalized)) return "";
  return normalized;
}

function hasImageAsset(sourceSlide) {
  const blocks = Array.isArray(sourceSlide?.blocks) ? sourceSlide.blocks : [];
  for (const block of blocks) {
    const bt = normalizeKey(block?.block_type ?? block?.type ?? "");
    if (bt !== "image") continue;
    const content = block?.content && typeof block.content === "object" ? block.content : {};
    const data = block?.data && typeof block.data === "object" ? block.data : {};
    const candidates = [
      content.url,
      content.src,
      content.imageUrl,
      content.image_url,
      data.url,
      data.src,
      data.imageUrl,
      data.image_url,
      block?.url,
      block?.src,
      block?.imageUrl,
      block?.image_url,
    ];
    if (candidates.some((item) => String(item || "").trim())) return true;
  }
  const elements = Array.isArray(sourceSlide?.elements) ? sourceSlide.elements : [];
  for (const element of elements) {
    const et = normalizeKey(element?.type ?? "");
    if (et !== "image") continue;
    const candidates = [element?.url, element?.src, element?.imageUrl, element?.image_url];
    if (candidates.some((item) => String(item || "").trim())) return true;
  }
  return false;
}

function getCatalog() {
  return getTemplateCatalog();
}

function listTemplateIds() {
  return Object.keys(getCatalog().templates || {});
}

function getDefaultTemplateId() {
  const fallback = normalizeKey(defaultTemplateId());
  if (fallback && listTemplateIds().includes(fallback)) return fallback;
  return "consulting_warm_light";
}

function getLayoutDefault(layoutKey = "split_2") {
  const catalog = getCatalog();
  const normalizedLayout = normalizeKey(layoutKey || "split_2") || "split_2";
  const configured = normalizeKey(catalog.layout_defaults?.[normalizedLayout] || "");
  if (configured && listTemplateIds().includes(configured)) return configured;
  return getDefaultTemplateId();
}

function keywordScore(blob, keywords) {
  let score = 0;
  for (const kw of keywords || []) {
    const marker = String(kw || "").trim().toLowerCase();
    if (!marker) continue;
    if (blob.includes(marker)) score += 1;
  }
  return score;
}

function templateKeywordScore(templateId, blob, catalog) {
  let best = 0;
  for (const rule of catalog.keyword_rules || []) {
    const template = String(rule?.template || "").trim().toLowerCase();
    if (!template || template !== templateId) continue;
    const score = keywordScore(blob, Array.isArray(rule?.keywords) ? rule.keywords : []);
    best = Math.max(best, score);
  }
  return best;
}

function normalizeArchetypeCandidates(raw) {
  const rows = Array.isArray(raw) ? raw : [];
  const out = [];
  const seen = new Set();
  for (const row of rows) {
    const value = typeof row === "string"
      ? row
      : row && typeof row === "object"
        ? row.archetype
        : "";
    const key = normalizeKey(value || "");
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(key);
  }
  return out;
}

function templateArchetypeBonus(templateId, archetypeKey, archetypeCandidates, catalog) {
  const templates = catalog?.templates || {};
  const template = templateId && typeof templates[templateId] === "object" ? templates[templateId] : {};
  const preferred = normalizeArchetypeCandidates(template?.preferred_archetypes);
  if (!preferred.length) return 0;
  const selected = normalizeKey(archetypeKey || "");
  if (selected && preferred.includes(selected)) return 3.2;
  const candidates = normalizeArchetypeCandidates(archetypeCandidates);
  if (candidates.some((candidate) => preferred.includes(candidate))) return 1.4;
  return 0;
}

function prefersLightTheme(searchBlob, blockTypes, { needsData, hasImageVisual }) {
  const blob = String(searchBlob || "").toLowerCase();
  const hintHit = LIGHT_THEME_HINTS.some((token) => token && blob.includes(String(token).toLowerCase()));
  const hasVisualBlocks = Boolean(Array.from(blockTypes || []).some((bt) => VISUAL_BLOCK_TYPES.has(bt)));
  const textHeavy = !needsData && !hasImageVisual && !hasVisualBlocks;
  return Boolean(hintHit || textHeavy);
}

function capabilityScore({
  templateId,
  capabilities,
  explicitType,
  layoutGrid,
  desiredDensity,
  preferredTone,
  blockTypes,
  needsVisual,
  needsData,
  hasImageVisual,
  keywordHit,
  layoutDefault,
  searchBlob,
  archetypeKey,
  archetypeCandidates,
  catalog,
}) {
  let score = 0;
  const slideTypes = new Set(capabilities.supported_slide_types || []);
  const layouts = new Set(capabilities.supported_layouts || []);
  const supportedBlocks = new Set(capabilities.supported_block_types || []);

  if (slideTypes.has(explicitType)) score += 2.5;
  else if (slideTypes.size > 0) score -= 4.0;
  if (explicitType === "content" && TERMINAL_TEMPLATE_IDS.has(templateId)) score -= 7.5;
  if (layouts.has(layoutGrid)) score += 3.0;
  else if (layouts.size > 0) score -= 6.0;

  const minRank = DENSITY_ORDER[normalizeDensity(capabilities?.density_range?.min)] ?? 0;
  const maxRank = DENSITY_ORDER[normalizeDensity(capabilities?.density_range?.max)] ?? 2;
  const desiredRank = DENSITY_ORDER[normalizeDensity(desiredDensity)] ?? 1;
  if (desiredRank >= minRank && desiredRank <= maxRank) score += 2.0;
  else score -= 2.0;

  for (const bt of blockTypes) {
    if (supportedBlocks.has(bt)) score += 0.35;
    else score -= 0.8;
  }

  if (needsVisual) score += (Number(capabilities.visual_anchor_capacity || 0) > 0 ? 1.5 : -4.0);
  if (needsData) score += (Number(capabilities.data_block_capacity || 0) > 0 ? 1.5 : -4.0);
  if (Boolean(capabilities.requires_image_asset) && !hasImageVisual) score -= 5.0;

  const contractId = String(getTemplateProfiles(templateId).contract_profile || "default");
  const contract = getContractProfile(contractId);
  const minVisualByContract = Number(contract.min_visual_blocks || 0);
  if (minVisualByContract > 0 && !needsVisual) {
    score -= 4.0;
  }

  score += Math.min(3, Number(keywordHit || 0));
  score += templateArchetypeBonus(templateId, archetypeKey, archetypeCandidates, catalog);
  if (templateId === "architecture_dark_panel" && keywordHit < 2 && !blockTypes.has("workflow")) {
    score -= 2.0;
  }
  if (prefersLightTheme(searchBlob, blockTypes, { needsData, hasImageVisual })) {
    if (templateId.endsWith("_light")) score += 1.8;
    else if (templateId.endsWith("_dark")) score -= 1.0;
  }
  const tone = normalizeTone(preferredTone);
  if (tone === "light") {
    if (templateId.endsWith("_light")) score += 4.0;
    else if (templateId.endsWith("_dark")) score -= 3.2;
  } else if (tone === "dark") {
    if (templateId.endsWith("_dark")) score += 3.2;
    else if (templateId.endsWith("_light")) score -= 2.6;
  }
  if (templateId === layoutDefault) score += 1.2;
  return score;
}

function pickBestTemplateFromAllowed({
  allowedTemplates,
  sourceSlide,
  explicitType,
  layoutGrid,
  desiredDensity,
  preferredTone = "",
}) {
  const candidates = normalizeTemplateWhitelist(allowedTemplates);
  if (!candidates.length) return "";
  if (candidates.length === 1) return candidates[0];

  const normalizedType = normalizeKey(explicitType || "content");
  const normalizedGrid = normalizeKey(layoutGrid || "split_2");
  const blob = buildSearchBlob(sourceSlide);
  const blockTypes = getSlideBlockTypes(sourceSlide);
  const needsVisual = Boolean(Array.from(blockTypes).some((bt) => VISUAL_BLOCK_TYPES.has(bt)))
    || Boolean(Array.isArray(sourceSlide?.image_keywords) && sourceSlide.image_keywords.length > 0);
  const needsData = Boolean(Array.from(blockTypes).some((bt) => DATA_BLOCK_TYPES.has(bt)));
  const hasImageVisual = hasImageAsset(sourceSlide);
  const catalog = getCatalog();
  const layoutDefault = getLayoutDefault(normalizedGrid);
  const archetypeKey = normalizeKey(sourceSlide?.archetype || "");
  const archetypeCandidates = normalizeArchetypeCandidates(sourceSlide?.archetype_candidates);

  let bestTemplate = candidates[0];
  let bestScore = -10_000;
  for (const templateId of candidates) {
    const capabilities = getTemplateCapabilities(templateId);
    const kwScore = templateKeywordScore(templateId, blob, catalog);
    const score = capabilityScore({
      templateId,
      capabilities,
      explicitType: normalizedType,
      layoutGrid: normalizedGrid,
      desiredDensity,
      preferredTone,
      blockTypes,
      needsVisual,
      needsData,
      hasImageVisual,
      keywordHit: kwScore,
      layoutDefault,
      searchBlob: blob,
      archetypeKey,
      archetypeCandidates,
      catalog,
    });
    if (score > bestScore) {
      bestScore = score;
      bestTemplate = templateId;
    }
  }
  return bestTemplate;
}

export function inferTemplateFamilyFromContent(
  sourceSlide,
  explicitType = "content",
  layoutGrid = "split_2",
  desiredDensity = "balanced",
  preferredTone = "",
) {
  const normalizedType = normalizeKey(explicitType || "content");
  const normalizedGrid = normalizeKey(layoutGrid || "split_2");
  const catalog = getCatalog();
  const templateIds = listTemplateIds();

  if (normalizedType === "cover" || normalizedGrid === "hero_1") return "hero_tech_cover";
  if (normalizedType === "summary") return "quote_hero_dark";

  const blob = buildSearchBlob(sourceSlide);
  const blockTypes = getSlideBlockTypes(sourceSlide);
  const needsVisual = Boolean(Array.from(blockTypes).some((bt) => VISUAL_BLOCK_TYPES.has(bt)))
    || Boolean(Array.isArray(sourceSlide?.image_keywords) && sourceSlide.image_keywords.length > 0);
  const needsData = Boolean(Array.from(blockTypes).some((bt) => DATA_BLOCK_TYPES.has(bt)));
  const hasImageVisual = hasImageAsset(sourceSlide);
  const layoutDefault = getLayoutDefault(normalizedGrid);
  const archetypeKey = normalizeKey(sourceSlide?.archetype || "");
  const archetypeCandidates = normalizeArchetypeCandidates(sourceSlide?.archetype_candidates);

  let bestTemplate = layoutDefault;
  let bestScore = -10_000;

  for (const templateId of templateIds) {
    const capabilities = getTemplateCapabilities(templateId);
    const kwScore = templateKeywordScore(templateId, blob, catalog);
    const score = capabilityScore({
      templateId,
      capabilities,
      explicitType: normalizedType,
      layoutGrid: normalizedGrid,
      desiredDensity,
      preferredTone,
      blockTypes,
      needsVisual,
      needsData,
      hasImageVisual,
      keywordHit: kwScore,
      layoutDefault,
      searchBlob: blob,
      archetypeKey,
      archetypeCandidates,
      catalog,
    });
    if (score > bestScore) {
      bestScore = score;
      bestTemplate = templateId;
    }
  }

  return templateIds.includes(bestTemplate) ? bestTemplate : getDefaultTemplateId();
}

export function resolveTemplateFamilyForSlide({
  sourceSlide,
  requestedTemplateFamily = "auto",
  explicitType = "content",
  layoutGrid = "split_2",
  desiredDensity = "balanced",
  preferredTone = "",
  normalizeTemplateFamily,
}) {
  const whitelist = normalizeTemplateWhitelist(
    pick(sourceSlide || {}, ["template_family_whitelist", "template_candidates", "template_whitelist"], []),
  );
  const requested = normalizeKey(requestedTemplateFamily) === "auto" ? "" : requestedTemplateFamily;
  const inferred = requested
    || inferTemplateFamilyFromContent(sourceSlide, explicitType, layoutGrid, desiredDensity, preferredTone);
  const inferredNormalized = normalizeKey(inferred || "");
  const constrainedInferred = whitelist.length > 0
    ? (
      whitelist.includes(inferredNormalized)
        ? inferredNormalized
        : pickBestTemplateFromAllowed({
          allowedTemplates: whitelist,
          sourceSlide,
          explicitType,
          layoutGrid,
          desiredDensity,
          preferredTone,
        })
    )
    : inferred;
  if (typeof normalizeTemplateFamily === "function") {
    const normalizedByFn = normalizeTemplateFamily(constrainedInferred, explicitType, layoutGrid);
    const normalizedFnKey = normalizeKey(normalizedByFn || "");
    if (whitelist.length > 0 && !whitelist.includes(normalizedFnKey)) {
      return pickBestTemplateFromAllowed({
        allowedTemplates: whitelist,
        sourceSlide,
        explicitType,
        layoutGrid,
        desiredDensity,
        preferredTone,
      });
    }
    return normalizedByFn;
  }
  const normalized = normalizeKey(constrainedInferred || getDefaultTemplateId());
  if (whitelist.length > 0) {
    if (whitelist.includes(normalized)) return normalized;
    return pickBestTemplateFromAllowed({
      allowedTemplates: whitelist,
      sourceSlide,
      explicitType,
      layoutGrid,
      desiredDensity,
      preferredTone,
    });
  }
  return listTemplateIds().includes(normalized) ? normalized : getDefaultTemplateId();
}

export function resolveSubtypeByTemplate(subtype, templateFamily) {
  const normalizedSubtype = normalizeKey(subtype || "") || "content";
  const family = normalizeKey(templateFamily || "") || getDefaultTemplateId();
  const overrides = getCatalog().subtype_overrides?.[family];
  if (overrides && overrides[normalizedSubtype]) return overrides[normalizedSubtype];
  return normalizedSubtype;
}

export function isLightTemplateFamily(templateFamily) {
  return String(templateFamily || "").endsWith("_light");
}

export function defaultTemplateForLayout(layoutGrid = "split_2") {
  return getLayoutDefault(layoutGrid);
}

export function assessTemplateCapabilityForSlide({
  sourceSlide,
  templateFamily,
  slideType = "",
  layoutGrid = "",
}) {
  const family = normalizeKey(templateFamily || "") || getDefaultTemplateId();
  const capabilities = getTemplateCapabilities(family);
  const supportedSlideTypes = new Set(
    (Array.isArray(capabilities?.supported_slide_types) ? capabilities.supported_slide_types : [])
      .map((value) => normalizeSlideTypeAlias(value))
      .filter(Boolean),
  );
  const supportedLayouts = new Set(
    (Array.isArray(capabilities?.supported_layouts) ? capabilities.supported_layouts : [])
      .map((value) => normalizeKey(value))
      .filter(Boolean),
  );
  const normalizedSlideType = normalizeSlideTypeAlias(
    slideType
    || sourceSlide?.subtype
    || sourceSlide?.page_type
    || sourceSlide?.slide_type
    || "",
  );
  const normalizedLayout = normalizeKey(layoutGrid || sourceSlide?.layout_grid || sourceSlide?.layout || "");
  const supportedBlocks = new Set(
    (Array.isArray(capabilities?.supported_block_types) ? capabilities.supported_block_types : [])
      .map((blockType) => normalizeBlockTypeAlias(blockType))
      .filter(Boolean),
  );
  const slideBlockTypes = Array.from(getSlideBlockTypes(sourceSlide))
    .map((blockType) => normalizeBlockTypeAlias(blockType))
    .filter(Boolean);
  const unsupportedBlockTypes = slideBlockTypes
    .filter((blockType) => CONSTRAINED_BLOCK_TYPES.has(blockType) && !supportedBlocks.has(blockType))
    .filter((value, idx, arr) => arr.indexOf(value) === idx);

  const missingRequiredImageAsset =
    Boolean(capabilities?.requires_image_asset) && !hasImageAsset(sourceSlide);
  const unsupportedSlideType =
    normalizedSlideType
    && supportedSlideTypes.size > 0
    && !supportedSlideTypes.has(normalizedSlideType);
  const unsupportedLayout =
    normalizedLayout
    && supportedLayouts.size > 0
    && !supportedLayouts.has(normalizedLayout);

  return {
    template_family: family,
    supported_slide_types: Array.from(supportedSlideTypes),
    supported_layouts: Array.from(supportedLayouts),
    slide_type: normalizedSlideType,
    layout_grid: normalizedLayout,
    supported_block_types: Array.from(supportedBlocks),
    slide_block_types: slideBlockTypes,
    unsupported_block_types: unsupportedBlockTypes,
    unsupported_slide_type: Boolean(unsupportedSlideType),
    unsupported_layout: Boolean(unsupportedLayout),
    missing_required_image_asset: missingRequiredImageAsset,
    compatible:
      unsupportedBlockTypes.length === 0
      && !missingRequiredImageAsset
      && !unsupportedSlideType
      && !unsupportedLayout,
  };
}

