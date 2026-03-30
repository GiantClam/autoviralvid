import { getCardById, getGrid, validateGrid } from "./bento-grid.mjs";
import { createChart, inferChartTypeFromBlock } from "./chart-factory.mjs";
import { renderIconDataForPptx, resolveIconName } from "./icon-factory.mjs";
import { isNonStandardChartType, renderNonStandardChartInCard } from "./svg-chart-converter.mjs";

const STYLE_RECIPE = {
  sharp: { cardRadius: 0.03 },
  soft: { cardRadius: 0.1 },
  rounded: { cardRadius: 0.2 },
  pill: { cardRadius: 0.3 },
};

function safeRecipe(style) {
  return STYLE_RECIPE[String(style || "soft")] || STYLE_RECIPE.soft;
}

function createRenderError(code, message) {
  const err = new Error(message);
  err.code = code;
  err.retryable = true;
  return err;
}

function blockType(block) {
  const direct = String(block?.block_type || block?.type || "").trim().toLowerCase();
  if (direct) return direct;
  return "text";
}

function readContent(block) {
  const content = block?.content;
  if (typeof content === "string") return content;
  if (content && typeof content === "object") {
    if (typeof content.title === "string" && content.title.trim()) return content.title.trim();
    if (typeof content.body === "string" && content.body.trim()) return content.body.trim();
    if (typeof content.text === "string" && content.text.trim()) return content.text.trim();
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

function addCardFrame({ pptx, slide, card, theme, style }) {
  const roundedRect = pptx?.shapes?.ROUNDED_RECTANGLE || "roundRect";
  slide.addShape(roundedRect, {
    x: card.x,
    y: card.y,
    w: card.w,
    h: card.h,
    rectRadius: safeRecipe(style).cardRadius,
    fill: { color: theme.cardBg || theme.white || "FFFFFF", transparency: 2 },
    line: { color: theme.borderColor || theme.light || "E2E8F0", pt: 0.6 },
    shadow: { type: "outer", blur: 2, opacity: 0.08, color: "000000" },
  });
}

function resolveImageUrl(block) {
  const content = block?.content && typeof block.content === "object" ? block.content : {};
  const data = block?.data && typeof block.data === "object" ? block.data : {};
  const candidates = [
    content.url,
    content.src,
    content.imageUrl,
    data.url,
    data.src,
    data.imageUrl,
    block?.url,
    block?.src,
    block?.imageUrl,
  ];
  for (const item of candidates) {
    const value = String(item || "").trim();
    if (value) return value;
  }
  return "";
}

function renderTextCard(ctx) {
  const { slide, card, theme, block } = ctx;
  const text = readContent(block) || "Content";
  slide.addText(text, {
    x: card.x + 0.18,
    y: card.y + 0.14,
    w: card.w - 0.36,
    h: card.h - 0.28,
    fontSize: 14,
    color: theme.darkText || "1E293B",
    valign: "top",
  });
}

function renderIconTextCard(ctx) {
  const { slide, card, theme, block } = ctx;
  const contentObj = block?.content && typeof block.content === "object" ? block.content : {};
  const dataObj = block?.data && typeof block.data === "object" ? block.data : {};
  const titleText = String(contentObj.title || dataObj.title || "").trim();
  const bodyText = String(contentObj.body || contentObj.text || readContent(block) || "").trim();
  const iconHint = String(
    block?.icon || dataObj.icon || contentObj.icon || contentObj.icon_name || dataObj.icon_name || "",
  ).trim();
  const iconName = resolveIconName({
    icon: iconHint,
    title: titleText,
    text: bodyText,
  });

  if (typeof slide.addImage === "function") {
    try {
      const iconData = renderIconDataForPptx({
        icon: iconName,
        title: titleText,
        text: bodyText,
        size: 56,
        color: theme.primary || "2F7BFF",
      });
      slide.addImage({
        data: iconData,
        x: card.x + 0.16,
        y: card.y + 0.16,
        w: 0.42,
        h: 0.42,
      });
    } catch {
      // degrade gracefully to text-only rendering
    }
  }

  if (titleText) {
    slide.addText(titleText, {
      x: card.x + 0.66,
      y: card.y + 0.16,
      w: card.w - 0.82,
      h: 0.28,
      fontSize: 13,
      color: theme.darkText || "1E293B",
      bold: true,
      valign: "top",
    });
  }

  slide.addText(bodyText || "Key point", {
    x: card.x + 0.66,
    y: card.y + (titleText ? 0.46 : 0.16),
    w: card.w - 0.82,
    h: card.h - (titleText ? 0.58 : 0.28),
    fontSize: 12,
    color: theme.darkText || "1E293B",
    valign: "top",
    breakLine: true,
  });
}

function renderImageFallbackCard(ctx, reason = "") {
  const { block } = ctx;
  const fallback = {
    ...block,
    block_type: "body",
    content: readContent(block) || (reason ? `Image unavailable: ${reason}` : "Image unavailable"),
  };
  renderTextCard({ ...ctx, block: fallback });
}

function renderImageCard(ctx) {
  const { slide, card, block } = ctx;
  const imageUrl = resolveImageUrl(block);
  const isDataUri = imageUrl.startsWith("data:image/");
  const isLocalPath = /^[A-Za-z]:\\|^\.\.?[\\/]|^\//.test(imageUrl);

  function normalizeImageDataForPptx(dataUri) {
    const raw = String(dataUri || "").trim();
    const base64Match = raw.match(/^data:(image\/[a-zA-Z0-9+.-]+);base64,(.+)$/i);
    if (base64Match) return `${base64Match[1]};base64,${base64Match[2]}`;
    const utf8Match = raw.match(/^data:(image\/[a-zA-Z0-9+.-]+);utf8,(.+)$/i);
    if (utf8Match) {
      try {
        const decoded = decodeURIComponent(utf8Match[2]);
        const b64 = Buffer.from(decoded, "utf-8").toString("base64");
        return `${utf8Match[1]};base64,${b64}`;
      } catch {
        return raw;
      }
    }
    return raw;
  }

  if (imageUrl && typeof slide.addImage === "function" && (isDataUri || isLocalPath)) {
    try {
      const opts = {
        x: card.x + 0.08,
        y: card.y + 0.08,
        w: card.w - 0.16,
        h: card.h - 0.16,
      };
      if (isDataUri) {
        slide.addImage({ data: normalizeImageDataForPptx(imageUrl), ...opts });
      } else {
        slide.addImage({ path: imageUrl, ...opts });
      }
      return;
    } catch {
      renderImageFallbackCard(ctx, "image load failed");
      return;
    }
  }
  renderImageFallbackCard(ctx, imageUrl ? "unsupported source" : "missing image source");
}

function renderListCard(ctx) {
  const { slide, card, theme, block } = ctx;
  const raw = readContent(block) || "";
  const lines = raw
    .split(/[;\n]/)
    .map((v) => String(v || "").trim())
    .filter(Boolean)
    .slice(0, 6);
  const listText = lines.length ? lines.map((v) => `- ${v}`).join("\n") : "- Key point";
  slide.addText(listText, {
    x: card.x + 0.18,
    y: card.y + 0.14,
    w: card.w - 0.36,
    h: card.h - 0.28,
    fontSize: 13,
    color: theme.darkText || "1E293B",
    valign: "top",
    breakLine: true,
  });
}

function renderKpiCard(ctx) {
  const { slide, card, theme, block } = ctx;
  const data = block?.data || block?.content || {};
  if (data.number === undefined || data.number === null || data.unit === undefined || data.trend === undefined) {
    throw createRenderError(
      "kpi_data_missing",
      "KPI block requires number, unit, and trend fields.",
    );
  }
  const number = data.number ?? "--";
  const unit = String(data.unit || "");
  const trend = Number(data.trend || 0);
  const trendText = Number.isFinite(trend) ? `${trend >= 0 ? "+" : "-"}${Math.abs(trend)}%` : "";

  slide.addText(String(number), {
    x: card.x + 0.18,
    y: card.y + 0.12,
    w: card.w - 0.36,
    h: Math.min(0.95, card.h * 0.6),
    fontSize: card.h > 1.8 ? 34 : 26,
    color: theme.primary || "2563EB",
    bold: true,
  });
  slide.addText(unit, {
    x: card.x + 0.18,
    y: card.y + card.h * 0.48,
    w: card.w - 0.36,
    h: 0.25,
    fontSize: 11,
    color: theme.secondary || "475569",
  });
  if (trendText) {
    slide.addText(trendText, {
      x: card.x + 0.18,
      y: card.y + card.h - 0.38,
      w: card.w - 0.36,
      h: 0.22,
      fontSize: 11,
      color: trend >= 0 ? (theme.success || "22C55E") : (theme.danger || "EF4444"),
      bold: true,
    });
  }
}

function isNumericCell(value) {
  if (typeof value === "number") return Number.isFinite(value);
  const text = String(value ?? "").trim();
  if (!text) return false;
  return /^-?\d+(\.\d+)?%?$/.test(text.replace(/,/g, ""));
}

function normalizeTableMatrix(block) {
  const source = [block?.data, block?.content, block].find((v) => v && typeof v === "object") || {};
  const headers = Array.isArray(source.headers)
    ? source.headers.map((v) => String(v ?? "").trim()).filter(Boolean)
    : [];
  const rows = Array.isArray(source.rows) ? source.rows : [];

  if (headers.length > 0 && rows.length > 0) {
    return {
      headers,
      rows: rows
        .filter((row) => Array.isArray(row))
        .map((row) => row.slice(0, headers.length).map((cell) => String(cell ?? "").trim())),
    };
  }

  const tableRows = Array.isArray(source.table_rows)
    ? source.table_rows
    : Array.isArray(source.tableRows)
      ? source.tableRows
      : [];
  if (!tableRows.length || !Array.isArray(tableRows[0])) return { headers: [], rows: [] };

  const normalizedRows = tableRows
    .filter((row) => Array.isArray(row))
    .map((row) => row.map((cell) => String(cell ?? "").trim()));
  const firstRow = normalizedRows[0] || [];
  const bodyRows = normalizedRows.slice(1);
  return { headers: firstRow, rows: bodyRows };
}

function renderTableCard(ctx) {
  const { slide, card, theme, block } = ctx;
  const matrix = normalizeTableMatrix(block);
  if (!Array.isArray(matrix.headers) || matrix.headers.length === 0 || !Array.isArray(matrix.rows)) {
    return renderTextCard(ctx);
  }

  if (typeof slide.addTable !== "function") {
    const fallback = [
      matrix.headers.join(" | "),
      ...matrix.rows.slice(0, 5).map((row) => row.join(" | ")),
    ].join("\n");
    slide.addText(fallback, {
      x: card.x + 0.18,
      y: card.y + 0.14,
      w: card.w - 0.36,
      h: card.h - 0.28,
      fontSize: 10,
      color: theme.darkText || "1E293B",
      valign: "top",
      breakLine: true,
    });
    return;
  }

  const headerCells = matrix.headers.map((header) => ({
    text: String(header || ""),
    options: {
      bold: true,
      fontSize: 10,
      color: theme.white || "FFFFFF",
      fill: { color: theme.primary || "2563EB" },
      align: "center",
      valign: "mid",
      margin: { top: 0.03, bottom: 0.03, left: 0.03, right: 0.03 },
    },
  }));
  const bodyCells = matrix.rows.slice(0, 8).map((row, rowIdx) =>
    matrix.headers.map((_, colIdx) => {
      const cell = row[colIdx] ?? "";
      return {
        text: String(cell),
        options: {
          fontSize: 9,
          color: theme.darkText || "1E293B",
          fill: { color: rowIdx % 2 === 0 ? (theme.white || "FFFFFF") : (theme.light || "E2E8F0") },
          align: isNumericCell(cell) ? "right" : "left",
          valign: "mid",
          margin: { top: 0.03, bottom: 0.03, left: 0.03, right: 0.03 },
        },
      };
    }),
  );

  slide.addTable([headerCells, ...bodyCells], {
    x: card.x + 0.12,
    y: card.y + 0.12,
    w: card.w - 0.24,
    h: card.h - 0.24,
    border: { type: "solid", pt: 0.4, color: theme.light || "E2E8F0" },
    colW: matrix.headers.map(() => (card.w - 0.24) / matrix.headers.length),
    autoPage: false,
  });
}

function renderChartCard(ctx) {
  const { pptx, slide, card, theme, block } = ctx;
  const data = block?.data || block?.content || {};
  const labels = Array.isArray(data.labels) ? data.labels : [];
  const datasets = Array.isArray(data.datasets) ? data.datasets : [];
  if (labels.length === 0 || datasets.length === 0) {
    throw createRenderError(
      "chart_data_missing",
      "Chart block requires labels and datasets.",
    );
  }
  const chartType = inferChartTypeFromBlock(block);
  if (isNonStandardChartType(chartType)) {
    const rendered = renderNonStandardChartInCard({
      slide,
      pptx,
      card,
      theme,
      data: {
        chartType,
        labels,
        datasets,
        title: String(block?.content?.title || block?.title || "").trim(),
      },
    });
    if (rendered?.applied) return;
  }
  if (typeof slide.addChart !== "function") {
    throw createRenderError(
      "chart_data_missing",
      "Chart block requires addChart support for standard chart types.",
    );
  }
  createChart(
    slide,
    pptx,
    chartType,
    datasets.map((d) => ({
      name: String(d.label || "Series"),
      labels,
      values: Array.isArray(d.data) ? d.data : [],
    })),
    {
      x: card.x + 0.14,
      y: card.y + 0.14,
      w: card.w - 0.28,
      h: card.h - 0.28,
    },
    theme,
  );
}

function normalizeTimelineItems(sourceSlide) {
  const rawItems = Array.isArray(sourceSlide?.timeline_items) ? sourceSlide.timeline_items : [];
  const out = [];
  for (const item of rawItems) {
    if (!item || typeof item !== "object") continue;
    const label = String(item.label || "").trim();
    const description = String(item.description || "").trim();
    if (!label || !description) continue;
    out.push({ label, description });
    if (out.length >= 5) break;
  }
  if (out.length > 0) return out;

  const blocks = Array.isArray(sourceSlide?.blocks) ? sourceSlide.blocks : [];
  const snippets = [];
  for (const block of blocks) {
    if (!block || typeof block !== "object") continue;
    const content = typeof block.content === "string" ? block.content : "";
    for (const piece of content.split(/[;\n]/)) {
      const value = String(piece || "").trim();
      if (!value) continue;
      snippets.push(value);
      if (snippets.length >= 5) break;
    }
    if (snippets.length >= 5) break;
  }
  if (snippets.length > 0) {
    const zh = /[\u4e00-\u9fff]/.test(snippets.join(""));
    return snippets.slice(0, 5).map((text, idx) => ({
      label: zh ? `阶段${idx + 1}` : `Step ${idx + 1}`,
      description: text,
    }));
  }

  return [
    { label: "Step 1", description: "Define scope and objective." },
    { label: "Step 2", description: "Execute core workflow and iterate." },
    { label: "Step 3", description: "Review outcomes and scale." },
  ];
}

export function renderTimelineSlide({ pptx, slide, grid, sourceSlide, theme }) {
  if (!grid?.axis || !Array.isArray(grid.cards) || grid.cards.length === 0) {
    return false;
  }
  const items = normalizeTimelineItems(sourceSlide);

  const lineShape = pptx?.shapes?.LINE || "line";
  const ovalShape = pptx?.shapes?.OVAL || "ellipse";
  slide.addShape(lineShape, {
    x: grid.axis.x1,
    y: grid.axis.y,
    w: grid.axis.x2 - grid.axis.x1,
    h: 0,
    line: { color: theme.secondary || "64748B", width: 1.2 },
  });

  items.forEach((item, idx) => {
    if (idx >= grid.cards.length) return;
    const card = grid.cards[idx];
    const dotX = card.x + card.w / 2 - 0.07;
    const dotY = grid.axis.y - 0.07;
    slide.addShape(ovalShape, {
      x: dotX,
      y: dotY,
      w: 0.14,
      h: 0.14,
      fill: { color: theme.primary || "2563EB" },
      line: { color: theme.primary || "2563EB", pt: 0.2 },
    });
    slide.addText(item.label, {
      x: card.x,
      y: grid.axis.y - 0.45,
      w: card.w,
      h: 0.25,
      fontSize: 10,
      bold: true,
      color: theme.primary || "2563EB",
      align: "center",
    });
    slide.addText(item.description, {
      x: card.x + 0.02,
      y: grid.axis.y + 0.2,
      w: card.w - 0.04,
      h: Math.max(0.8, card.h - 0.4),
      fontSize: 9,
      color: theme.darkText || "1E293B",
      align: "center",
      valign: "top",
      breakLine: true,
    });
  });
  return true;
}

function renderComparisonCard(ctx) {
  const { slide, card, theme, block } = ctx;
  const text = readContent(block) || "A vs B";
  const [leftRaw, rightRaw] = text.split("|");
  const left = String(leftRaw || "A").trim();
  const right = String(rightRaw || "B").trim();
  slide.addText(left, {
    x: card.x + 0.14,
    y: card.y + 0.16,
    w: (card.w - 0.28) / 2,
    h: card.h - 0.32,
    fontSize: 13,
    color: theme.darkText || "1E293B",
    bold: true,
  });
  slide.addText(right, {
    x: card.x + card.w / 2,
    y: card.y + 0.16,
    w: (card.w - 0.28) / 2,
    h: card.h - 0.32,
    fontSize: 13,
    color: theme.darkText || "1E293B",
    bold: true,
  });
}

const RENDERERS = {
  text: renderTextCard,
  body: renderTextCard,
  title: renderTextCard,
  subtitle: renderTextCard,
  icon_text: renderIconTextCard,
  quote: renderTextCard,
  image: renderImageCard,
  list: renderListCard,
  kpi: renderKpiCard,
  chart: renderChartCard,
  comparison: renderComparisonCard,
  table: renderTableCard,
};

export function renderCard({ pptx, slide, card, block, theme, style }) {
  addCardFrame({ pptx, slide, card, theme, style });
  const type = blockType(block);
  const renderer = RENDERERS[type] || renderTextCard;
  renderer({ pptx, slide, card, block, theme, style });
}

export function canRenderBentoSlide(sourceSlide) {
  const gridName = String(sourceSlide?.layout_grid || "").trim();
  const blocks = sourceSlide?.blocks;
  if (!gridName || !Array.isArray(blocks) || blocks.length === 0) return false;
  return validateGrid(gridName);
}

export function renderBentoSlide({ pptx, slide, sourceSlide, theme, style }) {
  if (!canRenderBentoSlide(sourceSlide)) return false;
  const blocks = Array.isArray(sourceSlide.blocks) ? sourceSlide.blocks : [];
  const gridName = String(sourceSlide.layout_grid);
  const grid = getGrid(gridName);
  if (!grid) return false;

  if (gridName === "timeline") {
    return renderTimelineSlide({ pptx, slide, grid, sourceSlide, theme, style });
  }

  const titleBlock = blocks.find((block) => blockType(block) === "title");
  const titleText = readContent(titleBlock);
  if (titleText) {
    slide.addText(titleText, {
      x: 0.42,
      y: 0.1,
      w: 9.12,
      h: 0.34,
      fontSize: 16,
      bold: true,
      color: theme.darkText || "1E293B",
      margin: 0,
    });
    slide.addShape("line", {
      x: 0.42,
      y: 0.45,
      w: 9.08,
      h: 0,
      line: { color: theme.borderColor || theme.light || "E2E8F0", pt: 0.6, transparency: 24 },
    });
  }

  const textLikeTypes = new Set(["title", "subtitle", "text", "body", "list", "quote", "icon_text", "comparison"]);
  const seenBlockSignatures = new Set();
  const selectedByCard = new Map();

  blocks.forEach((block, idx) => {
    const t = blockType(block);
    if (t === "title") return;
    const textKey = normalizeTextKey(readContent(block));
    const signature = textLikeTypes.has(t) && textKey ? `text:${textKey}` : `${t}:${textKey}`;
    if (seenBlockSignatures.has(signature)) return;
    seenBlockSignatures.add(signature);

    const card = getCardById(gridName, block?.card_id || block?.id, idx);
    if (!card) return;
    if (!selectedByCard.has(card.id)) {
      selectedByCard.set(card.id, { card, block });
      return;
    }

    const existing = selectedByCard.get(card.id);
    const existingType = blockType(existing.block);
    const incomingType = t;
    const existingIsText = textLikeTypes.has(existingType);
    const incomingIsText = textLikeTypes.has(incomingType);
    if (existingIsText && incomingIsText) {
      const merged = [readContent(existing.block), readContent(block)]
        .map((v) => String(v || "").trim())
        .filter(Boolean)
        .filter((v, i, arr) => arr.findIndex((it) => normalizeTextKey(it) === normalizeTextKey(v)) === i)
        .join("; ");
      selectedByCard.set(card.id, {
        card,
        block: { ...existing.block, block_type: existingType === "list" ? "list" : "body", content: merged },
      });
    }
  });

  for (const { card, block } of selectedByCard.values()) {
    renderCard({ pptx, slide, card, block, theme, style });
  }
  return true;
}



