import {
  normalizeGeneratorMode,
  normalizePageType,
  normalizeTheme,
} from "./official_skill_contract.mjs";

function normalizeKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function stableSlideId(slide, index) {
  const candidate = slide?.slide_id ?? slide?.id ?? slide?.page_number;
  const text = String(candidate || "").trim();
  return text || `slide-${index + 1}`;
}

function stableBlockId(block, slideId, index) {
  const candidate = block?.block_id ?? block?.id;
  const text = String(candidate || "").trim();
  return text || `${slideId}-block-${index + 1}`;
}

function blockText(block) {
  const content = block?.content;
  if (typeof content === "string") return content.trim();
  if (content && typeof content === "object") {
    const parts = [];
    for (const key of ["title", "body", "text", "label", "caption", "description"]) {
      const value = String(content[key] || "").trim();
      if (value) parts.push(value);
    }
    if (parts.length) return parts.join(" ");
  }
  const data = block?.data;
  if (data && typeof data === "object") {
    const parts = [];
    for (const key of ["title", "label", "description"]) {
      const value = String(data[key] || "").trim();
      if (value) parts.push(value);
    }
    if (parts.length) return parts.join(" ");
  }
  return "";
}

function inferPageType(slide, index, total) {
  const explicit = normalizePageType(
    slide?.page_type ||
      slide?.slide_type ||
      slide?.slideType ||
      slide?.subtype ||
      "",
    "",
  );
  if (explicit) return explicit;
  if (index === 0) return "cover";
  if (index === total - 1) return "summary";
  return "content";
}

function extractTextBlocks(slide, slideId) {
  const sourceBlocks = Array.isArray(slide?.blocks) ? slide.blocks : [];
  if (sourceBlocks.length > 0) {
    const blocks = [];
    for (let i = 0; i < sourceBlocks.length; i += 1) {
      const block = sourceBlocks[i];
      if (!block || typeof block !== "object") continue;
      const type = normalizeKey(block.block_type || block.type || "text") || "text";
      const content = blockText(block);
      if (!content) continue;
      const mapped = {
        block_id: stableBlockId(block, slideId, i),
        type,
        content,
      };
      if (block?.data && typeof block.data === "object") mapped.data = block.data;
      blocks.push(mapped);
    }
    return blocks;
  }

  const elements = Array.isArray(slide?.elements) ? slide.elements : [];
  const blocks = [];
  for (let i = 0; i < elements.length; i += 1) {
    const element = elements[i];
    if (!element || typeof element !== "object") continue;
    const type = normalizeKey(element.type);
    if (type !== "text") continue;
    const content = String(element.content || "").trim();
    if (!content) continue;
    blocks.push({
      block_id: stableBlockId(element, slideId, i),
      type: "text",
      content,
    });
  }
  return blocks;
}

export function toOfficialInput(input) {
  const slides = Array.isArray(input?.slides) ? input.slides : [];
  const generatorMode = normalizeGeneratorMode(input?.generator_mode, "official");
  const retryScope = normalizeKey(input?.retry_scope || "deck") || "deck";
  const theme = normalizeTheme(input?.theme || input?.minimax_theme || {});

  const officialSlides = slides.map((slide, index) => {
    const slideId = stableSlideId(slide, index);
    const blocks = extractTextBlocks(slide, slideId);
    return {
      slide_id: slideId,
      page_type: inferPageType(slide, index, slides.length),
      title: String(slide?.title || `Slide ${index + 1}`),
      blocks,
      retry_scope: retryScope === "deck" ? "slide" : retryScope,
    };
  });

  return {
    deck_id: String(input?.deck_id || "").trim() || undefined,
    title: String(input?.title || "Presentation"),
    author: String(input?.author || "AutoViralVid"),
    generator_mode: generatorMode,
    retry_scope: retryScope,
    original_style: Boolean(input?.original_style ?? true),
    disable_local_style_rewrite: Boolean(
      input?.disable_local_style_rewrite ?? true,
    ),
    theme,
    slides: officialSlides,
  };
}

function mapBackSlideType(slide) {
  const pageType = normalizePageType(
    slide?.page_type || slide?.slide_type || "content",
  );
  if (pageType === "section-divider") return "section";
  return pageType;
}

export function fromOfficialOutput(output) {
  const slides = Array.isArray(output?.slides) ? output.slides : [];
  const retryScope = normalizeKey(output?.retry_scope || "deck") || "deck";
  const mappedSlides = slides.map((slide, index) => {
    const slideId = stableSlideId(slide, index);
    const blocks = Array.isArray(slide?.blocks) ? slide.blocks : [];
    const elements = blocks.map((block, blockIndex) => ({
      block_id: stableBlockId(block, slideId, blockIndex),
      type: normalizeKey(block?.type || "text") || "text",
      content: String(block?.content || ""),
      data: block?.data && typeof block.data === "object" ? block.data : undefined,
    }));

    return {
      slide_id: slideId,
      title: String(slide?.title || `Slide ${index + 1}`),
      slide_type: mapBackSlideType(slide),
      retry_scope: normalizeKey(slide?.retry_scope || retryScope || "deck") || "deck",
      elements,
    };
  });

  return {
    deck_id: String(output?.deck_id || "").trim() || undefined,
    generator_mode: normalizeGeneratorMode(output?.generator_mode, "official"),
    retry_scope: retryScope,
    slides: mappedSlides,
    generator_meta:
      output?.generator_meta && typeof output.generator_meta === "object"
        ? output.generator_meta
        : {},
    errors: Array.isArray(output?.errors) ? output.errors : [],
  };
}
