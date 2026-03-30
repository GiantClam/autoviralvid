import {
  normalizeGeneratorMode,
  normalizeLayoutGrid,
  normalizePageType,
  normalizeRetryScope,
  normalizeTheme,
  validateOfficialInputContract,
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

function stripHtml(value) {
  return String(value || "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(p|div|li)>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeTextKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, " ")
    .replace(/[^0-9a-z\u4e00-\u9fff%+.-]/g, "");
}

function isGenericSlideTitle(value) {
  const text = String(value || "").trim();
  return /^slide\s*\d+$/i.test(text);
}

function sanitizeLine(value) {
  const raw = stripHtml(value);
  if (!raw) return "";
  return raw
    // Keep the pattern ASCII-safe to avoid source encoding issues.
    .replace(/^(?:\u8865\u5145\u8981\u70b9|supporting point)\s*[:：-]\s*/i, "")
    .replace(/^[\s\-*+\u2022\u00b7\u25cf\u25e6\u25aa\u25ab]+\s*/g, "")
    .trim();
}

function clampLine(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  const hasCjk = /[\u4e00-\u9fff]/.test(text);
  const maxLen = hasCjk ? 42 : 84;
  if (text.length <= maxLen) return text;
  return `${text.slice(0, Math.max(1, maxLen - 1))}…`;
}

function splitCandidateLines(text) {
  const cleaned = sanitizeLine(text);
  if (!cleaned) return [];
  return cleaned
    .split(/[\r\n;锛涖€??锛侊紵]+/)
    .map((line) => clampLine(line))
    .filter(Boolean);
}

function isVisualType(type) {
  return new Set(["image", "chart", "kpi", "workflow", "diagram", "table"]).has(String(type || ""));
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

function inferLayoutGrid(slide) {
  return (
    normalizeLayoutGrid(
      slide?.layout_grid
        || slide?.layout
        || "",
      "",
    )
    || normalizeLayoutGrid(
      slide?.slide_type
        || slide?.slideType
        || slide?.subtype
        || "",
      "",
    )
    || ""
  );
}

function inferSubtypeHint(slide) {
  const direct = normalizeKey(
    slide?.subtype
      || slide?.slide_type
      || slide?.slideType
      || "",
  );
  const pageType = normalizePageType(direct, "");
  if (!direct || pageType) return "";
  return direct;
}

function extractTextBlocks(slide, slideId) {
  const sourceBlocks = Array.isArray(slide?.blocks) ? slide.blocks : [];
  const titleKey = normalizeTextKey(slide?.title || "");
  const seen = new Set();
  const out = [];
  if (sourceBlocks.length > 0) {
    for (let i = 0; i < sourceBlocks.length; i += 1) {
      const block = sourceBlocks[i];
      if (!block || typeof block !== "object") continue;
      const type = normalizeKey(block.block_type || block.type || "text") || "text";
      const rawText = blockText(block);
      const content = clampLine(sanitizeLine(rawText));
      const contentKey = normalizeTextKey(content);
      if (!content && !isVisualType(type)) continue;
      if (contentKey && contentKey === titleKey && type !== "title") continue;
      const dedupeKey = `${type}:${contentKey}`;
      if (contentKey && seen.has(dedupeKey)) continue;
      if (contentKey) seen.add(dedupeKey);
      const mapped = {
        block_id: stableBlockId(block, slideId, i),
        type,
        content: content || clampLine(String(slide?.title || "Visual")),
      };
      const sourceContent = block?.content && typeof block.content === "object" ? block.content : {};
      const data = block?.data && typeof block.data === "object" ? { ...block.data } : {};
      if (isVisualType(type)) {
        const url =
          sourceContent.url
          || sourceContent.src
          || sourceContent.imageUrl
          || sourceContent.image_url
          || data.url
          || data.src
          || data.imageUrl
          || data.image_url
          || "";
        if (url) {
          data.url = String(url);
          data.imageUrl = String(url);
        }
      }
      if (block?.data && typeof block.data === "object") mapped.data = block.data;
      if (Object.keys(data).length > 0) mapped.data = data;
      out.push(mapped);
      if (out.length >= 12) break;
    }
    return out;
  }

  const elements = Array.isArray(slide?.elements) ? slide.elements : [];
  let titleAssigned = false;
  for (let i = 0; i < elements.length; i += 1) {
    const element = elements[i];
    if (!element || typeof element !== "object") continue;
    const type = normalizeKey(element.type);
    if (type === "text") {
      const lines = splitCandidateLines(element.content);
      for (const line of lines) {
        const lineKey = normalizeTextKey(line);
        if (!lineKey || lineKey === titleKey) continue;
        const top = Number(element.top || 0);
        const fontSize = Number(element?.style?.fontSize || 0);
        const htmlRaw = String(element.content || "");
        const probablyTitle =
          !titleAssigned
          && !isGenericSlideTitle(line)
          && (top < 160 || fontSize >= 26 || /<b>/i.test(htmlRaw));
        const mappedType = probablyTitle ? "title" : "body";
        const dedupeKey = `${mappedType}:${lineKey}`;
        if (seen.has(dedupeKey)) continue;
        seen.add(dedupeKey);
        out.push({
          block_id: stableBlockId(element, slideId, i),
          type: mappedType,
          content: line,
        });
        if (probablyTitle) titleAssigned = true;
        if (out.length >= 12) break;
      }
    } else if (type === "image") {
      const data = {};
      const url = String(element.src || element.url || element.imageUrl || "").trim();
      if (url) {
        data.url = url;
        data.imageUrl = url;
      }
      out.push({
        block_id: stableBlockId(element, slideId, i),
        type: "image",
        content: clampLine(String(slide?.title || "Visual")),
        ...(Object.keys(data).length > 0 ? { data } : {}),
      });
    }
    if (out.length >= 12) break;
  }
  return out;
}

export function toOfficialInput(input) {
  const slides = Array.isArray(input?.slides) ? input.slides : [];
  const generatorMode = normalizeGeneratorMode(input?.generator_mode, "official");
  const retryScope = normalizeRetryScope(input?.retry_scope || "deck", "deck");
  const theme = normalizeTheme(input?.theme || input?.minimax_theme || {});

  const officialSlides = slides.map((slide, index) => {
    const slideId = stableSlideId(slide, index);
    const blocks = extractTextBlocks(slide, slideId);
    const layoutGrid = inferLayoutGrid(slide);
    const subtypeHint = inferSubtypeHint(slide);
    const explicitTitle = sanitizeLine(String(slide?.title || ""));
    const firstTitleBlock =
      blocks.find((block) => String(block?.type || "").trim().toLowerCase() === "title") || null;
    const inferredTitle = sanitizeLine(firstTitleBlock?.content || "");
    const resolvedTitle = clampLine(
      (explicitTitle && !isGenericSlideTitle(explicitTitle) ? explicitTitle : inferredTitle)
      || explicitTitle
      || `Slide ${index + 1}`,
    );
    return {
      slide_id: slideId,
      page_type: inferPageType(slide, index, slides.length),
      ...(layoutGrid ? { layout_grid: layoutGrid } : {}),
      ...(subtypeHint ? { subtype: subtypeHint } : {}),
      title: resolvedTitle,
      blocks,
      retry_scope: retryScope === "deck" ? "slide" : retryScope,
    };
  });

  const candidate = {
    deck_id: String(input?.deck_id || "").trim() || undefined,
    title: String(input?.title || "Presentation"),
    author: String(input?.author || "AutoViralVid"),
    generator_mode: generatorMode,
    retry_scope: retryScope,
    original_style: Boolean(input?.original_style ?? false),
    disable_local_style_rewrite: Boolean(
      input?.disable_local_style_rewrite ?? false,
    ),
    theme,
    slides: officialSlides,
  };
  const contract = validateOfficialInputContract(candidate, { strict: false });
  if (!contract.ok) {
    throw new Error(
      `official_input_contract_invalid: ${contract.errors.slice(0, 6).join("; ")}`,
    );
  }
  return contract.normalized;
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
  const retryScope = normalizeRetryScope(output?.retry_scope || "deck", "deck");
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
      title: String(slide?.title || "").trim(),
      slide_type: mapBackSlideType(slide),
      retry_scope: normalizeRetryScope(slide?.retry_scope || retryScope || "deck", "deck"),
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
