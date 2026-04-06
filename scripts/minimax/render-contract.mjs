import { getContractProfile, getTemplateProfiles } from "./templates/template-profiles.mjs";
import { resolveTemplateFamilyForSlide } from "./templates/template-registry.mjs";
import { getArchetypeCatalog, resolveSlideArchetype } from "./templates/archetype-catalog.mjs";

export const RENDER_INPUT_SCHEMA = {
  title: "string",
  theme: {
    palette: "string",
    style: "string",
  },
  theme_recipe: "string",
  tone: "string",
  design_spec: "object",
  template_id: "string",
  skill_profile: "string",
  hardness_profile: "string",
  schema_profile: "string",
  contract_profile: "string",
  quality_profile: "string",
  presentation_contract_v2: "object",
  slides: [
    {
      page_number: "number",
      slide_type: "string",
      page_role: "string",
      archetype: "string",
      layout_grid: "string",
      template_id: "string",
      skill_profile: "string",
      hardness_profile: "string",
      schema_profile: "string",
      contract_profile: "string",
      quality_profile: "string",
      theme_recipe: "string",
      tone: "string",
      render_path: "string",
      blocks: [
        {
          block_type: "string",
          card_id: "string",
          content: "object|string",
        },
      ],
      bg_style: "string",
      image_keywords: ["string"],
    },
  ],
};

function asText(value, fallback = "") {
  const text = String(value ?? "").trim();
  return text || fallback;
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function asNumber(value, fallback = 0) {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return n;
}

function normalizeKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_\u4e00-\u9fff]+/g, "_");
}

function normalizeRenderPath(value) {
  const normalized = asText(value, "").toLowerCase();
  if (["pptxgenjs", "svg", "png_fallback"].includes(normalized)) return normalized;
  return "pptxgenjs";
}

function normalizeToneValue(value, fallback = "auto") {
  const normalized = asText(value, fallback).toLowerCase();
  if (normalized === "light" || normalized === "dark") return normalized;
  return "auto";
}

function normalizeThemeRecipeValue(value, fallback = "auto") {
  const normalized = asText(value, fallback).toLowerCase();
  return normalized || "auto";
}

function normalizeDesignSpec(payload, theme, themeRecipe = "auto", tone = "auto") {
  const raw = payload?.design_spec;
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    const visual = raw.visual && typeof raw.visual === "object" ? raw.visual : {};
    return {
      ...raw,
      colors: raw.colors && typeof raw.colors === "object" ? raw.colors : {},
      typography: raw.typography && typeof raw.typography === "object" ? raw.typography : {},
      spacing: raw.spacing && typeof raw.spacing === "object" ? raw.spacing : {},
      visual: {
        ...visual,
        theme_recipe: normalizeThemeRecipeValue(visual.theme_recipe, themeRecipe),
        tone: normalizeToneValue(visual.tone, tone),
      },
    };
  }
  const styleRecipe = asText(theme?.style, "soft").toLowerCase();
  return {
    colors: {},
    typography: {},
    spacing: {},
    visual: {
      style_recipe: styleRecipe,
      theme_recipe: normalizeThemeRecipeValue(payload?.theme_recipe, themeRecipe),
      tone: normalizeToneValue(payload?.tone, tone),
      visual_priority: true,
      visual_density: asText(payload?.visual_density, "balanced"),
    },
  };
}

function normalizeTheme(payload) {
  const source = payload?.theme && typeof payload.theme === "object" ? payload.theme : {};
  const palette = asText(source.palette, asText(payload?.minimax_palette_key, "auto"));
  const style = asText(source.style, asText(payload?.minimax_style_variant, "auto"));
  return { palette, style };
}

function normalizeBlock(raw, idx = 0) {
  const block = raw && typeof raw === "object" ? { ...raw } : {};
  const blockType = asText(block.block_type ?? block.type, "text");
  const cardId = asText(block.card_id ?? block.id, `card-${idx + 1}`);
  const content = block.content ?? block.text ?? "";
  return {
    ...block,
    block_type: blockType,
    card_id: cardId,
    content,
  };
}

