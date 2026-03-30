import { getContractProfile, getTemplateProfiles } from "./templates/template-profiles.mjs";
import { resolveTemplateFamilyForSlide } from "./templates/template-registry.mjs";

export const RENDER_INPUT_SCHEMA = {
  title: "string",
  theme: {
    palette: "string",
    style: "string",
  },
  design_spec: "object",
  template_id: "string",
  skill_profile: "string",
  hardness_profile: "string",
  schema_profile: "string",
  contract_profile: "string",
  quality_profile: "string",
  slides: [
    {
      page_number: "number",
      slide_type: "string",
      layout_grid: "string",
      template_id: "string",
      skill_profile: "string",
      hardness_profile: "string",
      schema_profile: "string",
      contract_profile: "string",
      quality_profile: "string",
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

function normalizeRenderPath(value) {
  const normalized = asText(value, "").toLowerCase();
  if (["pptxgenjs", "svg", "png_fallback"].includes(normalized)) return normalized;
  return "pptxgenjs";
}

function normalizeDesignSpec(payload, theme) {
  const raw = payload?.design_spec;
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    return {
      ...raw,
      colors: raw.colors && typeof raw.colors === "object" ? raw.colors : {},
      typography: raw.typography && typeof raw.typography === "object" ? raw.typography : {},
      spacing: raw.spacing && typeof raw.spacing === "object" ? raw.spacing : {},
      visual: raw.visual && typeof raw.visual === "object" ? raw.visual : {},
    };
  }
  const styleRecipe = asText(theme?.style, "soft").toLowerCase();
  return {
    colors: {},
    typography: {},
    spacing: {},
    visual: {
      style_recipe: styleRecipe,
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

function normalizeSlide(raw, idx, total, deckTemplateId = "auto", deckDesiredDensity = "balanced") {
  const source = raw && typeof raw === "object" ? { ...raw } : {};
  const slideType = inferSlideType(source, idx, total);
  const layoutGrid = inferLayoutGrid(source, slideType);
  const blocks = asArray(source.blocks).map((item, blockIdx) => normalizeBlock(item, blockIdx));
  const requestedTemplate = asText(source.template_family ?? source.template_id, deckTemplateId || "auto");
  const templateLock = Boolean(source.template_lock);
  const resolvedTemplate = resolveTemplateFamilyForSlide({
    sourceSlide: source,
    requestedTemplateFamily: templateLock ? (requestedTemplate || "auto") : "auto",
    explicitType: slideType,
    layoutGrid,
    desiredDensity: asText(source.content_density, deckDesiredDensity || "balanced"),
  });
  const profiles = getTemplateProfiles(resolvedTemplate);
  return {
    ...source,
    page_number: Number(source.page_number ?? idx + 1),
    slide_type: slideType,
    layout_grid: layoutGrid,
    template_family: profiles.template_id,
    template_id: templateLock ? asText(source.template_id, profiles.template_id) : profiles.template_id,
    skill_profile: templateLock ? asText(source.skill_profile, profiles.skill_profile) : profiles.skill_profile,
    hardness_profile: templateLock
      ? asText(source.hardness_profile, profiles.hardness_profile)
      : profiles.hardness_profile,
    schema_profile: templateLock ? asText(source.schema_profile, profiles.schema_profile) : profiles.schema_profile,
    contract_profile: templateLock
      ? asText(source.contract_profile, profiles.contract_profile)
      : profiles.contract_profile,
    quality_profile: templateLock
      ? asText(source.quality_profile, profiles.quality_profile)
      : profiles.quality_profile,
    render_path: normalizeRenderPath(source.render_path),
    blocks,
    bg_style: asText(source.bg_style, "light"),
    image_keywords: asArray(source.image_keywords).map((v) => asText(v)).filter(Boolean),
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
  const designSpec = normalizeDesignSpec(payload, theme);
  const requestedDeckTemplate = asText(payload.template_family ?? payload.template_id, "auto");
  const deckTemplateProfiles = getTemplateProfiles(requestedDeckTemplate);
  const normalizedSlides = slides.map((slide, idx) =>
    normalizeSlide(
      slide,
      idx,
      slides.length,
      requestedDeckTemplate,
      asText(payload.visual_density, "balanced"),
    ),
  );
  return {
    ...payload,
    title: asText(payload.title, "Presentation"),
    theme,
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
