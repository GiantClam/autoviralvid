#!/usr/bin/env node
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const VISUAL_TYPES = new Set(["image", "chart", "kpi", "workflow", "diagram", "table"]);
const TERMINAL_TYPES = new Set(["cover", "summary", "toc", "divider", "hero_1"]);

function parseArgs(argv) {
  const args = {
    files: [],
    minVisualAnchorRatio: 0.8,
    maxTextOnlyContentSlides: 0,
    minTemplateDiversity: 2,
    requireOfficialContentBlocks: true,
    reportPath: "",
  };
  for (let i = 0; i < argv.length; i += 1) {
    const token = String(argv[i] || "").trim();
    if (!token) continue;
    if (token === "--min-visual-anchor-ratio") {
      args.minVisualAnchorRatio = Number(argv[i + 1] || 0.8);
      i += 1;
      continue;
    }
    if (token === "--max-text-only-content-slides") {
      args.maxTextOnlyContentSlides = Number(argv[i + 1] || 0);
      i += 1;
      continue;
    }
    if (token === "--min-template-diversity") {
      args.minTemplateDiversity = Number(argv[i + 1] || 2);
      i += 1;
      continue;
    }
    if (token === "--skip-official-content-check") {
      args.requireOfficialContentBlocks = false;
      continue;
    }
    if (token === "--report-path") {
      args.reportPath = String(argv[i + 1] || "").trim();
      i += 1;
      continue;
    }
    if (token.startsWith("--")) {
      throw new Error(`Unknown option: ${token}`);
    }
    args.files.push(token);
  }
  if (!args.files.length) {
    throw new Error(
      "Usage: node scripts/tests/validate-render-metrics.mjs <render.json> [more...] " +
      "[--min-visual-anchor-ratio 0.8] [--max-text-only-content-slides 0] [--min-template-diversity 2]",
    );
  }
  return args;
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function normalizeType(value) {
  return String(value || "").trim().toLowerCase();
}

function isContentSlide(slide) {
  const slideType = normalizeType(slide?.slide_type || slide?.type);
  if (slideType && TERMINAL_TYPES.has(slideType)) return false;
  const pageType = normalizeType(slide?.page_type || slide?.pageType);
  if (pageType && TERMINAL_TYPES.has(pageType)) return false;
  return true;
}

function hasVisualBlock(slide) {
  const blocks = asArray(slide?.blocks);
  return blocks.some((block) => VISUAL_TYPES.has(normalizeType(block?.block_type || block?.type)));
}

function computeMetrics(renderJson) {
  const officialSlides = asArray(renderJson?.official_input?.slides);
  const officialContent = officialSlides.filter(
    (slide) => normalizeType(slide?.page_type || slide?.slide_type) === "content",
  );
  const officialEmpty = officialContent.filter((slide) => asArray(slide?.blocks).length === 0);
  const officialVisual = officialContent.filter(hasVisualBlock);
  const officialTextOnly = officialContent.filter((slide) => !hasVisualBlock(slide));

  const renderSlides = asArray(renderJson?.slides);
  const renderContent = renderSlides.filter(isContentSlide);
  const contentTemplates = new Set(
    renderContent
      .map((slide) => normalizeType(slide?.template_family || slide?.template_id))
      .filter(Boolean),
  );

  return {
    totalSlides: renderSlides.length || officialSlides.length,
    contentSlides: officialContent.length || renderContent.length,
    visualAnchorSlides: officialVisual.length,
    textOnlyContentSlides: officialTextOnly.length,
    visualAnchorRatio:
      officialContent.length > 0 ? Number((officialVisual.length / officialContent.length).toFixed(4)) : 1,
    templateDiversity: contentTemplates.size,
    officialContentSlides: officialContent.length,
    officialEmptyContentSlides: officialEmpty.length,
  };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const failures = [];
  const results = [];

  for (const file of args.files) {
    const abs = resolve(file);
    const json = JSON.parse(readFileSync(abs, "utf-8"));
    const metrics = computeMetrics(json);
    results.push({ file: abs, metrics });
    console.log(JSON.stringify({ file: abs, metrics }, null, 2));

    if (metrics.visualAnchorRatio < args.minVisualAnchorRatio) {
      failures.push(
        `${abs}: visual_anchor_ratio=${metrics.visualAnchorRatio} < ${args.minVisualAnchorRatio}`,
      );
    }
    if (metrics.textOnlyContentSlides > args.maxTextOnlyContentSlides) {
      failures.push(
        `${abs}: text_only_content_slides=${metrics.textOnlyContentSlides} > ${args.maxTextOnlyContentSlides}`,
      );
    }
    if (metrics.contentSlides >= 3 && metrics.templateDiversity < args.minTemplateDiversity) {
      failures.push(
        `${abs}: template_diversity=${metrics.templateDiversity} < ${args.minTemplateDiversity}`,
      );
    }
    if (args.requireOfficialContentBlocks && metrics.officialEmptyContentSlides > 0) {
      failures.push(
        `${abs}: official_input has ${metrics.officialEmptyContentSlides} content slides with empty blocks`,
      );
    }
  }

  const report = {
    ok: failures.length === 0,
    config: {
      minVisualAnchorRatio: args.minVisualAnchorRatio,
      maxTextOnlyContentSlides: args.maxTextOnlyContentSlides,
      minTemplateDiversity: args.minTemplateDiversity,
      requireOfficialContentBlocks: args.requireOfficialContentBlocks,
    },
    results,
    failures,
  };
  if (args.reportPath) {
    const reportAbs = resolve(args.reportPath);
    writeFileSync(reportAbs, JSON.stringify(report, null, 2), "utf-8");
  }

  if (failures.length) {
    console.error(JSON.stringify({ ok: false, failures }, null, 2));
    process.exit(1);
  }
  console.log(JSON.stringify({ ok: true }, null, 2));
}

main();