function inferSlideType(raw, idx, total) {
  const explicit = asText(raw?.slide_type ?? raw?.type, "");
  if (explicit) return explicit;
  if (idx === 0) return "cover";
  if (idx === total - 1) return "summary";
  return "content";
}

function inferPageRole(slideType) {
  const normalized = asText(slideType, "").toLowerCase();
  if (["cover", "toc", "divider", "summary"].includes(normalized)) return normalized;
  return "content";
}

function inferLayoutGrid(raw, slideType) {
  const explicit = asText(raw?.layout_grid ?? raw?.layout, "");
  if (explicit) return explicit;
  const typeHint = asText(slideType, "").toLowerCase();
  if ([
    "split_2",
    "asymmetric_2",
    "grid_2",
    "grid_3",
    "grid_4",
    "bento_5",
    "bento_6",
    "timeline",
  ].includes(typeHint)) {
    return typeHint;
  }
  if (slideType === "cover" || slideType === "summary") return "hero_1";
  return "split_2";
}

function normalizeSlide(
  raw,
  idx,
  total,
  deckTemplateId = "auto",
  deckDesiredDensity = "balanced",
  deckThemeRecipe = "auto",
  deckTone = "auto",
) {
  const source = raw && typeof raw === "object" ? { ...raw } : {};
  const slideType = inferSlideType(source, idx, total);
  const pageRole = inferPageRole(slideType);
  const layoutGrid = inferLayoutGrid(source, slideType);
  const blocks = asArray(source.blocks).map((item, blockIdx) => normalizeBlock(item, blockIdx));
  const requestedTemplate = asText(source.template_family ?? source.template_id, deckTemplateId || "auto");
  const templateLock = Boolean(source.template_lock);
  const explicitTemplate = normalizeKey(requestedTemplate) !== "auto";
  const resolvedTemplate = resolveTemplateFamilyForSlide({
    sourceSlide: source,
    requestedTemplateFamily: explicitTemplate ? requestedTemplate : (templateLock ? (requestedTemplate || "auto") : "auto"),
    explicitType: slideType,
    layoutGrid,
    desiredDensity: asText(source.content_density, deckDesiredDensity || "balanced"),
  });
  const profiles = getTemplateProfiles(resolvedTemplate);
  const semanticType = asText(
    source.semantic_type ?? source.semantic_subtype ?? source.content_subtype ?? source.subtype,
    asText(source.page_type, ""),
  );
  const resolvedArchetype = resolveSlideArchetype({
    pageRole,
    layoutGrid,
    semanticType,
  });
  const archetypePlan = inferArchetypePlan(source, resolvedArchetype);
  const archetype = asText(archetypePlan.selected, resolvedArchetype).toLowerCase();
  return {
    ...source,
    page_number: Number(source.page_number ?? idx + 1),
    slide_type: slideType,
    page_role: pageRole,
    archetype,
    archetype_confidence: asNumber(archetypePlan.confidence, 0.0),
    archetype_candidates: asArray(archetypePlan.candidates).slice(0, 3),
    archetype_plan: archetypePlan,
    layout_grid: layoutGrid,
    template_family: explicitTemplate ? asText(source.template_family, profiles.template_id) : profiles.template_id,
    template_id: (templateLock || explicitTemplate) ? asText(source.template_id, profiles.template_id) : profiles.template_id,
    skill_profile: (templateLock || explicitTemplate) ? asText(source.skill_profile, profiles.skill_profile) : profiles.skill_profile,
    hardness_profile: (templateLock || explicitTemplate)
      ? asText(source.hardness_profile, profiles.hardness_profile)
      : profiles.hardness_profile,
    schema_profile: (templateLock || explicitTemplate) ? asText(source.schema_profile, profiles.schema_profile) : profiles.schema_profile,
    contract_profile: (templateLock || explicitTemplate)
      ? asText(source.contract_profile, profiles.contract_profile)
      : profiles.contract_profile,
    quality_profile: (templateLock || explicitTemplate)
      ? asText(source.quality_profile, profiles.quality_profile)
      : profiles.quality_profile,
    theme_recipe: normalizeThemeRecipeValue(
      source.theme_recipe ?? source.themeRecipe,
      deckThemeRecipe,
    ),
    tone: normalizeToneValue(
      source.tone ?? source.theme_tone ?? source.preferred_tone,
      deckTone,
    ),
    render_path: normalizeRenderPath(source.render_path),
    blocks,
    bg_style: asText(source.bg_style, "light"),
    image_keywords: asArray(source.image_keywords).map((v) => asText(v)).filter(Boolean),
  };
}

