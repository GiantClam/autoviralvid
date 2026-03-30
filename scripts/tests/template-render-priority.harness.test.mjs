import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const INLINE_IMAGE =
  "data:image/png;base64," +
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR42mNk+M/wHwAE/wJ/lQJ6NwAAAABJRU5ErkJggg==";

test("locked template with local renderer should not be preempted by bento", () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "template-priority-"));
  const scriptPath = fileURLToPath(new URL("../generate-pptx-minimax.mjs", import.meta.url));
  const inputPath = path.join(workDir, "input.json");
  const outputPath = path.join(workDir, "out.pptx");
  const renderPath = path.join(workDir, "out.render.json");

  const payload = {
    title: "Template Priority Test",
    theme: { palette: "platinum_white_gold", style: "soft" },
    generator_mode: "official",
    original_style: true,
    disable_local_style_rewrite: true,
    slides: [
      {
        slide_id: "s1",
        page_number: 1,
        slide_type: "cover",
        layout_grid: "hero_1",
        template_family: "hero_tech_cover",
        template_lock: true,
        title: "Cover",
        blocks: [
          { block_type: "title", card_id: "title", content: "Cover" },
          { block_type: "subtitle", card_id: "sub", content: "Subtitle" },
        ],
      },
      {
        slide_id: "s2",
        page_number: 2,
        slide_type: "content",
        layout_grid: "grid_4",
        template_family: "neural_blueprint_light",
        template_lock: true,
        title: "Workflow Blueprint",
        blocks: [
          { block_type: "title", card_id: "title", content: "Workflow Blueprint" },
          { block_type: "body", card_id: "body", content: "RAG orchestration and guardrails", emphasis: ["RAG"] },
          { block_type: "list", card_id: "list", content: "Planner; Executor; Evaluator", emphasis: ["Evaluator"] },
          { block_type: "image", card_id: "image", content: { url: INLINE_IMAGE, title: "preview" }, emphasis: ["preview"] },
        ],
      },
      {
        slide_id: "s3",
        page_number: 3,
        slide_type: "content",
        layout_grid: "grid_4",
        template_family: "bento_mosaic_dark",
        template_lock: true,
        title: "Mosaic Signals",
        blocks: [
          { block_type: "title", card_id: "title", content: "Mosaic Signals" },
          { block_type: "body", card_id: "major", content: "North star KPI and channel performance", emphasis: ["North star KPI"] },
          { block_type: "list", card_id: "left", content: "Pipeline;Conversion;Retention", emphasis: ["Conversion"] },
          { block_type: "kpi", card_id: "right", content: "126%", data: { number: 126, unit: "%", trend: 9 }, emphasis: ["126%"] },
          { block_type: "image", card_id: "center", content: { url: INLINE_IMAGE, title: "snapshot" }, emphasis: ["snapshot"] },
        ],
      },
      {
        slide_id: "s4",
        page_number: 4,
        slide_type: "content",
        layout_grid: "grid_4",
        template_family: "bento_mosaic_dark",
        template_lock: true,
        title: "Capability Mismatch",
        blocks: [
          { block_type: "title", card_id: "title", content: "Capability Mismatch" },
          { block_type: "body", card_id: "body", content: "Should fallback to generic renderer branch", emphasis: ["fallback"] },
          { block_type: "list", card_id: "list", content: "Signal A;Signal B;Signal C", emphasis: ["Signal C"] },
          { block_type: "chart", card_id: "chart", content: "Q1;Q2;Q3;Q4", data: { labels: ["Q1", "Q2", "Q3", "Q4"], datasets: [{ data: [23, 34, 55, 67] }] }, emphasis: ["Q4"] },
          { block_type: "image", card_id: "image", content: { title: "missing-url" }, emphasis: ["missing-url"] },
        ],
      },
      {
        slide_id: "s5",
        page_number: 5,
        slide_type: "content",
        layout_grid: "bento_5",
        template_family: "neural_blueprint_light",
        template_lock: true,
        title: "Layout Guardrail",
        blocks: [
          { block_type: "title", card_id: "title", content: "Layout Guardrail" },
          { block_type: "body", card_id: "body", content: "Template layout unsupported, fallback expected", emphasis: ["fallback"] },
          { block_type: "list", card_id: "list", content: "Alpha;Beta;Gamma", emphasis: ["Gamma"] },
          { block_type: "image", card_id: "image", content: { url: INLINE_IMAGE, title: "preview" }, emphasis: ["preview"] },
        ],
      },
    ],
  };

  try {
    writeFileSync(inputPath, JSON.stringify(payload, null, 2), "utf-8");
    execFileSync("node", [
      scriptPath,
      "--input",
      inputPath,
      "--output",
      outputPath,
      "--render-output",
      renderPath,
      "--generator-mode",
      "official",
    ]);

    const render = JSON.parse(readFileSync(renderPath, "utf-8"));
    const rendererSummary = render?.template_renderer_summary && typeof render.template_renderer_summary === "object"
      ? render.template_renderer_summary
      : null;
    const slide2 = Array.isArray(render?.slides) ? render.slides[1] : null;
    const slide3 = Array.isArray(render?.slides) ? render.slides[2] : null;
    const slide4 = Array.isArray(render?.slides) ? render.slides[3] : null;
    const slide5 = Array.isArray(render?.slides) ? render.slides[4] : null;
    assert.ok(slide2, "missing second render slide");
    assert.ok(slide3, "missing third render slide");
    assert.ok(slide4, "missing fourth render slide");
    assert.ok(slide5, "missing fifth render slide");
    assert.equal(slide2.template_family, "neural_blueprint_light");
    assert.equal(
      Number(slide2?.actions?.[0]?.startFrame || 0),
      24,
      "slide was unexpectedly rendered through generic bento path",
    );
    assert.equal(
      Array.isArray(slide2?.actions) && slide2.actions.length >= 2,
      true,
      "slide should retain content-renderer multi-action sequence",
    );
    assert.equal(slide3.template_family, "bento_mosaic_dark");
    assert.equal(
      String(slide3.slide_type || "").toLowerCase(),
      "bento_5",
      "locked bento_mosaic_dark slide should map to catalog preferred layout",
    );
    assert.equal(slide4.template_family, "bento_mosaic_dark");
    assert.equal(
      String(slide4.slide_type || "").toLowerCase(),
      "grid_4",
      "capability-mismatch slide should fallback to generic layout mapping",
    );
    assert.equal(
      Number(slide4?.actions?.[0]?.startFrame || 0),
      24,
      "capability-mismatch slide should use generic content action timing",
    );
    assert.equal(Boolean(slide4?.template_renderer?.skipped), true, "slide4 should mark template renderer fallback");
    assert.equal(
      String(slide4?.template_renderer?.reason || ""),
      "unsupported_block_types",
      "slide4 fallback reason should indicate block capability mismatch",
    );
    assert.equal(
      Array.isArray(slide4?.template_renderer?.unsupported_block_types)
      && slide4.template_renderer.unsupported_block_types.includes("chart"),
      true,
      "slide4 diagnostics should include unsupported chart block",
    );
    assert.equal(slide5.template_family, "neural_blueprint_light");
    assert.equal(
      String(slide5.slide_type || "").toLowerCase(),
      "bento_5",
      "layout-mismatch slide should fallback to source layout mapping",
    );
    assert.equal(
      Number(slide5?.actions?.[0]?.startFrame || 0),
      24,
      "layout-mismatch slide should use generic content action timing",
    );
    assert.equal(Boolean(slide5?.template_renderer?.skipped), true, "slide5 should mark template renderer fallback");
    assert.equal(
      String(slide5?.template_renderer?.reason || ""),
      "unsupported_layout",
      "slide5 fallback reason should indicate layout mismatch",
    );
    assert.equal(Boolean(slide5?.template_renderer?.unsupported_layout), true, "slide5 diagnostics should flag unsupported layout");
    assert.ok(rendererSummary, "missing template_renderer_summary");
    assert.equal(Number(rendererSummary?.evaluated_slides || 0), 4, "summary evaluated slide count mismatch");
    assert.equal(Number(rendererSummary?.skipped_slides || 0), 2, "summary skipped slide count mismatch");
    assert.equal(Number(rendererSummary?.reason_counts?.unsupported_block_types || 0), 1, "summary block mismatch count mismatch");
    assert.equal(Number(rendererSummary?.reason_counts?.unsupported_layout || 0), 1, "summary layout mismatch count mismatch");
    assert.equal(Number(rendererSummary?.mode_counts?.local_template || 0), 2, "summary local template mode count mismatch");
    assert.equal(Number(rendererSummary?.mode_counts?.fallback_generic || 0), 2, "summary fallback mode count mismatch");
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});
