import { getTemplateSpec } from "./template-specs.mjs";
import { getTemplatePreferredLayout } from "./template-catalog.mjs";

import { createChart } from "../chart-factory.mjs";
import { renderBentoSlide } from "../card-renderers.mjs";

const SLIDE_W = 10;
const SLIDE_H = 5.625;

function clampRect(x, y, w, h, inset = 0) {
  const safeInset = Math.max(0, Number(inset) || 0);
  const safeX = Math.min(Math.max(Number(x) || 0, safeInset), SLIDE_W - safeInset - 0.2);
  const safeY = Math.min(Math.max(Number(y) || 0, safeInset), SLIDE_H - safeInset - 0.2);
  const maxW = Math.max(0.2, SLIDE_W - safeInset - safeX);
  const maxH = Math.max(0.2, SLIDE_H - safeInset - safeY);
  return {
    x: safeX,
    y: safeY,
    w: Math.max(0.2, Math.min(Number(w) || 0.2, maxW)),
    h: Math.max(0.2, Math.min(Number(h) || 0.2, maxH)),
  };
}

function truncate(text, max = 80) {
  const s = String(text || "").trim();
  if (s.length <= max) return s;
  return `${s.slice(0, max - 1)}...`;
}

function fitFont(base, text, min = 12) {
  const len = String(text || "").trim().length;
  if (len <= 24) return base;
  const shrink = Math.ceil((len - 24) / 10);
  return Math.max(min, base - shrink);
}

function splitText(value, max = 8) {
  const list = String(value || "")
    .split(/[;；,\n，。.!?]+/)
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  const out = [];
  const seen = new Set();
  for (const item of list) {
    const key = item.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
    if (out.length >= max) break;
  }
  return out;
}

function normalizeTextKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, " ")
    .replace(/[^0-9a-z\u4e00-\u9fff%+.-]/g, "");
}

function pickSecondaryHeading(primary, points = [], fallback = "Focus") {
  const primaryKey = normalizeTextKey(primary);
  for (const item of points) {
    const text = String(item || "").trim();
    if (!text) continue;
    const key = normalizeTextKey(text);
    if (!key || key === primaryKey) continue;
    return text;
  }
  return fallback;
}

function blockType(block) {
  return String(block?.block_type || block?.type || "").trim().toLowerCase();
}

function blockText(block) {
  const content = block?.content;
  if (typeof content === "string") return content.trim();
  if (content && typeof content === "object") {
    const parts = [];
    for (const key of ["title", "body", "text", "label", "caption", "description"]) {
      const v = String(content[key] || "").trim();
      if (v) parts.push(v);
    }
    if (parts.length) return parts.join(" ");
  }
  const data = block?.data;
  if (data && typeof data === "object") {
    for (const key of ["label", "title", "description"]) {
      const v = String(data[key] || "").trim();
      if (v) return v;
    }
  }
  return "";
}

function safeBulletsFromArgs(args, max = 12) {
  const explicit = Array.isArray(args?.bullets) ? args.bullets : [];
  const sourceSlide = args?.sourceSlide && typeof args.sourceSlide === "object" ? args.sourceSlide : {};
  const blocks = Array.isArray(sourceSlide.blocks) ? sourceSlide.blocks : [];
  const fromBlocks = blocks
    .filter((block) => ["body", "list", "quote", "icon_text", "subtitle"].includes(blockType(block)))
    .flatMap((block) => splitText(blockText(block), 4));
  const merged = [...explicit.map((v) => String(v || "").trim()), ...fromBlocks];
  const out = [];
  const seen = new Set();
  for (const item of merged) {
    if (!item) continue;
    const key = item.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
    if (out.length >= max) break;
  }
  return out.length ? out : ["Core point", "Supporting evidence", "Execution action"];
}

function findFirstBlock(sourceSlide, acceptedTypes) {
  const blocks = Array.isArray(sourceSlide?.blocks) ? sourceSlide.blocks : [];
  const accepted = new Set(acceptedTypes.map((v) => String(v).toLowerCase()));
  return blocks.find((block) => accepted.has(blockType(block))) || null;
}

function normalizeImageDataForPptx(rawInput) {
  const raw = String(rawInput || "").trim();
  const base64Match = raw.match(/^data:(image\/[a-zA-Z0-9+.-]+);base64,(.+)$/i);
  if (base64Match) return `${base64Match[1]};base64,${base64Match[2]}`;
  const utf8Match = raw.match(/^data:(image\/[a-zA-Z0-9+.-]+);utf8,(.+)$/i);
  if (utf8Match) {
    try {
      const decoded = decodeURIComponent(utf8Match[2]);
      const b64 = Buffer.from(decoded, "utf-8").toString("base64");
      return `${utf8Match[1]};base64,${b64}`;
    } catch {
      return "";
    }
  }
  if (/^image\/[a-zA-Z0-9+.-]+;base64,/.test(raw)) return raw;
  return "";
}

function pickImageSource(sourceSlide) {
  const imageBlock = findFirstBlock(sourceSlide, ["image"]);
  if (!imageBlock) return "";
  const content = imageBlock?.content && typeof imageBlock.content === "object" ? imageBlock.content : {};
  const data = imageBlock?.data && typeof imageBlock.data === "object" ? imageBlock.data : {};
  const candidates = [
    content.url,
    content.src,
    content.imageUrl,
    data.url,
    data.src,
    data.imageUrl,
    imageBlock?.url,
    imageBlock?.src,
    imageBlock?.imageUrl,
  ];
  for (const item of candidates) {
    const normalized = normalizeImageDataForPptx(item);
    if (normalized) return normalized;
  }
  return "";
}

function extractKpi(sourceSlide, bullets = []) {
  const kpiBlock = findFirstBlock(sourceSlide, ["kpi"]);
  const payload = kpiBlock?.data && typeof kpiBlock.data === "object" ? kpiBlock.data : {};
  const fromText = `${kpiBlock ? blockText(kpiBlock) : ""} ${bullets.join(" ")}`;
  const numberMatch = fromText.match(/-?\d+(?:\.\d+)?/);
  const trendMatch = fromText.match(/([+-]?\d+(?:\.\d+)?)%/);
  const number = payload.number ?? (numberMatch ? Number(numberMatch[0]) : "--");
  const trend = payload.trend ?? (trendMatch ? Number(trendMatch[1]) : 8);
  return {
    number,
    unit: String(payload.unit || "%"),
    label: truncate(String(payload.label || blockText(kpiBlock) || bullets[0] || "KPI"), 36),
    trend,
  };
}

function addPanel(slide, rect, theme, opts = {}) {
  const { radius = 0.08, fill = theme.cardBg, transparency = 10, border = theme.borderColor, pt = 0.6, dash } = opts;
  const safe = clampRect(rect.x, rect.y, rect.w, rect.h, 0.02);
  slide.addShape("roundRect", {
    ...safe,
    rectRadius: radius,
    fill: { color: fill, transparency },
    line: { color: border, pt, ...(dash ? { dash } : {}) },
  });
  return safe;
}

function addSlideText(slide, text, rect, options = {}) {
  const safe = clampRect(rect.x, rect.y, rect.w, rect.h, 0.02);
  slide.addText(truncate(text, options.maxChars || 160), {
    ...safe,
    fontFace: options.fontFace,
    fontSize: options.fontSize,
    bold: !!options.bold,
    color: options.color,
    align: options.align,
    valign: options.valign,
    margin: 0,
    fit: options.fit || "shrink",
    breakLine: options.breakLine === true,
  });
}