function inferArchetypePlan(slide, fallbackArchetype = "thesis_assertion") {
  const selectedFallback = asText(slide?.archetype, asText(fallbackArchetype, "thesis_assertion")).toLowerCase();
  const rawPlan = slide?.archetype_plan && typeof slide.archetype_plan === "object"
    ? slide.archetype_plan
    : {};
  const selected = asText(rawPlan.selected, selectedFallback).toLowerCase();
  const confidence = Math.max(0, Math.min(1, asNumber(rawPlan.confidence, asNumber(slide?.archetype_confidence, 0))));
  const rawCandidates = asArray(rawPlan.candidates).length
    ? asArray(rawPlan.candidates)
    : asArray(slide?.archetype_candidates);
  const candidates = rawCandidates
    .map((row) => {
      if (row && typeof row === "object") {
        return {
          archetype: asText(row.archetype, ""),
          score: Math.max(0, Math.min(1, asNumber(row.score, 0))),
          base_score: Math.max(0, Math.min(1, asNumber(row.base_score, asNumber(row.score, 0)))),
          fit_bonus: asNumber(row.fit_bonus, 0),
          status: asText(row.status, "ok"),
          reasons: asArray(row.reasons).map((item) => asText(item)).filter(Boolean).slice(0, 6),
        };
      }
      const text = asText(row, "");
      if (!text) return null;
      return {
        archetype: text,
        score: 0.5,
        base_score: 0.5,
        fit_bonus: 0,
        status: "ok",
        reasons: [],
      };
    })
    .filter(Boolean)
    .slice(0, 3);
  const finalCandidates = candidates.length
    ? candidates
    : [{
      archetype: selected,
      score: Math.max(0.5, confidence || 0.5),
      base_score: Math.max(0.5, confidence || 0.5),
      fit_bonus: 0,
      status: "ok",
      reasons: [],
    }];
  return {
    selected,
    confidence: confidence || Math.max(0.5, asNumber(finalCandidates[0]?.score, 0.5)),
    candidates: finalCandidates,
    rerank_version: asText(rawPlan.rerank_version, "v1"),
  };
}

function inferSemanticConstraints(slide) {
  const blockTypes = new Set(
    (Array.isArray(slide?.blocks) ? slide.blocks : [])
      .map((b) => normalizedBlockType(b))
      .filter(Boolean),
  );
  const semanticType = asText(
    slide?.semantic_type ?? slide?.semantic_subtype ?? slide?.content_subtype ?? slide?.subtype,
    "",
  ).toLowerCase();
  const diagramType = ["workflow", "diagram", "timeline", "roadmap"].find((key) =>
    semanticType.includes(key) || blockTypes.has(key),
  ) || "none";
  return {
    media_required: blockTypes.has("image"),
    chart_required: blockTypes.has("chart") || blockTypes.has("kpi") || blockTypes.has("table"),
    diagram_type: diagramType,
  };
}

