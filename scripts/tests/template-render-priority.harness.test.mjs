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
    const slide2 = Array.isArray(render?.slides) ? render.slides[1] : null;
    assert.ok(slide2, "missing second render slide");
    assert.equal(slide2.template_family, "neural_blueprint_light");
    assert.notEqual(
      String(slide2.slide_type || "").toLowerCase(),
      "grid_4",
      "slide was unexpectedly rendered through bento path",
    );
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});