function renderHeroTechCover({
  slide,
  title,
  subtitle,
  theme,
  style,
  helpers,
  sourceSlide,
}) {
  const { FONT_BY_STYLE, FONT_ZH } = helpers;
  const spec = getTemplateSpec("hero_tech_cover");
  const titleText = truncate(String(title || "Presentation").trim(), 60);
  const subtitleText = truncate(String(subtitle || sourceSlide?.narration || "").trim(), 72);
  const titleFont = fitFont(titleText.length > 28 ? spec.title.fontSizeLong : spec.title.fontSizeShort, titleText, 28);
  const deckMeta = sourceSlide?.meta && typeof sourceSlide.meta === "object" ? sourceSlide.meta : {};
  const badgeRaw = String(deckMeta.badge || sourceSlide?.badge || "").trim();
  const presenterRaw = String(deckMeta.presenter || sourceSlide?.author || "").trim();
  const orgRaw = String(deckMeta.organization || sourceSlide?.organization || "").trim();
  const dateRaw = String(deckMeta.date || sourceSlide?.date || "").trim();
  const badge = truncate(badgeRaw, 28);
  const presenter = truncate(presenterRaw, 24);
  const org = truncate(orgRaw, 30);
  const dateText = truncate(dateRaw, 24);

  slide.addShape("rect", { x: 0, y: 0, w: SLIDE_W, h: SLIDE_H, fill: { color: theme.bg }, line: { color: theme.bg, pt: 0 } });
  addPanel(slide, spec.orbit, theme, {
    radius: spec.orbit.radius,
    fill: theme.accentSoft || theme.secondary,
    transparency: 78,
    border: theme.accentSoft || theme.secondary,
    pt: 0,
  });
  if (badge) {
    addPanel(slide, spec.badge, theme, {
      radius: spec.badge.radius,
      fill: theme.accentSoft || theme.secondary,
      transparency: 12,
      border: theme.light,
    });
    addSlideText(slide, badge, {
      x: spec.badge.x + 0.04,
      y: spec.badge.y + 0.05,
      w: spec.badge.w - 0.08,
      h: 0.18,
    }, {
      fontFace: FONT_BY_STYLE[style].enTitle,
      fontSize: 9,
      bold: true,
      color: theme.darkText,
      align: "center",
      maxChars: 36,
    });
  }
  addSlideText(slide, titleText, spec.title, {
    fontFace: FONT_ZH,
    fontSize: titleFont,
    bold: true,
    color: theme.darkText,
    maxChars: 72,
  });
  if (subtitleText) {
    addSlideText(slide, subtitleText, spec.subtitle, {
      fontFace: FONT_ZH,
      fontSize: spec.subtitle.fontSize,
      color: theme.mutedText,
      maxChars: 96,
    });
  }
  addPanel(slide, spec.divider, theme, {
    radius: spec.divider.h / 2,
    fill: theme.accentStrong || theme.accent,
    transparency: 0,
    border: theme.accentStrong || theme.accent,
    pt: 0,
  });

  const footerParts = [presenter, dateText, org].filter(Boolean);
  if (footerParts.length > 0) {
    addSlideText(
      slide,
      footerParts.join("   |   "),
      spec.footer,
      {
        fontFace: FONT_ZH,
        fontSize: spec.footer.fontSize,
        color: theme.mutedText,
        maxChars: 120,
      },
    );
  }
  return true;
}

function renderArchitectureDarkPanelTemplate(slide, bullets, pageNumber, theme, style, helpers, sourceSlide) {
  const { FONT_ZH, addPageBadge } = helpers;
  const spec = getTemplateSpec("architecture_dark_panel");
  const points = safeBulletsFromArgs({ bullets, sourceSlide }, 8);
  const rows = [points.slice(0, 2), points.slice(2, 4), points.slice(4, 6)].map((arr) => arr.filter(Boolean));

  addPanel(slide, spec.board, theme, { radius: spec.board.radius, fill: theme.cardBg, transparency: 8, border: theme.borderColor, pt: spec.board.borderWidth });
  rows.forEach((group, idx) => {
    const y = spec.board.y + 0.15 + idx * (spec.row.h + spec.row.gap);
    addPanel(slide, { x: spec.board.x + 0.04, y, w: spec.board.w - 0.08, h: spec.row.h }, theme, {
      radius: spec.row.radius,
      fill: theme.cardAltBg,
      transparency: 14,
      border: theme.borderColor,
      pt: spec.row.borderWidth,
    });
    addPanel(slide, { x: spec.board.x + spec.leftAccent.xOffset, y: y + spec.leftAccent.yOffset, w: spec.leftAccent.w, h: spec.leftAccent.h }, theme, {
      radius: spec.leftAccent.w / 2,
      fill: theme.accentStrong || theme.accent,
      transparency: 0,
      border: theme.accentStrong || theme.accent,
      pt: 0,
    });
    addSlideText(slide, `Layer ${idx + 1}`, {
      x: spec.board.x + spec.rowTitle.xOffset,
      y: y + spec.rowTitle.yOffset,
      w: spec.rowTitle.w,
      h: spec.rowTitle.h,
    }, {
      fontFace: FONT_ZH,
      fontSize: spec.rowTitle.fontSize,
      bold: true,
      color: theme.accentStrong || theme.accent,
      maxChars: 16,
    });
    addSlideText(slide, group.join(" 路 ") || "Core capability", {
      x: spec.board.x + spec.rowBody.xOffset,
      y: y + spec.rowBody.yOffset,
      w: spec.rowBody.w,
      h: spec.rowBody.h,
    }, {
      fontFace: FONT_ZH,
      fontSize: fitFont(spec.rowBody.fontSize, group.join(" 路 "), 12),
      bold: true,
      color: theme.darkText,
      maxChars: 60,
    });
    slide.addShape("line", {
      x: spec.board.x + spec.connector.xOffset,
      y: y + spec.connector.yOffset,
      w: spec.connector.w,
      h: spec.connector.h,
      line: { color: theme.accentStrong || theme.accent, pt: spec.connector.pt, dash: spec.connector.dash },
    });
  });

  addPanel(slide, spec.rightPanel, theme, {
    radius: spec.rightPanel.radius,
    fill: theme.cardAltBg,
    transparency: 20,
    border: theme.accentStrong || theme.accent,
    pt: spec.rightPanel.borderWidth,
    dash: "dash",
  });
  const sideHeading = pickSecondaryHeading(sourceSlide?.title, points, "Safeguards");
  addSlideText(slide, truncate(sideHeading, 14), spec.rightTitle, {
    fontFace: FONT_ZH,
    fontSize: fitFont(spec.rightTitle.fontSize, sideHeading, 15),
    bold: true,
    color: theme.accentStrong || theme.accent,
    align: "center",
    maxChars: 16,
  });
  points.slice(0, 3).forEach((label, idx) => {
    addSlideText(slide, label, {
      x: spec.rightItems.x,
      y: spec.rightItems.y + idx * spec.rightItems.step,
      w: spec.rightItems.w,
      h: spec.rightItems.h,
    }, {
      fontFace: FONT_ZH,
      fontSize: fitFont(spec.rightItems.fontSize, label, 11),
      bold: true,
      color: theme.darkText,
      align: "center",
      maxChars: 18,
    });
  });
  addPageBadge(slide, pageNumber, theme, style);
  return true;
}