function inferContentChannel(slide) {
  const strategy = slide?.content_strategy && typeof slide.content_strategy === "object"
    ? slide.content_strategy
    : {};
  const evidence = Array.isArray(strategy.evidence)
    ? strategy.evidence.map((v) => asText(v)).filter(Boolean).slice(0, 4)
    : [];
  const fallbackEvidence = [];
  if (!evidence.length) {
    const blocks = Array.isArray(slide?.blocks) ? slide.blocks : [];
    for (const block of blocks) {
      const bt = normalizedBlockType(block);
      if (bt === "title") continue;
      const text = blockPlainText(block);
      if (!text) continue;
      fallbackEvidence.push(text);
      if (fallbackEvidence.length >= 4) break;
    }
  }
  const dataPoints = [];
  for (const block of Array.isArray(slide?.blocks) ? slide.blocks : []) {
    const bt = normalizedBlockType(block);
    if (!["chart", "kpi", "table"].includes(bt)) continue;
    const content = block?.content && typeof block.content === "object" ? block.content : {};
    dataPoints.push({
      block_type: bt,
      label: asText(content.label ?? content.title, asText(block?.card_id, "")),
      value: content.value ?? null,
    });
    if (dataPoints.length >= 6) break;
  }
  const titleText = (() => {
    const explicit = asText(slide?.title, "");
    if (explicit) return explicit;
    for (const block of Array.isArray(slide?.blocks) ? slide.blocks : []) {
      if (normalizedBlockType(block) !== "title") continue;
      const text = blockPlainText(block);
      if (text) return text;
    }
    return "";
  })();
  const mediaIntent = (() => {
    const keywords = Array.isArray(slide?.image_keywords)
      ? slide.image_keywords.map((v) => asText(v)).filter(Boolean)
      : [];
    if (keywords.length) return keywords.slice(0, 3).join(" ");
    const semantic = asText(
      slide?.semantic_type ?? slide?.semantic_subtype ?? slide?.content_subtype ?? slide?.subtype,
      "",
    );
    if (semantic) return semantic;
    return asText(slide?.title, "visual_context");
  })();
  return {
    title: titleText,
    assertion: asText(strategy.assertion, titleText),
    evidence: evidence.length ? evidence : fallbackEvidence,
    data_points: dataPoints,
    media_intent: mediaIntent,
  };
}

function inferVisualChannel(slide) {
  return {
    layout: asText(slide?.layout_grid, "split_2"),
    render_path: asText(slide?.render_path, "pptxgenjs"),
    component_slots: inferComponentSlots(slide),
    animation_rhythm: asText(slide?.animation_rhythm, "calm"),
  };
}

function inferComponentSlots(slide) {
  const slots = [];
  const blocks = Array.isArray(slide?.blocks) ? slide.blocks : [];
  for (const block of blocks) {
    const cardId = asText(block?.card_id, "");
    if (!cardId) continue;
    slots.push(cardId);
    if (slots.length >= 8) break;
  }
  return slots.length ? slots : ["title", "body"];
}

function buildPresentationContractV2({ title, designSpec, slides }) {
  const normalizedSlides = Array.isArray(slides) ? slides : [];
  return {
    version: "v2",
    deck_spec: {
      topic: asText(title, "Presentation"),
      design_tokens: {
        color: designSpec?.colors || {},
        typography: designSpec?.typography || {},
        spacing: designSpec?.spacing || {},
      },
      guardrails: {
        token_only_mode: true,
        max_text_only_slide_ratio: 0.2,
        min_media_coverage_ratio: 0.7,
      },
    },
    slides: normalizedSlides.map((slide, idx) => ({
      ...(() => {
        const fallbackArchetype = asText(slide?.archetype, "thesis_assertion");
        const plan = inferArchetypePlan(slide, fallbackArchetype);
        return {
          archetype: asText(plan.selected, fallbackArchetype),
          archetype_confidence: Math.max(0, Math.min(1, asNumber(plan.confidence, 0))),
          archetype_candidates: asArray(plan.candidates).slice(0, 3),
          archetype_plan: plan,
        };
      })(),
      slide_id: asText(slide?.slide_id ?? slide?.id, `slide-${idx + 1}`),
      page_role: asText(slide?.page_role, inferPageRole(slide?.slide_type)),
      layout_grid: asText(slide?.layout_grid, "split_2"),
      render_path: asText(slide?.render_path, "pptxgenjs"),
      component_slots: inferComponentSlots(slide),
      content_channel: inferContentChannel(slide),
      visual_channel: inferVisualChannel(slide),
      semantic_constraints: inferSemanticConstraints(slide),
    })),
  };
}

function hasRenderableContent(slide) {
  return (
    (Array.isArray(slide.blocks) && slide.blocks.length > 0) ||
    (Array.isArray(slide.elements) && slide.elements.length > 0) ||
    !!asText(slide.markdown) ||
    !!asText(slide.imageUrl) ||
    !!asText(slide.title) ||
    !!asText(slide.narration) ||
    !!asText(slide.speaker_notes) ||
    (Array.isArray(slide.key_points) && slide.key_points.length > 0) ||
    (Array.isArray(slide.bullets) && slide.bullets.length > 0)
  );
}

