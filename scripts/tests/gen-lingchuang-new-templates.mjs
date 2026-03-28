#!/usr/bin/env node
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const INLINE_IMAGE =
  "data:image/png;base64," +
  "iVBORw0KGgoAAAANSUhEUgAAAlgAAAFvCAYAAABgJfQbAAAACXBIWXMAAAsSAAALEgHS3X78AAAB" +
  "k0lEQVR4nO3RMQEAIAzAMMC/5yFjCxIFfXpn5gAA4C4DgIYBAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" +
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPwGfGAAAZq" +
  "mEToAAAAASUVORK5CYII=";

const EXPECTED_FAMILIES = [
  "hero_tech_cover",
  "architecture_dark_panel",
  "neural_blueprint_light",
  "consulting_warm_light",
  "dashboard_dark",
  "ecosystem_orange_dark",
  "ops_lifecycle_light",
  "split_media_dark",
  "architecture_dark_panel",
  "hero_dark",
];

function parseArgs(argv) {
  const args = {
    outputDir: "test_outputs/lingchuang_new_templates",
    strict: true,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const token = String(argv[i] || "").trim();
    if (!token) continue;
    if (token === "--output-dir") {
      args.outputDir = String(argv[i + 1] || args.outputDir).trim();
      i += 1;
      continue;
    }
    if (token === "--no-strict") {
      args.strict = false;
      continue;
    }
    throw new Error(`Unknown option: ${token}`);
  }
  return args;
}