function renderEcosystemOrangeTemplate(slide, bullets, pageNumber, theme, style, helpers, sourceSlide) {
  const { FONT_BY_STYLE, FONT_ZH, addPageBadge } = helpers;
  const spec = getTemplateSpec("ecosystem_orange_dark");
  const points = safeBulletsFromArgs({ bullets, sourceSlide }, 8);
  const kpi = extractKpi(sourceSlide, points);

  addPanel(slide, spec.leftCard, theme, { radius: spec.leftCard.radius, fill: theme.cardBg, transparency: 12, border: theme.borderColor, pt: spec.leftCard.borderWidth });
  addSlideText(slide, String(kpi.number), spec.kpiNumber, {
    fontFace: FONT_BY_STYLE[style].enTitle,
    fontSize: fitFont(spec.kpiNumber.fontSize, String(kpi.number), 36),
    bold: true,
    color: theme.primary,
    maxChars: 16,
  });
  addSlideText(slide, `${kpi.unit} ${kpi.label}`.trim(), spec.kpiLabel, {
    fontFace: FONT_ZH,
    fontSize: fitFont(spec.kpiLabel.fontSize, kpi.label, 12),
    bold: true,
    color: theme.darkText,
    maxChars: 28,
  });
  points.slice(0, 3).forEach((item, idx) => {
    addSlideText(slide, `• ${item}`, {
      x: spec.kpiBullets.x,
      y: spec.kpiBullets.y + idx * spec.kpiBullets.step,
      w: spec.kpiBullets.w,
      h: spec.kpiBullets.h,
    }, {
      fontFace: FONT_ZH,
      fontSize: spec.kpiBullets.fontSize,
      color: theme.mutedText,
      maxChars: 42,
    });
  });

  addPanel(slide, spec.rightCard, theme, { radius: spec.rightCard.radius, fill: theme.cardAltBg, transparency: 14, border: theme.borderColor, pt: spec.rightCard.borderWidth });
  addPanel(slide, spec.centerPill, theme, { radius: spec.centerPill.radius, fill: theme.primary, transparency: 0, border: theme.primary, pt: 0 });
  const coreHeading = pickSecondaryHeading(sourceSlide?.title, points, "Core Platform");
  addSlideText(slide, truncate(String(coreHeading), 20), {
    x: spec.centerPill.x,
    y: spec.centerPill.y + 0.11,
    w: spec.centerPill.w,
    h: 0.34,
  }, {
    fontFace: FONT_BY_STYLE[style].enTitle,
    fontSize: fitFont(spec.centerPill.fontSize, coreHeading, 18),
    bold: true,
    color: "FFFFFF",
    align: "center",
    maxChars: 28,
  });

  const nodeLabels = [points[0] || "People", points[1] || "Vehicle", points[2] || "Home"];
  spec.nodes.forEach((node, idx) => {
    slide.addShape("ellipse", {
      x: node.x,
      y: node.y,
      w: spec.nodeCircle.w,
      h: spec.nodeCircle.h,
      fill: { color: theme.bg },
      line: { color: theme.primary, pt: spec.nodeCircle.borderWidth },
    });
    addSlideText(slide, truncate(nodeLabels[idx], 3), {
      x: node.x,
      y: node.y + 0.18,
      w: spec.nodeCircle.w,
      h: 0.42,
    }, {
      fontFace: FONT_ZH,
      fontSize: 24,
      bold: true,
      color: theme.darkText,
      align: "center",
      maxChars: 4,
    });
  });

  slide.addShape("line", { x: 6.5, y: 2.25, w: 0, h: -0.2, line: { color: theme.primary, pt: 1.05, dash: "dot" } });
  slide.addShape("line", { x: 5.36, y: 2.52, w: -0.3, h: 0.74, line: { color: theme.primary, pt: 1.05, dash: "dot" } });
  slide.addShape("line", { x: 7.65, y: 2.52, w: 0.3, h: 0.74, line: { color: theme.primary, pt: 1.05, dash: "dot" } });

  const bottomItemW = (spec.bottomStrip.w - spec.bottomStrip.itemGap * 2) / 3;
  points.slice(0, 3).forEach((item, idx) => {
    const x = spec.bottomStrip.x + idx * (bottomItemW + spec.bottomStrip.itemGap);
    addPanel(slide, { x, y: spec.bottomStrip.y, w: bottomItemW, h: spec.bottomStrip.h }, theme, {
      radius: spec.bottomStrip.itemRadius,
      fill: theme.accentSoft,
      transparency: 38,
      border: theme.borderColor,
      pt: 0.45,
    });
    addSlideText(slide, item, {
      x: x + 0.03,
      y: spec.bottomStrip.y + 0.12,
      w: bottomItemW - 0.06,
      h: 0.2,
    }, {
      fontFace: FONT_ZH,
      fontSize: spec.bottomStrip.fontSize,
      bold: true,
      color: theme.primary,
      align: "center",
      maxChars: 22,
    });
  });

  addPageBadge(slide, pageNumber, theme, style);
  return true;
}

function renderNeuralBlueprintLightTemplate(slide, bullets, pageNumber, theme, style, helpers, sourceSlide) {
  const { FONT_ZH, addBulletList, addPageBadge } = helpers;
  const spec = getTemplateSpec("neural_blueprint_light");
  const bgCard = "FFFFFF";
  const bgAlt = "EEF3FB";
  const border = "CFDAEC";
  const text = "0F1E35";
  const muted = "6B7C96";
  const accent = "2F67E8";
  const points = safeBulletsFromArgs({ bullets, sourceSlide }, 8);

  addPanel(slide, spec.left, theme, { radius: spec.left.radius, fill: bgCard, transparency: 0, border, pt: 0.6 });
  for (let i = 0; i < 6; i += 1) {
    const col = i % 2;
    const row = Math.floor(i / 2);
    addPanel(slide, {
      x: spec.left.x + 0.18 + col * 1.38,
      y: spec.left.y + 0.43 + row * 0.62,
      w: 1.2,
      h: 0.5,
    }, theme, { radius: 0.06, fill: bgAlt, transparency: 0, border, pt: 0.4 });
    addSlideText(slide, points[i] || `Module ${i + 1}`, {
      x: spec.left.x + 0.26 + col * 1.38,
      y: spec.left.y + 0.62 + row * 0.62,
      w: 1.03,
      h: 0.24,
    }, {
      fontFace: FONT_ZH,
      fontSize: fitFont(12, points[i] || `Module ${i + 1}`, 10),
      bold: true,
      color: text,
      align: "center",
      maxChars: 14,
    });
  }

  addPanel(slide, spec.right, theme, { radius: spec.right.radius, fill: bgCard, transparency: 0, border, pt: 0.6 });
  const imageData = pickImageSource(sourceSlide);
  if (imageData) {
    slide.addImage({
      data: imageData,
      ...clampRect(spec.right.x + 0.24, spec.right.y + 0.42, spec.right.w - 0.46, 1.68, 0.02),
    });
  } else {
    addPanel(slide, {
      x: spec.right.x + 0.24,
      y: spec.right.y + 0.42,
      w: spec.right.w - 0.46,
      h: 1.68,
    }, theme, { radius: 0.06, fill: bgAlt, transparency: 18, border, pt: 0.5 });
    const fallbackTitle = truncate(sourceSlide?.title || "Visual workflow focus", 38);
    addSlideText(slide, fallbackTitle, {
      x: spec.right.x + 0.28,
      y: spec.right.y + 0.52,
      w: spec.right.w - 0.56,
      h: 0.24,
    }, {
      fontFace: FONT_ZH,
      fontSize: 12,
      color: text,
      align: "left",
      maxChars: 42,
    });
    points.slice(0, 3).forEach((line, idx) => {
      addSlideText(slide, `• ${truncate(line || "Detail", 36)}`, {
        x: spec.right.x + 0.28,
        y: spec.right.y + 0.84 + idx * 0.34,
        w: spec.right.w - 0.56,
        h: 0.24,
      }, {
        fontFace: FONT_ZH,
        fontSize: 11,
        color: muted,
        maxChars: 40,
      });
    });
  }

  addPanel(slide, spec.lowerLeft, theme, { radius: spec.lowerLeft.radius, fill: bgCard, transparency: 0, border, pt: 0.6 });
  addPanel(slide, spec.lowerRight, theme, { radius: spec.lowerRight.radius, fill: bgCard, transparency: 0, border, pt: 0.6 });
  addBulletList(slide, points.slice(0, 4), spec.lowerLeft.x + 0.18, spec.lowerLeft.y + 0.28, spec.lowerLeft.w - 0.38, 1.2, { ...theme, darkText: text, mutedText: muted, primary: accent }, style, 4);
  addBulletList(slide, points.slice(2, 6), spec.lowerRight.x + 0.18, spec.lowerRight.y + 0.28, spec.lowerRight.w - 0.38, 1.2, { ...theme, darkText: text, mutedText: muted, primary: accent }, style, 4);
  addPageBadge(slide, pageNumber, theme, style);
  return true;
}