function isContentSlide(slide) {
  const t = asText(slide?.slide_type, "").toLowerCase();
  return !["cover", "summary", "toc", "divider", "hero_1"].includes(t);
}

function normalizedBlockType(block) {
  return asText(block?.block_type ?? block?.type, "").toLowerCase();
}

function normalizedContractProfile(slide) {
  return asText(slide?.contract_profile, "default").toLowerCase();
}

function blockPlainText(block) {
  const content = block?.content;
  if (typeof content === "string") return content.trim();
  if (content && typeof content === "object") {
    const parts = [];
    for (const key of ["title", "body", "text", "label", "caption", "description"]) {
      const value = String(content[key] ?? "").trim();
      if (value) parts.push(value);
    }
    if (parts.length) return parts.join(" ");
  }
  const data = block?.data;
  if (data && typeof data === "object") {
    for (const key of ["title", "label", "description"]) {
      const value = String(data[key] ?? "").trim();
      if (value) return value;
    }
  }
  return "";
}

function normalizeTextKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, " ")
    .replace(/[^0-9a-z\u4e00-\u9fff%+.-]/g, "");
}

function hasDuplicateBlockText(slide) {
  const blocks = Array.isArray(slide?.blocks) ? slide.blocks : [];
  const seen = new Set();
  for (const block of blocks) {
    const t = normalizeTextKey(blockPlainText(block));
    if (!t || normalizedBlockType(block) === "title") continue;
    if (seen.has(t)) return true;
    seen.add(t);
  }
  return false;
}

function countByTypes(slide, types = []) {
  const typeSet = new Set((types || []).map((t) => String(t || "").toLowerCase()).filter(Boolean));
  if (!typeSet.size) return 0;
  const blocks = Array.isArray(slide?.blocks) ? slide.blocks : [];
  let count = 0;
  for (const block of blocks) {
    if (typeSet.has(normalizedBlockType(block))) count += 1;
  }
  return count;
}

function countTextBlocks(slide, visualTypes = []) {
  const visualSet = new Set((visualTypes || []).map((t) => String(t || "").toLowerCase()));
  const blocks = Array.isArray(slide?.blocks) ? slide.blocks : [];
  let count = 0;
  for (const block of blocks) {
    const bt = normalizedBlockType(block);
    if (!bt || bt === "title") continue;
    if (visualSet.has(bt)) continue;
    count += 1;
  }
  return count;
}

function hasEmphasisSignal(slide) {
  const blocks = Array.isArray(slide?.blocks) ? slide.blocks : [];
  return blocks.some((block) => {
    const bt = normalizedBlockType(block);
    if (bt === "title") return false;
    const emphasis = block?.emphasis;
    if (Array.isArray(emphasis) && emphasis.some((item) => String(item ?? "").trim())) return true;
    const text = blockPlainText(block);
    return /\d+(?:\.\d+)?%?/.test(text);
  });
}

export function normalizeRenderInput(input) {
  const payload = input && typeof input === "object" ? { ...input } : {};
  const slides = asArray(payload.slides);
  const theme = normalizeTheme(payload);
  const themeRecipe = normalizeThemeRecipeValue(
    payload.theme_recipe
      ?? payload.themeRecipe
      ?? payload?.design_spec?.visual?.theme_recipe,
    "auto",
  );
  const tone = normalizeToneValue(
    payload.tone
      ?? payload.theme_tone
      ?? payload?.design_spec?.visual?.tone,
    "auto",
  );
  const designSpec = normalizeDesignSpec(payload, theme, themeRecipe, tone);
  const requestedDeckTemplate = asText(payload.template_family ?? payload.template_id, "auto");
  const deckTemplateProfiles = getTemplateProfiles(requestedDeckTemplate);
  const normalizedSlides = slides.map((slide, idx) =>
    normalizeSlide(
      slide,
      idx,
      slides.length,
      requestedDeckTemplate,
      asText(payload.visual_density, "balanced"),
      themeRecipe,
      tone,
    ),
  );
  const presentationContractV2 = buildPresentationContractV2({
    title: asText(payload.title, "Presentation"),
    designSpec,
    slides: normalizedSlides,
  });
  return {
    ...payload,
    title: asText(payload.title, "Presentation"),
    theme,
    theme_recipe: themeRecipe,
    tone,
    minimax_palette_key: theme.palette,
    minimax_style_variant: theme.style,
    template_family: deckTemplateProfiles.template_id,
    template_id: asText(payload.template_id, deckTemplateProfiles.template_id),
    skill_profile: asText(payload.skill_profile, deckTemplateProfiles.skill_profile),
    hardness_profile: asText(payload.hardness_profile, deckTemplateProfiles.hardness_profile),
    schema_profile: asText(payload.schema_profile, deckTemplateProfiles.schema_profile),
    contract_profile: asText(payload.contract_profile, deckTemplateProfiles.contract_profile),
    quality_profile: asText(payload.quality_profile, deckTemplateProfiles.quality_profile),
    design_spec: designSpec,
    presentation_contract_v2: presentationContractV2,
    slides: normalizedSlides,
  };
}