function buildInput() {
  return {
    title: "\u7075\u521b\u667a\u80fd\uff1aAI\u8425\u9500\u4e0e\u6570\u5b57\u4eba\u589e\u957f\u5f15\u64ce",
    author: "\u7075\u521b\u667a\u80fd",
    generator_mode: "official",
    original_style: true,
    disable_local_style_rewrite: true,
    visual_priority: false,
    svg_mode: "off",
    visual_density: "dense",
    constraint_hardness: "balanced",
    theme: {
      palette: "platinum_white_gold",
      style: "soft",
    },
    slides: [
      {
        slide_id: "lc-01",
        page_number: 1,
        slide_type: "cover",
        layout_grid: "hero_1",
        template_family: "hero_tech_cover",
        template_lock: true,
        title: "\u7075\u521b\u667a\u80fd\uff1a\u4ece\u201c\u5199\u4ee3\u7801\u201d\u5230\u201c\u7f16\u6392\u4e1a\u52a1\u201d\u7684\u8dc3\u8fc1",
        blocks: [
          { block_type: "title", card_id: "title", content: "\u7075\u521b\u667a\u80fd\uff1a\u4ece\u201c\u5199\u4ee3\u7801\u201d\u5230\u201c\u7f16\u6392\u4e1a\u52a1\u201d\u7684\u8dc3\u8fc1" },
          { block_type: "subtitle", card_id: "subtitle", content: "\u4f01\u4e1a\u7ea7 AI \u5de5\u4f5c\u6d41 + LLMOps \u4e00\u4f53\u5316\u4ea4\u4ed8\u4f53\u7cfb" },
        ],
      },
      {
        slide_id: "lc-02",
        page_number: 2,
        slide_type: "content",
        layout_grid: "template_canvas",
        template_family: "architecture_dark_panel",
        template_lock: true,
        title: "\u53ef\u89c6\u5316\u7f16\u6392\u67b6\u6784",
        blocks: [
          { block_type: "title", card_id: "title", content: "\u53ef\u89c6\u5316\u7f16\u6392\u67b6\u6784" },
          { block_type: "body", card_id: "body", content: "\u4e1a\u52a1 DSL\u3001\u6d41\u7a0b\u7f16\u6392\u5f15\u64ce\u3001\u6267\u884c\u6cbb\u7406\u4e09\u5c42\u89e3\u8026", emphasis: ["\u4e09\u5c42"] },
          { block_type: "list", card_id: "list", content: "\u58f0\u660e\u5f0f\u5de5\u4f5c\u6d41; \u8282\u70b9\u7ea7\u7070\u5ea6; \u53ef\u89c2\u6d4b\u53ef\u56de\u653e", emphasis: ["\u7070\u5ea6"] },
          { block_type: "workflow", card_id: "wf", content: "Planner -> Executor -> Guardrail -> Feedback", emphasis: ["Guardrail"] },
        ],
      },
      {
        slide_id: "lc-03",
        page_number: 3,
        slide_type: "content",
        layout_grid: "template_canvas",
        template_family: "neural_blueprint_light",
        template_lock: true,
        title: "\u96f6\u4ee3\u7801 Workflow \u9884\u89c8",
        blocks: [
          { block_type: "title", card_id: "title", content: "\u96f6\u4ee3\u7801 Workflow \u9884\u89c8" },
          { block_type: "body", card_id: "body", content: "\u62d6\u62fd\u5373\u53ef\u62fc\u88c5 RAG + Agent \u4efb\u52a1\u94fe\u8def", emphasis: ["RAG"] },
          { block_type: "list", card_id: "list", content: "\u8282\u70b9\u5c01\u88c5; \u8def\u7531\u7f16\u6392; \u6548\u679c\u8bc4\u4f30", emphasis: ["\u8bc4\u4f30"] },
          { block_type: "image", card_id: "image", content: { url: INLINE_IMAGE, title: "workflow-screen" }, emphasis: ["UI"] },
        ],
      },
      {
        slide_id: "lc-04",
        page_number: 4,
        slide_type: "content",
        layout_grid: "template_canvas",
        template_family: "consulting_warm_light",
        template_lock: true,
        title: "\u987e\u95ee\u5f0f\u4ea4\u4ed8\u65b9\u6cd5\u8bba",
        blocks: [
          { block_type: "title", card_id: "title", content: "\u987e\u95ee\u5f0f\u4ea4\u4ed8\u65b9\u6cd5\u8bba" },
          { block_type: "body", card_id: "body", content: "\u4ece\u8bca\u65ad\u5230\u8bd5\u70b9\u518d\u5230\u653e\u91cf\uff0c12 \u5468\u95ed\u73af\u843d\u5730", emphasis: ["12\u5468"] },
          { block_type: "list", card_id: "list", content: "\u8bca\u65ad; \u8bd5\u70b9; \u590d\u5236; \u6cbb\u7406", emphasis: ["\u590d\u5236"] },
          { block_type: "image", card_id: "image", content: { url: INLINE_IMAGE, title: "case-board" }, emphasis: ["\u6848\u4f8b"] },
        ],
      },
      {
        slide_id: "lc-05",
        page_number: 5,
        slide_type: "data",
        layout_grid: "grid_3",
        template_family: "dashboard_dark",
        template_lock: true,
        title: "ROI \u4e0e\u589e\u957f\u770b\u677f",
        blocks: [
          { block_type: "title", card_id: "title", content: "ROI \u4e0e\u589e\u957f\u770b\u677f" },
          { block_type: "body", card_id: "c1", content: "\u5185\u5bb9\u4ea7\u80fd\u3001\u8f6c\u5316\u6548\u7387\u3001\u534f\u540c\u6548\u7387\u540c\u65f6\u63d0\u5347", emphasis: ["\u63d0\u5347"] },
          { block_type: "list", card_id: "c1", content: "\u7ebf\u7d22\u8f6c\u5316 +22%; CPA \u4e0b\u964d 31%; \u5185\u5bb9\u4ea4\u4ed8 +3.4x", emphasis: ["3.4x"] },
          {
            block_type: "chart",
            card_id: "c2",
            content: "ROI \u5b63\u5ea6\u8d8b\u52bf",
            emphasis: ["\u8d8b\u52bf"],
            data: {
              chartType: "bar",
              labels: ["Q1", "Q2", "Q3", "Q4"],
              datasets: [{ label: "ROI", data: [100, 132, 156, 181] }],
            },
          },
          { block_type: "kpi", card_id: "c3", content: "\u7efc\u5408 ROI", emphasis: ["81%"], data: { number: 81, unit: "%", trend: 12 } },
        ],
      },
      {
        slide_id: "lc-06",
        page_number: 6,
        slide_type: "content",
        layout_grid: "template_canvas",
        template_family: "ecosystem_orange_dark",
        template_lock: true,
        title: "\u751f\u6001\u5408\u4f5c\u4e0e\u6e20\u9053\u653e\u5927",
        blocks: [
          { block_type: "title", card_id: "title", content: "\u751f\u6001\u5408\u4f5c\u4e0e\u6e20\u9053\u653e\u5927" },
          { block_type: "body", card_id: "body", content: "\u5e73\u53f0-\u4f19\u4f34-\u5ba2\u6237\u4e09\u5c42\u534f\u540c\uff0c\u62c9\u9ad8\u89c4\u6a21\u589e\u957f\u6548\u7387", emphasis: ["\u4e09\u5c42"] },
          { block_type: "list", card_id: "list", content: "\u533a\u57df\u4ee3\u7406; \u8054\u8425\u670d\u52a1; \u884c\u4e1a ISV", emphasis: ["ISV"] },
          { block_type: "kpi", card_id: "kpi", content: "\u5e74\u590d\u5408\u589e\u957f", emphasis: ["35%"], data: { number: 35, unit: "%", trend: 9 } },
          { block_type: "diagram", card_id: "diagram", content: "\u5e73\u53f0 -> \u4f19\u4f34 -> \u5ba2\u6237\u7684\u751f\u6001\u6d41", emphasis: ["\u751f\u6001"] },
        ],
      },
      {
        slide_id: "lc-07",
        page_number: 7,
        slide_type: "content",
        layout_grid: "template_canvas",
        template_family: "ops_lifecycle_light",
        template_lock: true,
        title: "LLMOps \u5168\u751f\u547d\u5468\u671f",
        blocks: [
          { block_type: "title", card_id: "title", content: "LLMOps \u5168\u751f\u547d\u5468\u671f" },
          { block_type: "body", card_id: "body", content: "PromptOps + EvalOps + Observability \u7ec4\u6210\u8fd0\u8425\u95ed\u73af", emphasis: ["\u95ed\u73af"] },
          { block_type: "list", card_id: "list", content: "\u53d8\u66f4\u8bc4\u5ba1; \u5728\u7ebf\u76d1\u63a7; \u81ea\u52a8\u56de\u6eda", emphasis: ["\u56de\u6eda"] },
          { block_type: "kpi", card_id: "kpi", content: "SLA \u7a33\u5b9a\u6027", emphasis: ["99.9%"], data: { number: 99.9, unit: "%", trend: 2 } },
        ],
      },
      {
        slide_id: "lc-08",
        page_number: 8,
        slide_type: "content",
        layout_grid: "template_canvas",
        template_family: "split_media_dark",
        template_lock: true,
        title: "\u4f20\u7edf\u65b9\u6848 vs \u7075\u521b\u667a\u80fd\u65b9\u6848",
        blocks: [
          { block_type: "title", card_id: "title", content: "\u4f20\u7edf\u65b9\u6848 vs \u7075\u521b\u667a\u80fd\u65b9\u6848" },
          { block_type: "body", card_id: "body", content: "\u4f20\u7edf API \u5806\u780c\u3001\u4eba\u5de5\u6267\u884c\uff1b\u7075\u521b\u667a\u80fd\u5b9e\u73b0\u53ef\u7f16\u6392\u3001\u53ef\u6cbb\u7406", emphasis: ["\u53ef\u6cbb\u7406"] },
          { block_type: "list", card_id: "list", content: "\u6548\u7387 +10x; \u6210\u672c -90%; \u4ea4\u4ed8\u5468\u671f -60%", emphasis: ["10x"] },
          { block_type: "image", card_id: "image", content: { url: INLINE_IMAGE, title: "comparison-screen" }, emphasis: ["\u5bf9\u6bd4"] },
        ],
      },
      {
        slide_id: "lc-09",
        page_number: 9,
        slide_type: "content",
        layout_grid: "template_canvas",
        template_family: "architecture_dark_panel",
        template_lock: true,
        title: "\u843d\u5730\u8def\u7ebf\u56fe",
        blocks: [
          { block_type: "title", card_id: "title", content: "\u843d\u5730\u8def\u7ebf\u56fe" },
          { block_type: "body", card_id: "body", content: "\u4ece PoC \u5230\u89c4\u6a21\u5316\u8425\u8fd0\uff0c\u5206\u4e09\u9636\u6bb5\u63a8\u8fdb", emphasis: ["\u4e09\u9636\u6bb5"] },
          { block_type: "list", card_id: "list", content: "\u9636\u6bb51\uff1a\u8bca\u65ad; \u9636\u6bb52\uff1a\u8bd5\u70b9; \u9636\u6bb53\uff1a\u653e\u91cf", emphasis: ["\u653e\u91cf"] },
          { block_type: "workflow", card_id: "workflow", content: "Diagnose -> Pilot -> Scale -> Governance", emphasis: ["Scale"] },
        ],
      },
      {
        slide_id: "lc-10",
        page_number: 10,
        slide_type: "summary",
        layout_grid: "hero_1",
        template_family: "hero_dark",
        template_lock: true,
        title: "\u5408\u4f5c\u5efa\u8bae",
        blocks: [
          { block_type: "title", card_id: "title", content: "\u5408\u4f5c\u5efa\u8bae" },
          { block_type: "list", card_id: "main", content: "\u5148\u8bd5\u70b9\u540e\u653e\u91cf; \u4ee5 ROI \u4f5c\u4e3a\u51b3\u7b56\u6838\u5fc3; \u5efa\u7acb\u5b63\u5ea6\u5171\u521b\u673a\u5236" },
        ],
      },
    ],
  };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  mkdirSync(args.outputDir, { recursive: true });
  const inputPath = path.join(args.outputDir, "lingchuang-new-templates.input.json");
  const outputPath = path.join(args.outputDir, "lingchuang-new-templates.pptx");
  const renderPath = path.join(args.outputDir, "lingchuang-new-templates.render.json");
  const input = buildInput();
  writeFileSync(inputPath, JSON.stringify(input, null, 2), "utf-8");

  execFileSync("node", [
    "scripts/generate-pptx-minimax.mjs",
    "--input",
    inputPath,
    "--output",
    outputPath,
    "--render-output",
    renderPath,
    "--generator-mode",
    "official",
  ], { stdio: "pipe" });

  const render = JSON.parse(readFileSync(renderPath, "utf-8"));
  const actual = (Array.isArray(render?.slides) ? render.slides : []).map(
    (slide) => String(slide?.template_family || ""),
  );

  const mismatch = [];
  for (let i = 0; i < EXPECTED_FAMILIES.length; i += 1) {
    if (EXPECTED_FAMILIES[i] !== actual[i]) {
      mismatch.push({
        index: i + 1,
        expected: EXPECTED_FAMILIES[i],
        actual: actual[i] || "",
      });
    }
  }

  const summary = {
    ok: mismatch.length === 0,
    output: outputPath,
    render: renderPath,
    input: inputPath,
    expected: EXPECTED_FAMILIES,
    actual,
    mismatch,
  };
  console.log(JSON.stringify(summary, null, 2));

  if (args.strict && mismatch.length > 0) {
    throw new Error(
      "Template-lock routing mismatch. This indicates current template selection pass-through cannot " +
      "stably honor user-provided per-slide template intent.",
    );
  }
}

main();