function renderOpsLifecycleLightTemplate(slide, bullets, pageNumber, theme, style, helpers, sourceSlide) {
  const { FONT_ZH, addPageBadge } = helpers;
  const spec = getTemplateSpec("ops_lifecycle_light");
  const bgCard = "FFFFFF";
  const bgAlt = "EEF3FB";
  const border = "CFDAEC";
  const text = "0F1E35";
  const muted = "6B7C96";
  const accent = "2F67E8";
  const points = safeBulletsFromArgs({ bullets, sourceSlide }, 10);

  const cardTitles = [points[0], points[1], points[2], points[3]].map((v, idx) => v || `Section ${idx + 1}`);
  const cardBodies = [
    points.slice(4, 7),
    points.slice(5, 8),
    points.slice(6, 9),
    points.slice(7, 10),
  ];

  spec.grid.forEach((card, idx) => {
    addPanel(slide, card, theme, { radius: 0.08, fill: bgCard, transparency: 0, border, pt: 0.6 });
    addSlideText(slide, cardTitles[idx], {
      x: card.x + spec.title.xOffset,
      y: card.y + spec.title.yOffset,
      w: card.w - 0.44,
      h: spec.title.h,
    }, {
      fontFace: FONT_ZH,
      fontSize: fitFont(spec.title.fontSize, cardTitles[idx], 15),
      bold: true,
      color: text,
      maxChars: 30,
    });

    if (idx === 0) {
      addPanel(slide, {
        x: card.x + spec.badge.xOffset,
        y: card.y + spec.badge.yOffset,
        w: spec.badge.w,
        h: spec.badge.h,
      }, theme, { radius: spec.badge.radius, fill: "E9F0FC", border: "E9F0FC", pt: 0, transparency: 0 });
      addSlideText(slide, truncate(points[4] || "Efficiency uplift", 20), {
        x: card.x + spec.badge.xOffset,
        y: card.y + spec.badge.yOffset + 0.08,
        w: spec.badge.w,
        h: 0.16,
      }, {
        fontFace: FONT_ZH,
        fontSize: spec.badge.fontSize,
        bold: true,
        color: accent,
        align: "center",
        maxChars: 20,
      });
    }

    if (idx % 2 === 1) {
      addPanel(slide, {
        x: card.x + spec.dashedBox.xOffset,
        y: card.y + spec.dashedBox.yOffset,
        w: card.w - 0.44,
        h: spec.dashedBox.h,
      }, theme, {
        radius: spec.dashedBox.radius,
        fill: bgAlt,
        transparency: 14,
        border,
        pt: spec.dashedBox.borderWidth,
        dash: "dash",
      });
      addSlideText(slide, cardBodies[idx][0] || "Monitoring view", {
        x: card.x + 0.42,
        y: card.y + 1.29,
        w: card.w - 0.84,
        h: 0.22,
      }, {
        fontFace: FONT_ZH,
        fontSize: 12,
        color: muted,
        align: "center",
        maxChars: 36,
      });
    } else {
      cardBodies[idx].slice(0, 3).forEach((line, lineIdx) => {
        addSlideText(slide, `• ${line || "Detail"}`, {
          x: card.x + spec.list.xOffset,
          y: card.y + spec.list.yOffset + lineIdx * spec.list.step,
          w: card.w - spec.list.wPad,
          h: 0.2,
        }, {
          fontFace: FONT_ZH,
          fontSize: spec.list.fontSize,
          color: muted,
          maxChars: 48,
        });
      });
    }
  });
  addPageBadge(slide, pageNumber, theme, style);
  return true;
}