export function validateRenderInput(payload) {
  const errors = [];
  if (!payload || typeof payload !== "object") {
    return { ok: false, errors: ["payload must be an object"] };
  }
  if (!asText(payload.title)) {
    errors.push("title is required");
  }
  if (!asText(payload.theme_recipe)) {
    errors.push("theme_recipe is required");
  }
  if (!asText(payload.tone)) {
    errors.push("tone is required");
  }
  const theme = payload.theme;
  if (!theme || typeof theme !== "object") {
    errors.push("theme must be an object");
  } else {
    if (!asText(theme.palette)) errors.push("theme.palette is required");
    if (!asText(theme.style)) errors.push("theme.style is required");
  }
  if (!Array.isArray(payload.slides)) {
    errors.push("slides must be an array");
    return { ok: false, errors };
  }
  if (!asText(payload.template_id)) errors.push("template_id is required");
  if (!asText(payload.skill_profile)) errors.push("skill_profile is required");
  if (!asText(payload.hardness_profile)) errors.push("hardness_profile is required");
  if (!asText(payload.schema_profile)) errors.push("schema_profile is required");
  if (!asText(payload.contract_profile)) errors.push("contract_profile is required");
  if (!asText(payload.quality_profile)) errors.push("quality_profile is required");
  if (!payload.design_spec || typeof payload.design_spec !== "object" || Array.isArray(payload.design_spec)) {
    errors.push("design_spec must be an object");
  } else {
    if (!payload.design_spec.colors || typeof payload.design_spec.colors !== "object") {
      errors.push("design_spec.colors must be an object");
    }
    if (!payload.design_spec.typography || typeof payload.design_spec.typography !== "object") {
      errors.push("design_spec.typography must be an object");
    }
    if (!payload.design_spec.spacing || typeof payload.design_spec.spacing !== "object") {
      errors.push("design_spec.spacing must be an object");
    }
    if (!payload.design_spec.visual || typeof payload.design_spec.visual !== "object") {
      errors.push("design_spec.visual must be an object");
    }
  }
  const archetypeCatalog = getArchetypeCatalog();
  const archetypeSet = new Set(archetypeCatalog.archetypes || []);
  const contractV2 = payload.presentation_contract_v2;
  if (!contractV2 || typeof contractV2 !== "object" || Array.isArray(contractV2)) {
    errors.push("presentation_contract_v2 must be an object");
  } else {
    if (!Array.isArray(contractV2.slides)) {
      errors.push("presentation_contract_v2.slides must be an array");
    } else if (contractV2.slides.length !== payload.slides.length) {
      errors.push("presentation_contract_v2.slides length must match payload.slides length");
    } else {
      contractV2.slides.forEach((row, idx) => {
        if (!row || typeof row !== "object") {
          errors.push(`presentation_contract_v2.slides[${idx}] must be an object`);
          return;
        }
        if (!asText(row.slide_id)) {
          errors.push(`presentation_contract_v2.slides[${idx}].slide_id is required`);
        }
        const archetype = asText(row.archetype).toLowerCase();
        if (!archetype) {
          errors.push(`presentation_contract_v2.slides[${idx}].archetype is required`);
        } else if (!archetypeSet.has(archetype)) {
          errors.push(`presentation_contract_v2.slides[${idx}].archetype is unknown: ${archetype}`);
        }
        const archetypePlan = row.archetype_plan;
        if (!archetypePlan || typeof archetypePlan !== "object" || Array.isArray(archetypePlan)) {
          errors.push(`presentation_contract_v2.slides[${idx}].archetype_plan must be an object`);
        } else {
          if (asText(archetypePlan.selected).toLowerCase() !== archetype) {
            errors.push(`presentation_contract_v2.slides[${idx}].archetype_plan.selected must equal archetype`);
          }
          const conf = asNumber(archetypePlan.confidence, -1);
          if (!(conf >= 0 && conf <= 1)) {
            errors.push(`presentation_contract_v2.slides[${idx}].archetype_plan.confidence must be in [0,1]`);
          }
          if (!Array.isArray(archetypePlan.candidates) || !archetypePlan.candidates.length) {
            errors.push(`presentation_contract_v2.slides[${idx}].archetype_plan.candidates must be a non-empty array`);
          }
        }
        const contentChannel = row.content_channel;
        if (!contentChannel || typeof contentChannel !== "object" || Array.isArray(contentChannel)) {
          errors.push(`presentation_contract_v2.slides[${idx}].content_channel must be an object`);
        } else {
          if (!asText(contentChannel.title)) {
            errors.push(`presentation_contract_v2.slides[${idx}].content_channel.title is required`);
          }
          if (!asText(contentChannel.assertion)) {
            errors.push(`presentation_contract_v2.slides[${idx}].content_channel.assertion is required`);
          }
          if (!Array.isArray(contentChannel.evidence)) {
            errors.push(`presentation_contract_v2.slides[${idx}].content_channel.evidence must be an array`);
          }
          if (!Array.isArray(contentChannel.data_points)) {
            errors.push(`presentation_contract_v2.slides[${idx}].content_channel.data_points must be an array`);
          }
          if (!asText(contentChannel.media_intent)) {
            errors.push(`presentation_contract_v2.slides[${idx}].content_channel.media_intent is required`);
          }
        }
        const visualChannel = row.visual_channel;
        if (!visualChannel || typeof visualChannel !== "object" || Array.isArray(visualChannel)) {
          errors.push(`presentation_contract_v2.slides[${idx}].visual_channel must be an object`);
        } else {
          if (!asText(visualChannel.layout)) {
            errors.push(`presentation_contract_v2.slides[${idx}].visual_channel.layout is required`);
          }
          if (!asText(visualChannel.render_path)) {
            errors.push(`presentation_contract_v2.slides[${idx}].visual_channel.render_path is required`);
          }
          if (!Array.isArray(visualChannel.component_slots)) {
            errors.push(`presentation_contract_v2.slides[${idx}].visual_channel.component_slots must be an array`);
          }
        }
        const semantic = row.semantic_constraints;
        if (!semantic || typeof semantic !== "object" || Array.isArray(semantic)) {
          errors.push(`presentation_contract_v2.slides[${idx}].semantic_constraints must be an object`);
        } else {
          if (typeof semantic.media_required !== "boolean") {
            errors.push(`presentation_contract_v2.slides[${idx}].semantic_constraints.media_required must be boolean`);
          }
          if (typeof semantic.chart_required !== "boolean") {
            errors.push(`presentation_contract_v2.slides[${idx}].semantic_constraints.chart_required must be boolean`);
          }
          if (!asText(semantic.diagram_type)) {
            errors.push(`presentation_contract_v2.slides[${idx}].semantic_constraints.diagram_type is required`);
          }
        }
      });
    }
  }

  payload.slides.forEach((slide, idx) => {
    if (!slide || typeof slide !== "object") {
      errors.push(`slides[${idx}] must be an object`);
      return;
    }
    const pageNumber = Number(slide.page_number);
    if (!Number.isFinite(pageNumber) || pageNumber <= 0) {
      errors.push(`slides[${idx}].page_number must be a positive number`);
    }
    if (!asText(slide.slide_type)) {
      errors.push(`slides[${idx}].slide_type is required`);
    }
    if (!asText(slide.page_role)) {
      errors.push(`slides[${idx}].page_role is required`);
    }
    if (!asText(slide.archetype)) {
      errors.push(`slides[${idx}].archetype is required`);
    } else {
      const archetype = asText(slide.archetype).toLowerCase();
      if (!archetypeSet.has(archetype)) {
        errors.push(`slides[${idx}].archetype is unknown: ${archetype}`);
      }
    }
    if (!asText(slide.layout_grid)) {
      errors.push(`slides[${idx}].layout_grid is required`);
    }
    if (!asText(slide.template_id)) {
      errors.push(`slides[${idx}].template_id is required`);
    }
    if (!asText(slide.skill_profile)) {
      errors.push(`slides[${idx}].skill_profile is required`);
    }
    const hardness = asText(slide.hardness_profile).toLowerCase();
    if (!hardness) {
      errors.push(`slides[${idx}].hardness_profile is required`);
    } else if (!["minimal", "balanced", "strict"].includes(hardness)) {
      errors.push(`slides[${idx}].hardness_profile must be minimal|balanced|strict`);
    }
    if (!asText(slide.schema_profile)) {
      errors.push(`slides[${idx}].schema_profile is required`);
    }
    if (!asText(slide.contract_profile)) {
      errors.push(`slides[${idx}].contract_profile is required`);
    }
    if (!asText(slide.quality_profile)) {
      errors.push(`slides[${idx}].quality_profile is required`);
    }
    if (!asText(slide.theme_recipe)) {
      errors.push(`slides[${idx}].theme_recipe is required`);
    }
    if (!asText(slide.tone)) {
      errors.push(`slides[${idx}].tone is required`);
    }
    const renderPath = asText(slide.render_path, "pptxgenjs").toLowerCase();
    if (!["pptxgenjs", "svg", "png_fallback"].includes(renderPath)) {
      errors.push(`slides[${idx}].render_path must be pptxgenjs|svg|png_fallback`);
    }
    if (!hasRenderableContent(slide)) {
      errors.push(`slides[${idx}] must include blocks, elements, markdown, or imageUrl`);
    }
    if (isContentSlide(slide) && Array.isArray(slide.blocks) && slide.blocks.length > 0) {
      const contract = getContractProfile(normalizedContractProfile(slide));
      for (const requiredType of contract.required_block_types || []) {
        if (countByTypes(slide, [requiredType]) <= 0) {
          errors.push(`slides[${idx}] content contract: ${requiredType} block is required`);
        }
      }
      for (const group of contract.required_one_of_groups || []) {
        if (countByTypes(slide, group) <= 0) {
          errors.push(
            `slides[${idx}] content contract: one of [${group.join("|")}] is required`,
          );
        }
      }
      if (countTextBlocks(slide, contract.visual_anchor_types || []) < Number(contract.min_text_blocks || 0)) {
        errors.push(`slides[${idx}] content contract: min_text_blocks=${contract.min_text_blocks} not satisfied`);
      }
      if (countByTypes(slide, contract.visual_anchor_types || []) < Number(contract.min_visual_blocks || 0)) {
        errors.push(`slides[${idx}] content contract: visual anchor requirement not satisfied`);
      }
      if (contract.forbid_duplicate_text && hasDuplicateBlockText(slide)) {
        errors.push(`slides[${idx}] content contract: duplicate non-title block text detected`);
      }
      if (contract.require_emphasis_signal && !hasEmphasisSignal(slide)) {
        errors.push(`slides[${idx}] content contract: emphasis signal is required (emphasis[] or numeric focus)`);
      }
    }
    if (Array.isArray(slide.blocks)) {
      slide.blocks.forEach((block, blockIdx) => {
        if (!block || typeof block !== "object") {
          errors.push(`slides[${idx}].blocks[${blockIdx}] must be an object`);
          return;
        }
        if (!asText(block.block_type)) {
          errors.push(`slides[${idx}].blocks[${blockIdx}].block_type is required`);
        }
        if (!asText(block.card_id)) {
          errors.push(`slides[${idx}].blocks[${blockIdx}].card_id is required`);
        }
        if (block.content === undefined || block.content === null || (typeof block.content === "string" && !block.content.trim())) {
          errors.push(`slides[${idx}].blocks[${blockIdx}].content is required`);
        }
      });
    }
  });

  return { ok: errors.length === 0, errors };
}
