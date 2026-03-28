import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

test("generator harness: official input keeps non-empty blocks for content slides", () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "minimax-harness-"));
  const scriptPath = fileURLToPath(new URL("../generate-pptx-minimax.mjs", import.meta.url));
  const fixturePath = fileURLToPath(
    new URL("../../agent/renders/tmp/ppt_pipeline/d1ef781b8ac5/stage-4-render-payload.json", import.meta.url),
  );
  const outputPath = path.join(workDir, "out.pptx");
  const renderOutputPath = path.join(workDir, "out.render.json");

  try {
    execFileSync("node", [
      scriptPath,
      "--input",
      fixturePath,
      "--output",
      outputPath,
      "--render-output",
      renderOutputPath,
    ]);

    const renderJson = JSON.parse(readFileSync(renderOutputPath, "utf-8"));
    const slides = Array.isArray(renderJson?.official_input?.slides)
      ? renderJson.official_input.slides
      : [];
    const contentSlides = slides.filter(
      (slide) => String(slide?.page_type || "").toLowerCase() === "content",
    );
    assert.ok(contentSlides.length > 0, "fixture should include content slides");

    const emptyBlockSlides = contentSlides.filter(
      (slide) => !Array.isArray(slide?.blocks) || slide.blocks.length === 0,
    );
    assert.equal(
      emptyBlockSlides.length,
      0,
      `official_input content slides should keep blocks, got empty: ${emptyBlockSlides
        .map((s) => s?.slide_id || "unknown")
        .join(", ")}`,
    );
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});