function renderConsultingWarmLightTemplate(slide, bullets, pageNumber, theme, style, helpers, sourceSlide) {
  const { FONT_ZH, addBulletList, addPageBadge } = helpers;
  const spec = getTemplateSpec("consulting_warm_light");
  const bgCard = "FFFFFF";
  const bgAlt = "F6ECE2";
  const border = "D8BFAA";
  const text = "3A2A23";
  const muted = "7F6B5D";
  const accent = "9B3B2E";
  const points = safeBulletsFromArgs({ bullets, sourceSlide }, 10);
  const imageData = pickImageSource(sourceSlide);

  addPanel(slide, spec.heroRule, theme, { radius: spec.heroRule.radius, fill: bgCard, transparency: 0, border, pt: 0.6 });
  const ruleHeading = pickSecondaryHeading(sourceSlide?.title, points, "Recommendation rule");
  addSlideText(slide, truncate(ruleHeading, 60), {
    x: 0.78,
    y: 1.13,
    w: 8.3,
    h: 0.24,
  }, {
    fontFace: FONT_ZH,
    fontSize: 18,
    bold: true,
    color: accent,
    maxChars: 64,
  });

  for (let i = 0; i < 4; i += 1) {
    const x = spec.topGrid.x + i * (spec.topGrid.cardW + spec.topGrid.gap);
    addPanel(slide, { x, y: spec.topGrid.y, w: spec.topGrid.cardW, h: spec.topGrid.cardH }, theme, { radius: 0.06, fill: bgCard, border, pt: 0.5, transparency: 0 });
    addSlideText(slide, points[i] || `Region ${i + 1}`, {
      x: x + 0.12,
      y: spec.topGrid.y + 0.2,
      w: spec.topGrid.cardW - 0.24,
      h: 0.3,
    }, {
      fontFace: FONT_ZH,
      fontSize: fitFont(16, points[i] || `Region ${i + 1}`, 12),
      bold: true,
      color: accent,
      align: "center",
      maxChars: 22,
    });
  }

  spec.bottomCards.forEach((card, idx) => {
    addPanel(slide, card, theme, {
      radius: 0.08,
      fill: idx === 2 ? bgAlt : bgCard,
      transparency: idx === 2 ? 8 : 0,
      border,
      pt: 0.5,
    });
  });

  addBulletList(slide, points.slice(0, 3), spec.bottomCards[0].x + 0.2, spec.bottomCards[0].y + 0.36, spec.bottomCards[0].w - 0.4, 1.06, { ...theme, darkText: text, mutedText: muted, primary: accent }, style, 3);
  addBulletList(slide, points.slice(3, 6), spec.bottomCards[1].x + 0.2, spec.bottomCards[1].y + 0.36, spec.bottomCards[1].w - 0.4, 1.06, { ...theme, darkText: text, mutedText: muted, primary: accent }, style, 3);
  if (imageData) {
    slide.addImage({
      data: imageData,
      ...clampRect(spec.bottomCards[2].x + 0.08, spec.bottomCards[2].y + 0.08, spec.bottomCards[2].w - 0.16, spec.bottomCards[2].h - 0.16, 0.02),
    });
  } else {
    addSlideText(slide, truncate(points[6] || "Execution highlight", 40), {
      x: spec.bottomCards[2].x + 0.12,
      y: spec.bottomCards[2].y + 0.14,
      w: spec.bottomCards[2].w - 0.24,
      h: 0.24,
    }, {
      fontFace: FONT_ZH,
      fontSize: 12,
      color: accent,
      align: "left",
      maxChars: 34,
    });
    points.slice(3, 6).forEach((item, idx) => {
      addSlideText(slide, `• ${truncate(item || "Detail", 28)}`, {
        x: spec.bottomCards[2].x + 0.14,
        y: spec.bottomCards[2].y + 0.48 + idx * 0.3,
        w: spec.bottomCards[2].w - 0.28,
        h: 0.24,
      }, {
        fontFace: FONT_ZH,
        fontSize: 11,
        color: muted,
        maxChars: 32,
      });
    });
  }

  addPageBadge(slide, pageNumber, theme, style);
  return true;
}

function extractChartSeries(sourceSlide, fallback = []) {
  const chartBlock = findFirstBlock(sourceSlide, ["chart"]);
  const chartData = chartBlock?.data && typeof chartBlock.data === "object" ? chartBlock.data : {};
  const labels = Array.isArray(chartData.labels) ? chartData.labels : [];
  const datasets = Array.isArray(chartData.datasets) ? chartData.datasets : [];
  if (labels.length && datasets.length) {
    const first = datasets[0] || {};
    const values = Array.isArray(first.data) ? first.data : [];
    const out = [];
    for (let i = 0; i < Math.min(labels.length, values.length, 6); i += 1) {
      const label = String(labels[i] || "").trim();
      const value = Number(values[i]);
      if (!label || !Number.isFinite(value)) continue;
      out.push({ label, value });
    }
    if (out.length) return out;
  }
  const fallbackValues = [];
  for (const item of fallback) {
    const text = String(item || "");
    const m = text.match(/([0-9]+(?:\.[0-9]+)?)/);
    if (!m) continue;
    fallbackValues.push({
      label: truncate(text.replace(/([0-9]+(?:\.[0-9]+)?%?)/, "").trim() || text, 14),
      value: Number(m[1]),
    });
    if (fallbackValues.length >= 5) break;
  }
  if (fallbackValues.length) return fallbackValues;
  return [
    { label: "Q1", value: 100 },
    { label: "Q2", value: 128 },
    { label: "Q3", value: 154 },
    { label: "Q4", value: 176 },
  ];
}

function renderSplitMediaDarkTemplate(slide, bullets, pageNumber, theme, style, helpers, sourceSlide) {
  const { FONT_ZH, addBulletList, addPageBadge } = helpers;
  const spec = getTemplateSpec("split_media_dark");
  const points = safeBulletsFromArgs({ bullets, sourceSlide }, 8);
  const kpi = extractKpi(sourceSlide, points);
  const imageData = pickImageSource(sourceSlide);

  addPanel(slide, spec.left, theme, {
    radius: spec.left.radius,
    fill: theme.cardBg,
    transparency: 10,
    border: theme.borderColor,
    pt: 0.7,
  });
  addSlideText(slide, truncate(String(sourceSlide?.title || points[0] || "Core Narrative"), 44), {
    x: spec.left.x + 0.18,
    y: spec.left.y + 0.16,
    w: spec.left.w - 0.36,
    h: 0.34,
  }, {
    fontFace: FONT_ZH,
    fontSize: fitFont(18, sourceSlide?.title || points[0], 14),
    bold: true,
    color: theme.darkText,
    maxChars: 48,
  });

  addBulletList(
    slide,
    points.slice(0, 5),
    spec.left.x + 0.18,
    spec.left.y + 0.58,
    spec.left.w - 0.36,
    spec.left.h - 1.2,
    theme,
    style,
    5,
  );

  addPanel(slide, {
    x: spec.left.x + 0.18,
    y: spec.left.y + spec.left.h - 0.54,
    w: Math.min(2.2, spec.left.w - 0.36),
    h: 0.34,
  }, theme, {
    radius: 0.08,
    fill: theme.accentSoft || theme.secondary,
    transparency: 15,
    border: theme.accentSoft || theme.secondary,
    pt: 0,
  });
  addSlideText(slide, `${kpi.number}${kpi.unit}  |  ${kpi.trend >= 0 ? "+" : ""}${kpi.trend}%`, {
    x: spec.left.x + 0.2,
    y: spec.left.y + spec.left.h - 0.5,
    w: Math.min(2.16, spec.left.w - 0.4),
    h: 0.24,
  }, {
    fontFace: FONT_ZH,
    fontSize: 11,
    bold: true,
    color: theme.darkText,
    maxChars: 40,
  });

  addPanel(slide, spec.right, theme, {
    radius: spec.right.radius,
    fill: theme.cardAltBg,
    transparency: 12,
    border: theme.borderColor,
    pt: 0.7,
  });
  if (imageData) {
    slide.addImage({
      data: imageData,
      ...clampRect(spec.right.x + 0.12, spec.right.y + 0.12, spec.right.w - 0.24, spec.right.h - 0.24, 0.02),
    });
  } else {
    addPanel(slide, {
      x: spec.right.x + 0.18,
      y: spec.right.y + 0.16,
      w: spec.right.w - 0.36,
      h: spec.right.h - 0.32,
    }, theme, {
      radius: 0.08,
      fill: theme.cardBg,
      transparency: 8,
      border: theme.borderColor,
      pt: 0.5,
      dash: "dash",
    });
    points.slice(0, 4).forEach((item, idx) => {
      addSlideText(slide, item, {
        x: spec.right.x + 0.24,
        y: spec.right.y + 0.34 + idx * 0.44,
        w: spec.right.w - 0.48,
        h: 0.26,
      }, {
        fontFace: FONT_ZH,
        fontSize: 12,
        color: theme.mutedText,
        maxChars: 38,
      });
    });
  }
  addPageBadge(slide, pageNumber, theme, style);
  return true;
}

