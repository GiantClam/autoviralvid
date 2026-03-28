/**
 * Shared heuristics for MiniMax PPT style/palette/subtype selection.
 * Keep this module deterministic so it can be tested via harness.
 */

export function normalizeKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function pick(obj, keys, fallback = "") {
  for (const key of keys) {
    if (obj && obj[key] !== undefined && obj[key] !== null) return obj[key];
  }
  return fallback;
}

function stripHtml(input) {
  return String(input || "")
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/\s+/g, " ")
    .trim();
}

function blockType(block) {
  return String(block?.block_type || block?.type || "").trim().toLowerCase();
}

export function inferSubtype(slide) {
  const explicit = normalizeKey(
    pick(slide, ["page_type", "pageType", "slide_type", "slideType", "subtype"], ""),
  );
  if (
    [
      "cover",
      "toc",
      "summary",
      "contact",
      "section",
      "table",
      "comparison",
      "timeline",
      "data",
    ].includes(explicit)
  ) {
    if (explicit === "toc" || explicit === "cover" || explicit === "summary" || explicit === "contact") {
      return "content";
    }
    return explicit;
  }

  const title = stripHtml(String(pick(slide, ["title"], ""))).toLowerCase();
  const elements = Array.isArray(slide?.elements) ? slide.elements : [];
  const blocks = Array.isArray(slide?.blocks) ? slide.blocks : [];
  const hasElementType = (type) =>
    elements.some((el) => String(el?.type || "").toLowerCase() === String(type).toLowerCase());
  const hasBlockType = (type) => blocks.some((block) => blockType(block) === String(type).toLowerCase());
  if (/(part|section|\u7ae0\u8282|\u90e8\u5206|\u5206\u7bc7)/.test(title)) return "section";
  if (hasElementType("table") || hasBlockType("table")) return "table";
  if (/(\u5bf9\u6bd4|\u6bd4\u8f83|vs|versus|\u4f18\u52bf|\u5dee\u5f02)/.test(title)) return "comparison";
  if (hasElementType("chart") || hasBlockType("chart") || hasBlockType("kpi")) return "data";
  if (
    /(\u6d41\u7a0b|\u9636\u6bb5|\u8def\u7ebf\u56fe|roadmap|timeline|\u6b65\u9aa4|\u91cc\u7a0b\u7891|\u5b9e\u65bd\u8def\u5f84)/.test(
      title,
    )
  ) {
    return "timeline";
  }
  if (/(\u6570\u636e|\u589e\u957f|\u8f6c\u5316|roi|\u6548\u7387|\u6307\u6807)/.test(title)) return "data";
  if (hasElementType("image") || hasBlockType("image")) return "mixed";
  return "content";
}

export function selectStyle(styleInput, styleHint, topicText, preserveOriginal = false) {
  const normalized = normalizeKey(styleInput);
  if (["sharp", "soft", "rounded", "pill"].includes(normalized)) return normalized;
  if (preserveOriginal) return "soft";

  if (styleHint === "creative") return "pill";
  if (styleHint === "education") return "rounded";
  if (styleHint === "professional") return "soft";

  const topic = String(topicText || "").toLowerCase();
  if (/(\u4f01\u4e1a|\u516c\u53f8|\u5546\u4e1a|\u5236\u9020|\u5de5\u4e1a|\u884c\u4e1a|\u65b9\u6848|\u6c47\u62a5|\u62a5\u544a|business|enterprise|industry)/.test(topic)) return "sharp";
  if (/(finance|\u8d22\u62a5|\u5b63\u5ea6|\u7ecf\u8425|analysis|report)/.test(topic)) return "sharp";
  if (/(education|\u8bfe\u7a0b|\u57f9\u8bad|school)/.test(topic)) return "rounded";
  if (/(brand|fashion|creative|marketing|\u8bbe\u8ba1|\u54c1\u724c)/.test(topic)) return "pill";
  return "soft";
}

export function selectPalette(paletteInput, topicText, preserveOriginal = false) {
  const normalized = normalizeKey(paletteInput);
  if (normalized && normalized !== "auto") return normalized;
  if (preserveOriginal) return "business_authority";

  const topic = String(topicText || "").toLowerCase();
  if (/(\u4f01\u4e1a|\u516c\u53f8|\u5236\u9020|\u5de5\u4e1a|\u884c\u4e1a|\u5546\u4e1a|business|enterprise|industry)/.test(topic)) return "business_authority";
  if (/(finance|\u7ecf\u8425|\u5b63\u5ea6|analysis|report|saas|business)/.test(topic)) return "business_authority";
  if (/(health|\u533b\u7597|wellness)/.test(topic)) return "modern_wellness";
  if (/(education|\u8bfe\u7a0b|\u57f9\u8bad|chart)/.test(topic)) return "education_charts";
  if (/(eco|forest|\u73af\u5883|esg)/.test(topic)) return "forest_eco";
  if (/(luxury|\u9ad8\u7aef|premium)/.test(topic)) return "platinum_white_gold";
  if (/(ai|cloud|tech|\u79d1\u6280)/.test(topic)) return "pure_tech_blue";
  return "luxury_mysterious";
}
