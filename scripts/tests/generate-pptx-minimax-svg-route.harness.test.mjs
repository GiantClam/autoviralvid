import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

test("generator harness: render_path=svg emits svg slide metadata", () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "minimax-svg-route-"));
  const scriptPath = fileURLToPath(new URL("../generate-pptx-minimax.mjs", import.meta.url));
  const inputPath = path.join(workDir, "input.json");
  const outputPath = path.join(workDir, "out.pptx");
  const renderOutputPath = path.join(workDir, "out.render.json");

  const payload = {
    title: "SVG Route Demo",
    author: "test",
    minimax_style_variant: "soft",
    minimax_palette_key: "pure_tech_blue",
    design_spec: {
      colors: { primary: "2F7BFF", bg: "060B17", text_primary: "E8F0FF" },
      typography: { title_font: "Microsoft YaHei", body_font: "Microsoft YaHei", body_size: 15 },
      spacing: { page_margin: 0.45, card_gap: 0.2, card_radius: 0.1, header_height: 0.68 },
      visual: { style_recipe: "soft", visual_priority: true, visual_density: "balanced" },
    },
    slides: [
      {
        page_number: 1,
        slide_type: "content",
        layout_grid: "timeline",
        template_lock: true,
        template_family: "split_media_dark",
        render_path: "svg",
        title: "Pipeline Flow",
        svg_markup:
          '<svg width="960" height="540" viewBox="0 0 960 540"><rect x="120" y="100" width="220" height="90" fill="#1F2937"/><path d="M 360 145 L 520 145 L 520 185 Z" fill="#2563EB"/><text x="140" y="155" font-size="28" fill="#FFFFFF">Stage 1</text></svg>',
        blocks: [
          { block_type: "title", card_id: "title", content: "Pipeline Flow" },
          { block_type: "body", card_id: "body", content: "吞吐提升 28%，时延下降 15%" },
          { block_type: "list", card_id: "list", content: "采集稳定;转换可靠;发布可追踪" },
          { block_type: "workflow", card_id: "main", content: "Collect -> Transform -> Deliver" },
        ],
      },
    ],
  };

  try {
    writeFileSync(inputPath, JSON.stringify(payload), "utf-8");
    execFileSync("node", [
      scriptPath,
      "--input",
      inputPath,
      "--output",
      outputPath,
      "--render-output",
      renderOutputPath,
    ]);

    const renderJson = JSON.parse(readFileSync(renderOutputPath, "utf-8"));
    const slides = Array.isArray(renderJson?.slides) ? renderJson.slides : [];
    assert.equal(slides.length >= 1, true);
    assert.equal(slides[0]?.render_path, "svg");
    assert.equal(String(slides[0]?.svg_render_mode || "").length > 0, true);
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});

test("generator harness: svg-mode on does not force overlay for pptxgenjs slides", () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "minimax-svg-mode-"));
  const scriptPath = fileURLToPath(new URL("../generate-pptx-minimax.mjs", import.meta.url));
  const inputPath = path.join(workDir, "input.json");
  const outputOnPath = path.join(workDir, "on.pptx");
  const renderOnPath = path.join(workDir, "on.render.json");
  const outputForcePath = path.join(workDir, "force.pptx");
  const renderForcePath = path.join(workDir, "force.render.json");

  const payload = {
    title: "SVG Mode Semantics",
    author: "test",
    minimax_style_variant: "soft",
    minimax_palette_key: "pure_tech_blue",
    slides: [
      {
        page_number: 1,
        slide_type: "content",
        layout_grid: "split_2",
        render_path: "pptxgenjs",
        title: "Mode Check",
        blocks: [
          { block_type: "title", card_id: "title", content: "Mode Check" },
          {
            block_type: "body",
            card_id: "body",
            content: "Default on should not inject a full-page svg overlay.",
            emphasis: ["svg overlay"],
          },
          {
            block_type: "list",
            card_id: "list",
            content: "Signal A;Signal B;Signal C",
            emphasis: ["Signal B"],
          },
        ],
      },
    ],
  };

  try {
    writeFileSync(inputPath, JSON.stringify(payload), "utf-8");

    execFileSync("node", [
      scriptPath,
      "--input",
      inputPath,
      "--output",
      outputOnPath,
      "--render-output",
      renderOnPath,
      "--svg-mode",
      "on",
    ]);
    execFileSync("node", [
      scriptPath,
      "--input",
      inputPath,
      "--output",
      outputForcePath,
      "--render-output",
      renderForcePath,
      "--svg-mode",
      "force",
    ]);

    const renderOn = JSON.parse(readFileSync(renderOnPath, "utf-8"));
    const renderForce = JSON.parse(readFileSync(renderForcePath, "utf-8"));
    const onSlide = Array.isArray(renderOn?.slides) ? renderOn.slides[0] : null;
    const forceSlide = Array.isArray(renderForce?.slides) ? renderForce.slides[0] : null;
    assert.ok(onSlide, "missing slide in svg-mode on output");
    assert.ok(forceSlide, "missing slide in svg-mode force output");
    assert.equal(String(onSlide.svg_render_mode || ""), "");
    assert.equal(
      String(forceSlide.svg_render_mode || "").startsWith("overlay_"),
      true,
      "svg-mode force should inject overlay layer",
    );
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});