function renderDashboardDarkTemplate(slide, bullets, pageNumber, theme, style, helpers, sourceSlide) {
  const { FONT_ZH, FONT_BY_STYLE, addBulletList, addPageBadge } = helpers;
  const spec = getTemplateSpec("dashboard_dark");
  const points = safeBulletsFromArgs({ bullets, sourceSlide }, 10);
  const series = extractChartSeries(sourceSlide, points);
  const kpiPrimary = extractKpi(sourceSlide, points);
  const kpiSecondary = {
    number: Number.isFinite(Number(kpiPrimary.number)) ? Number(kpiPrimary.number) + 7 : 28,
    unit: "%",
    label: truncate(points[1] || "Conversion", 20),
    trend: Number(kpiPrimary.trend || 6) + 3,
  };
  const kpiThird = {
    number: 3.4,
    unit: "x",
    label: truncate(points[2] || "Throughput", 20),
    trend: 11,
  };

  addPanel(slide, spec.canvas, theme, {
    radius: spec.canvas.radius,
    fill: theme.cardBg,
    transparency: 8,
    border: theme.borderColor,
    pt: 0.7,
  });
  const kpis = [kpiPrimary, kpiSecondary, kpiThird];
  spec.kpiCards.forEach((card, idx) => {
    const item = kpis[idx];
    addPanel(slide, card, theme, {
      radius: 0.08,
      fill: theme.cardAltBg,
      transparency: 12,
      border: theme.borderColor,
      pt: 0.5,
    });
    addSlideText(slide, String(item.number), {
      x: card.x + 0.14,
      y: card.y + 0.1,
      w: card.w - 0.28,
      h: 0.42,
    }, {
      fontFace: FONT_BY_STYLE[style].enTitle,
      fontSize: 24,
      bold: true,
      color: theme.primary,
      maxChars: 12,
    });
    addSlideText(slide, `${item.unit} ${item.label}`.trim(), {
      x: card.x + 0.14,
      y: card.y + 0.54,
      w: card.w - 0.28,
      h: 0.2,
    }, {
      fontFace: FONT_ZH,
      fontSize: 10,
      color: theme.mutedText,
      maxChars: 24,
    });
  });

  addPanel(slide, spec.left, theme, {
    radius: spec.left.radius,
    fill: theme.cardAltBg,
    transparency: 12,
    border: theme.borderColor,
    pt: 0.6,
  });
  addBulletList(
    slide,
    points.slice(0, 4),
    spec.left.x + 0.16,
    spec.left.y + 0.22,
    spec.left.w - 0.32,
    spec.left.h - 0.3,
    theme,
    style,
    4,
  );

  addPanel(slide, spec.chart, theme, {
    radius: spec.chart.radius,
    fill: theme.cardAltBg,
    transparency: 8,
    border: theme.borderColor,
    pt: 0.6,
  });
  let nativeChartDrawn = false;
  if (helpers?.pptx && typeof slide?.addChart === "function") {
    try {
      const labels = series.slice(0, 6).map((item) => truncate(item.label, 10));
      const values = series.slice(0, 6).map((item) => Number(item.value || 0));
      createChart(
        slide,
        helpers.pptx,
        "bar",
        [{ name: "Index", labels, values }],
        {
          x: spec.chart.x + 0.12,
          y: spec.chart.y + 0.14,
          w: spec.chart.w - 0.24,
          h: spec.chart.h - 0.24,
          showLegend: false,
        },
        theme,
      );
      nativeChartDrawn = true;
    } catch {
      nativeChartDrawn = false;
    }
  }
  if (!nativeChartDrawn) {
    const maxVal = Math.max(1, ...series.map((s) => Number(s.value || 0)));
    const rowH = 0.26;
    const rowGap = 0.1;
    series.slice(0, 5).forEach((item, idx) => {
      const y = spec.chart.y + 0.18 + idx * (rowH + rowGap);
      const barW = Math.max(0.3, ((spec.chart.w - 1.7) * Number(item.value || 0)) / maxVal);
      addSlideText(slide, truncate(item.label, 8), {
        x: spec.chart.x + 0.16,
        y: y + 0.01,
        w: 0.78,
        h: rowH,
      }, {
        fontFace: FONT_ZH,
        fontSize: 10,
        color: theme.mutedText,
        maxChars: 10,
      });
      addPanel(slide, { x: spec.chart.x + 0.96, y, w: barW, h: rowH }, theme, {
        radius: 0.06,
        fill: theme.primary,
        transparency: 0,
        border: theme.primary,
        pt: 0,
      });
      addSlideText(slide, String(item.value), {
        x: spec.chart.x + 0.98 + barW,
        y: y + 0.01,
        w: 0.56,
        h: rowH,
      }, {
        fontFace: FONT_BY_STYLE[style].enBody,
        fontSize: 10,
        bold: true,
        color: theme.darkText,
        maxChars: 10,
      });
    });
  }

  addPageBadge(slide, pageNumber, theme, style);
  return true;
}

function renderKpiDashboardDarkTemplate(slide, bullets, pageNumber, theme, style, helpers, sourceSlide) {
  const nextTheme = {
    ...theme,
    template_family: "kpi_dashboard_dark",
    cardBg: theme.cardBg || "0E1630",
    cardAltBg: theme.cardAltBg || "121F3D",
    borderColor: theme.borderColor || "1E335E",
  };
  const ok = renderDashboardDarkTemplate(slide, bullets, pageNumber, nextTheme, style, helpers, sourceSlide);
  if (!ok) return false;
  addPanel(slide, { x: 0.66, y: 0.9, w: 2.2, h: 0.26 }, nextTheme, {
    radius: 0.13,
    fill: nextTheme.primary || "2F7BFF",
    transparency: 0,
    border: nextTheme.primary || "2F7BFF",
    pt: 0,
  });
  addSlideText(slide, "KPI Dashboard", { x: 0.74, y: 0.92, w: 1.96, h: 0.22 }, {
    fontFace: helpers?.FONT_BY_STYLE?.[style]?.enBody,
    fontSize: 10,
    bold: true,
    color: nextTheme.white || "FFFFFF",
    maxChars: 32,
  });
  return true;
}

function renderImageShowcaseLightTemplate(slide, bullets, pageNumber, theme, style, helpers, sourceSlide) {
  const { addBulletList, addPageBadge, FONT_ZH } = helpers;
  const spec = getTemplateSpec("image_showcase_light");
  const nextTheme = {
    ...theme,
    template_family: "image_showcase_light",
    bg: "F6F8FC",
    cardBg: "FFFFFF",
    cardAltBg: "EEF3FB",
    borderColor: "CFDAEC",
    darkText: "0F1E35",
    mutedText: "6B7C96",
  };
  const points = safeBulletsFromArgs({ bullets, sourceSlide }, 8);
  const imageData = pickImageSource(sourceSlide);

  addPanel(slide, spec.hero, nextTheme, {
    radius: spec.hero.radius,
    fill: nextTheme.cardBg,
    transparency: 0,
    border: nextTheme.borderColor,
    pt: 0.7,
  });
  if (imageData) {
    slide.addImage({
      data: imageData,
      ...clampRect(spec.hero.x + 0.1, spec.hero.y + 0.1, spec.hero.w - 0.2, spec.hero.h - 0.2, 0.02),
    });
  } else {
    addBulletList(
      slide,
      points.slice(0, 5),
      spec.hero.x + 0.22,
      spec.hero.y + 0.24,
      spec.hero.w - 0.44,
      spec.hero.h - 0.46,
      nextTheme,
      style,
      5,
    );
  }

  for (const [idx, slot] of [spec.sideTop, spec.sideBottom].entries()) {
    addPanel(slide, slot, nextTheme, {
      radius: slot.radius,
      fill: nextTheme.cardBg,
      transparency: 0,
      border: nextTheme.borderColor,
      pt: 0.7,
    });
    addSlideText(slide, points[idx] || `Highlight ${idx + 1}`, {
      x: slot.x + 0.16,
      y: slot.y + 0.18,
      w: slot.w - 0.32,
      h: slot.h - 0.3,
    }, {
      fontFace: FONT_ZH,
      fontSize: 13,
      color: nextTheme.darkText,
      maxChars: 72,
      breakLine: true,
    });
  }

  addPageBadge(slide, pageNumber, nextTheme, style);
  return true;
}

