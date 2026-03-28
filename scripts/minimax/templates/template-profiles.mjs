import { getTemplateCatalog } from "./template-catalog.mjs";

const DEFAULT_TEMPLATE_ID = "dashboard_dark";
const DEFAULT_CONTRACT_PROFILE_ID = "default";

const DENSITY_ORDER = { sparse: 0, balanced: 1, dense: 2 };

function getTemplates() {
  return getTemplateCatalog().templates || {};
}

function normalizeTemplateId(templateId = "") {
  const requested = String(templateId || "").trim().toLowerCase();
  if (requested && Object.prototype.hasOwnProperty.call(getTemplates(), requested)) return requested;
  return DEFAULT_TEMPLATE_ID;
}

export function getTemplateProfiles(templateId = DEFAULT_TEMPLATE_ID) {
  const templates = getTemplates();
  const id = normalizeTemplateId(templateId);
  const profile = templates[id] || {};
  return {
    template_id: id,
    skill_profile: String(profile.skill_profile || "general-content"),
    hardness_profile: String(profile.hardness_profile || "balanced"),
    schema_profile: String(profile.schema_profile || "ppt-template/v2-generic"),
    contract_profile: String(profile.contract_profile || "default"),
    quality_profile: String(profile.quality_profile || "default"),
  };
}

function normalizeDensity(value = "balanced") {
  const normalized = String(value || "").trim().toLowerCase();
  return Object.prototype.hasOwnProperty.call(DENSITY_ORDER, normalized) ? normalized : "balanced";
}

function normalizeStringArray(value, fallback = []) {
  if (!Array.isArray(value)) return fallback;
  return value.map((item) => String(item || "").trim().toLowerCase()).filter(Boolean);
}

export function getTemplateCapabilities(templateId = DEFAULT_TEMPLATE_ID) {
  const templates = getTemplates();
  const id = normalizeTemplateId(templateId);
  const raw = templates[id]?.capabilities && typeof templates[id].capabilities === "object"
    ? templates[id].capabilities
    : {};
  const densityRange = raw.density_range && typeof raw.density_range === "object" ? raw.density_range : {};
  return {
    template_id: id,
    supported_slide_types: normalizeStringArray(raw.supported_slide_types, ["content"]),
    supported_layouts: normalizeStringArray(raw.supported_layouts, ["split_2"]),
    supported_block_types: normalizeStringArray(raw.supported_block_types, ["title", "body", "list"]),
    density_range: {
      min: normalizeDensity(densityRange.min || "sparse"),
      max: normalizeDensity(densityRange.max || "dense"),
      recommended: normalizeDensity(densityRange.recommended || "balanced"),
    },
    visual_anchor_capacity: Number(raw.visual_anchor_capacity || 0),
    data_block_capacity: Number(raw.data_block_capacity || 0),
    requires_image_asset: Boolean(raw.requires_image_asset),
  };
}

export function getContractProfile(contractProfileId = DEFAULT_CONTRACT_PROFILE_ID) {
  const contractProfiles = getTemplateCatalog().contract_profiles || {};
  const requested = String(contractProfileId || "").trim().toLowerCase() || DEFAULT_CONTRACT_PROFILE_ID;
  const raw = contractProfiles[requested] && typeof contractProfiles[requested] === "object"
    ? contractProfiles[requested]
    : contractProfiles[DEFAULT_CONTRACT_PROFILE_ID] || {};
  const groups = Array.isArray(raw.required_one_of_groups)
    ? raw.required_one_of_groups
      .filter((group) => Array.isArray(group))
      .map((group) => normalizeStringArray(group))
      .filter((group) => group.length > 0)
    : [];
  return {
    id: requested,
    required_block_types: normalizeStringArray(raw.required_block_types),
    required_one_of_groups: groups,
    min_text_blocks: Number(raw.min_text_blocks || 0),
    min_visual_blocks: Number(raw.min_visual_blocks || 0),
    visual_anchor_types: normalizeStringArray(raw.visual_anchor_types, ["image", "chart", "kpi", "workflow", "diagram"]),
    require_emphasis_signal: Boolean(raw.require_emphasis_signal),
    forbid_duplicate_text: Boolean(raw.forbid_duplicate_text),
  };
}

export function getQualityProfile(qualityProfileId = "default") {
  const qualityProfiles = getTemplateCatalog().quality_profiles || {};
  const requested = String(qualityProfileId || "").trim().toLowerCase() || "default";
  const raw = qualityProfiles[requested] && typeof qualityProfiles[requested] === "object"
    ? qualityProfiles[requested]
    : qualityProfiles.default || {};
  const toNumber = (value, fallback) => {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
  };
  return {
    id: requested,
    min_typography_levels: Math.max(1, Math.round(toNumber(raw.min_typography_levels, 2))),
    min_content_blocks: Math.max(1, Math.round(toNumber(raw.min_content_blocks, 2))),
    blank_area_max_ratio: Math.max(0.1, Math.min(0.9, toNumber(raw.blank_area_max_ratio, 0.45))),
    chart_min_font_size: Math.max(6, toNumber(raw.chart_min_font_size, 9)),
    require_emphasis_signal: Boolean(raw.require_emphasis_signal ?? true),
    forbid_duplicate_text: Boolean(raw.forbid_duplicate_text ?? true),
    forbid_title_echo: Boolean(raw.forbid_title_echo ?? true),
    require_image_url: Boolean(raw.require_image_url ?? true),
    layout_max_type_ratio: Math.max(0.1, Math.min(0.95, toNumber(raw.layout_max_type_ratio, 0.45))),
    layout_max_adjacent_repeat: Math.max(1, Math.round(toNumber(raw.layout_max_adjacent_repeat, 1))),
    layout_min_slide_count: Math.max(2, Math.round(toNumber(raw.layout_min_slide_count, 6))),
    layout_min_variety_long_deck: Math.max(1, Math.round(toNumber(raw.layout_min_variety_long_deck, 4))),
    layout_long_deck_threshold: Math.max(4, Math.round(toNumber(raw.layout_long_deck_threshold, 10))),
    enforce_terminal_slide_types: Boolean(raw.enforce_terminal_slide_types ?? false),
  };
}