function renderProcessFlowDarkTemplate(slide, bullets, pageNumber, theme, style, helpers, sourceSlide) {
  const { FONT_ZH, addPageBadge } = helpers;
  const spec = getTemplateSpec("process_flow_dark");
  const nextTheme = {
    ...theme,
    template_family: "process_flow_dark",
    cardBg: theme.cardBg || "0F162C",
    cardAltBg: theme.cardAltBg || "132241",
    borderColor: theme.borderColor || "2A3F6E",
  };
  const points = safeBulletsFromArgs({ bullets, sourceSlide }, 8);

  addPanel(slide, spec.board, nextTheme, {
    radius: spec.board.radius,
    fill: nextTheme.cardBg,
    transparency: 8,
    border: nextTheme.borderColor,
    pt: 0.8,
  });

  const nodeTexts = [points[0], points[1], points[2], points[3]].map((v, i) => v || `Step ${i + 1}`);
  spec.nodes.forEach((node, idx) => {
    addPanel(slide, node, nextTheme, {
      radius: 0.08,
      fill: nextTheme.cardAltBg,
      transparency: 4,
      border: nextTheme.borderColor,
      pt: 0.7,
    });
    addSlideText(slide, `0${idx + 1}`, {
      x: node.x + 0.14,
      y: node.y + 0.16,
      w: 0.38,
      h: 0.26,
    }, {
      fontFace: FONT_ZH,
      fontSize: 12,
      bold: true,
      color: nextTheme.accent || "18E0D1",
      maxChars: 4,
    });
    addSlideText(slide, nodeTexts[idx], {
      x: node.x + 0.14,
      y: node.y + 0.5,
      w: node.w - 0.28,
      h: node.h - 0.62,
    }, {
      fontFace: FONT_ZH,
      fontSize: 11,
      color: nextTheme.darkText,
      maxChars: 88,
      breakLine: true,
    });
    if (idx < spec.nodes.length - 1) {
      slide.addShape("line", {
        x: node.x + node.w,
        y: node.y + node.h / 2,
        w: spec.nodes[idx + 1].x - (node.x + node.w),
        h: 0,
        line: { color: nextTheme.accent || "18E0D1", pt: 1.1 },
      });
    }
  });

  addPageBadge(slide, pageNumber, nextTheme, style);
  return true;
}

function renderComparisonCardsLightTemplate(slide, bullets, pageNumber, theme, style, helpers, sourceSlide) {
  const { FONT_ZH, addPageBadge } = helpers;
  const spec = getTemplateSpec("comparison_cards_light");
  const nextTheme = {
    ...theme,
    template_family: "comparison_cards_light",
    bg: "F7F8FB",
    cardBg: "FFFFFF",
    cardAltBg: "F1F4FA",
    borderColor: "D7E0EE",
    darkText: "17243D",
    mutedText: "667A9D",
  };
  const points = safeBulletsFromArgs({ bullets, sourceSlide }, 9);

  spec.cards.forEach((card, idx) => {
    addPanel(slide, card, nextTheme, {
      radius: 0.09,
      fill: nextTheme.cardBg,
      transparency: 0,
      border: nextTheme.borderColor,
      pt: 0.7,
    });
    addSlideText(slide, idx === 0 ? "Option A" : idx === 1 ? "Option B" : "Option C", {
      x: card.x + 0.16,
      y: card.y + 0.18,
      w: card.w - 0.32,
      h: 0.24,
    }, {
      fontFace: FONT_ZH,
      fontSize: 12,
      bold: true,
      color: nextTheme.primary || "2F67E8",
      maxChars: 24,
    });
    const text = [points[idx * 2], points[idx * 2 + 1]].filter(Boolean).join("; ") || points[idx] || "Comparison point";
    addSlideText(slide, text, {
      x: card.x + 0.16,
      y: card.y + 0.5,
      w: card.w - 0.32,
      h: card.h - 0.72,
    }, {
      fontFace: FONT_ZH,
      fontSize: 11,
      color: nextTheme.darkText,
      maxChars: 120,
      breakLine: true,
    });
  });

  addPageBadge(slide, pageNumber, nextTheme, style);
  return true;
}

function renderQuoteHeroDarkTemplate(slide, bullets, pageNumber, theme, style, helpers, sourceSlide) {
  const { FONT_ZH, addPageBadge } = helpers;
  const spec = getTemplateSpec("quote_hero_dark");
  const quoteBlock = findFirstBlock(sourceSlide, ["quote", "body", "list"]);
  const quoteText = truncate(
    blockText(quoteBlock) || safeBulletsFromArgs({ bullets, sourceSlide }, 2).join("；") || "Insight drives execution.",
    200,
  );
  const authorText = truncate(String(sourceSlide?.author || sourceSlide?.speaker || "Source"), 48);
  const nextTheme = {
    ...theme,
    template_family: "quote_hero_dark",
    cardBg: theme.cardBg || "0E1630",
    cardAltBg: theme.cardAltBg || "132241",
    borderColor: theme.borderColor || "2A3F6E",
  };

  addPanel(slide, spec.quotePanel, nextTheme, {
    radius: spec.quotePanel.radius,
    fill: nextTheme.cardAltBg,
    transparency: 8,
    border: nextTheme.borderColor,
    pt: 0.8,
  });
  addSlideText(slide, `"${quoteText}"`, spec.quote, {
    fontFace: FONT_ZH,
    fontSize: spec.quote.fontSize,
    color: nextTheme.darkText,
    bold: true,
    align: "center",
    valign: "mid",
    maxChars: 220,
    breakLine: true,
  });
  addSlideText(slide, `- ${authorText}`, spec.author, {
    fontFace: FONT_ZH,
    fontSize: spec.author.fontSize,
    color: nextTheme.mutedText,
    align: "right",
    maxChars: 68,
  });

  addPageBadge(slide, pageNumber, nextTheme, style);
  return true;
}

const BENTO_CARD_ORDER = {
  grid_4: ["tl", "tr", "bl", "br"],
  bento_5: ["hero", "s1", "s2", "s3", "s4"],
};

function ensureBentoTemplateSource(sourceSlide = {}, bullets = [], templateFamily = "bento_2x2_dark") {
  const family = String(templateFamily || "").trim().toLowerCase();
  const forcedLayout = getTemplatePreferredLayout(family, "grid_4");
  if (sourceSlide && typeof sourceSlide === "object") {
    sourceSlide.layout_grid = forcedLayout;
  }
  const out = sourceSlide && typeof sourceSlide === "object" ? { ...sourceSlide } : {};
  out.layout_grid = forcedLayout;
  const blocks = Array.isArray(out.blocks)
    ? out.blocks
      .filter((item) => item && typeof item === "object")
      .map((item) => ({ ...item }))
    : [];
  const titleText = truncate(String(out.title || bullets[0] || "Core Highlights"), 64);
  if (!blocks.some((item) => blockType(item) === "title")) {
    blocks.unshift({ block_type: "title", card_id: "title", content: titleText });
  }

  const slots = BENTO_CARD_ORDER[forcedLayout] || ["tl", "tr", "bl", "br"];
  let slotIdx = 0;
  let nonTitleCount = 0;
  for (const block of blocks) {
    if (blockType(block) === "title") continue;
    nonTitleCount += 1;
    const hasSlot = String(block.card_id || block.id || "").trim().length > 0;
    if (hasSlot) continue;
    block.card_id = slots[slotIdx % slots.length];
    slotIdx += 1;
  }

  if (nonTitleCount === 0) {
    const fallbackItems = safeBulletsFromArgs({ bullets, sourceSlide: out }, 6);
    const generated = [
      { block_type: "body", card_id: slots[0], content: fallbackItems[0] || "Core narrative" },
      { block_type: "list", card_id: slots[1], content: fallbackItems.slice(1, 4).join("; ") || "Insight A; Insight B" },
      { block_type: "kpi", card_id: slots[2], data: { number: 118, unit: "%", trend: 8 }, content: "118%" },
      { block_type: "image", card_id: slots[3], content: { title: fallbackItems[4] || "Visual anchor" } },
    ];
    blocks.push(...generated);
  }

  out.blocks = blocks;
  return out;
}

function renderBentoTemplate(slide, bullets, pageNumber, theme, style, helpers, sourceSlide, templateFamily) {
  const preparedSource = ensureBentoTemplateSource(sourceSlide, bullets, templateFamily);
  const pptx = helpers?.pptx || {
    shapes: { ROUNDED_RECTANGLE: "roundRect" },
    charts: { BAR: "bar" },
  };
  const ok = renderBentoSlide({
    pptx,
    slide,
    sourceSlide: preparedSource,
    theme,
    style,
  });
  if (!ok) return false;

  if (String(templateFamily || "").trim().toLowerCase() === "bento_mosaic_dark") {
    slide.addShape("line", {
      x: 0.54,
      y: 0.88,
      w: 8.92,
      h: 0,
      line: { color: theme.accentStrong || theme.accent || "18E0D1", pt: 0.8, transparency: 22 },
    });
    slide.addShape("ellipse", {
      x: 9.14,
      y: 0.82,
      w: 0.16,
      h: 0.16,
      fill: { color: theme.accentStrong || theme.accent || "18E0D1", transparency: 0 },
      line: { color: theme.accentStrong || theme.accent || "18E0D1", pt: 0 },
    });
  }

  if (typeof helpers?.addPageBadge === "function") {
    helpers.addPageBadge(slide, pageNumber, theme, style);
  }
  return true;
}

const CONTENT_RENDERERS = new Set([
  "architecture_dark_panel",
  "ecosystem_orange_dark",
  "neural_blueprint_light",
  "ops_lifecycle_light",
  "consulting_warm_light",
  "split_media_dark",
  "dashboard_dark",
  "bento_2x2_dark",
  "bento_mosaic_dark",
  "kpi_dashboard_dark",
  "image_showcase_light",
  "process_flow_dark",
  "comparison_cards_light",
  "quote_hero_dark",
]);

const COVER_RENDERERS = new Set(["hero_tech_cover"]);

export function hasTemplateContentRenderer(templateFamily) {
  return CONTENT_RENDERERS.has(String(templateFamily || "").trim().toLowerCase());
}

export function hasTemplateCoverRenderer(templateFamily) {
  return COVER_RENDERERS.has(String(templateFamily || "").trim().toLowerCase());
}

export function listTemplateContentRenderers() {
  return Array.from(CONTENT_RENDERERS).sort();
}

export function listTemplateCoverRenderers() {
  return Array.from(COVER_RENDERERS).sort();
}

export function renderTemplateCover(args) {
  const family = String(args?.templateFamily || "").trim().toLowerCase();
  if (!hasTemplateCoverRenderer(family)) return false;
  return renderHeroTechCover(args);
}

export function renderTemplateContent(args) {
  const family = String(args?.templateFamily || "").trim().toLowerCase();
  switch (family) {
    case "architecture_dark_panel":
      return renderArchitectureDarkPanelTemplate(
        args.slide,
        args.bullets,
        args.pageNumber,
        args.theme,
        args.style,
        args.helpers,
        args.sourceSlide,
      );
    case "ecosystem_orange_dark":
      return renderEcosystemOrangeTemplate(
        args.slide,
        args.bullets,
        args.pageNumber,
        args.theme,
        args.style,
        args.helpers,
        args.sourceSlide,
      );
    case "neural_blueprint_light":
      return renderNeuralBlueprintLightTemplate(
        args.slide,
        args.bullets,
        args.pageNumber,
        args.theme,
        args.style,
        args.helpers,
        args.sourceSlide,
      );
    case "ops_lifecycle_light":
      return renderOpsLifecycleLightTemplate(
        args.slide,
        args.bullets,
        args.pageNumber,
        args.theme,
        args.style,
        args.helpers,
        args.sourceSlide,
      );
    case "consulting_warm_light":
      return renderConsultingWarmLightTemplate(
        args.slide,
        args.bullets,
        args.pageNumber,
        args.theme,
        args.style,
        args.helpers,
        args.sourceSlide,
      );
    case "split_media_dark":
      return renderSplitMediaDarkTemplate(
        args.slide,
        args.bullets,
        args.pageNumber,
        args.theme,
        args.style,
        args.helpers,
        args.sourceSlide,
      );
    case "dashboard_dark":
      return renderDashboardDarkTemplate(
        args.slide,
        args.bullets,
        args.pageNumber,
        args.theme,
        args.style,
        args.helpers,
        args.sourceSlide,
      );
    case "kpi_dashboard_dark":
      return renderKpiDashboardDarkTemplate(
        args.slide,
        args.bullets,
        args.pageNumber,
        args.theme,
        args.style,
        args.helpers,
        args.sourceSlide,
      );
    case "image_showcase_light":
      return renderImageShowcaseLightTemplate(
        args.slide,
        args.bullets,
        args.pageNumber,
        args.theme,
        args.style,
        args.helpers,
        args.sourceSlide,
      );
    case "process_flow_dark":
      return renderProcessFlowDarkTemplate(
        args.slide,
        args.bullets,
        args.pageNumber,
        args.theme,
        args.style,
        args.helpers,
        args.sourceSlide,
      );
    case "comparison_cards_light":
      return renderComparisonCardsLightTemplate(
        args.slide,
        args.bullets,
        args.pageNumber,
        args.theme,
        args.style,
        args.helpers,
        args.sourceSlide,
      );
    case "quote_hero_dark":
      return renderQuoteHeroDarkTemplate(
        args.slide,
        args.bullets,
        args.pageNumber,
        args.theme,
        args.style,
        args.helpers,
        args.sourceSlide,
      );
    case "bento_2x2_dark":
    case "bento_mosaic_dark":
      return renderBentoTemplate(
        args.slide,
        args.bullets,
        args.pageNumber,
        args.theme,
        args.style,
        args.helpers,
        args.sourceSlide,
        family,
      );
    default:
      return false;
  }
}



