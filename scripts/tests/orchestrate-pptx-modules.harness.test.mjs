import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

test("orchestrate-pptx-modules CLI generates manifest and slide modules", () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "orchestrate-modules-"));
  const inputPath = path.join(workDir, "payload.json");
  const modulesDir = path.join(workDir, "slides");
  const scriptPath = fileURLToPath(new URL("../orchestrate-pptx-modules.mjs", import.meta.url));
  const payload = {
    title: "CLI demo",
    author: "test",
    slides: [
      {
        slide_id: "s1",
        page_number: 1,
        slide_type: "cover",
        title: "Cover",
        blocks: [
          { block_type: "title", card_id: "title", content: "Cover" },
          { block_type: "subtitle", card_id: "sub", content: "Intro" },
        ],
      },
      {
        slide_id: "s2",
        page_number: 2,
        slide_type: "summary",
        title: "Summary",
        blocks: [
          { block_type: "title", card_id: "title", content: "Summary" },
          { block_type: "list", card_id: "list", content: "Point A;Point B" },
        ],
      },
    ],
  };

  try {
    writeFileSync(inputPath, JSON.stringify(payload), "utf-8");
    const stdout = execFileSync("node", [
      scriptPath,
      "--input",
      inputPath,
      "--modules-dir",
      modulesDir,
    ], { encoding: "utf-8" });
    const result = JSON.parse(String(stdout || "").trim());
    assert.equal(result.success, true);
    assert.equal(result.module_count, 2);
    const manifest = JSON.parse(readFileSync(result.manifest_path, "utf-8"));
    assert.equal(Array.isArray(manifest.modules), true);
    assert.equal(manifest.modules.length, 2);
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});

test("orchestrate-pptx-modules compile stage emits full deck after slide-target render", () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "orchestrate-modules-compile-"));
  const inputPath = path.join(workDir, "payload.json");
  const modulesDir = path.join(workDir, "slides");
  const outputPath = path.join(workDir, "deck.pptx");
  const renderOutputPath = path.join(workDir, "deck.render.json");
  const scriptPath = fileURLToPath(new URL("../orchestrate-pptx-modules.mjs", import.meta.url));
  const payload = {
    title: "CLI compile full deck demo",
    author: "test",
    retry_scope: "slide",
    target_slide_ids: ["s2"],
    slides: [
      {
        slide_id: "s1",
        page_number: 1,
        slide_type: "cover",
        title: "Cover",
        blocks: [
          { block_type: "title", card_id: "title", content: "Cover" },
          { block_type: "subtitle", card_id: "sub", content: "Intro" },
        ],
      },
      {
        slide_id: "s2",
        page_number: 2,
        slide_type: "summary",
        title: "Summary",
        blocks: [
          { block_type: "title", card_id: "title", content: "Summary" },
          { block_type: "list", card_id: "list", content: "Done;Next" },
        ],
      },
    ],
  };

  try {
    writeFileSync(inputPath, JSON.stringify(payload), "utf-8");
    const stdout = execFileSync("node", [
      scriptPath,
      "--input",
      inputPath,
      "--modules-dir",
      modulesDir,
      "--render-each",
      "--target-slide-ids",
      "s2",
      "--compile",
      "--output",
      outputPath,
      "--render-output",
      renderOutputPath,
    ], { encoding: "utf-8" });
    const result = JSON.parse(String(stdout || "").trim());
    assert.equal(result.success, true);
    assert.equal(result.compile?.ok, true);

    const renderSpec = JSON.parse(readFileSync(renderOutputPath, "utf-8"));
    assert.equal(renderSpec.retry_scope, "deck");
    assert.equal(Array.isArray(renderSpec.slides), true);
    assert.equal(renderSpec.slides.length, 2);
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});

test("orchestrate-pptx-modules runs external subagent executor when --subagent-exec is enabled", () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "orchestrate-modules-subagent-"));
  const inputPath = path.join(workDir, "payload.json");
  const modulesDir = path.join(workDir, "slides");
  const fakeExecutorPath = path.join(workDir, "fake-subagent.mjs");
  const fakeGeneratorPath = path.join(workDir, "fake-generator.mjs");
  const markerPath = path.join(workDir, "fake-subagent.called");
  const scriptPath = fileURLToPath(new URL("../orchestrate-pptx-modules.mjs", import.meta.url));
  const payload = {
    title: "CLI subagent demo",
    author: "test",
    retry_scope: "slide",
    target_slide_ids: ["s2"],
    slides: [
      {
        slide_id: "s1",
        page_number: 1,
        slide_type: "cover",
        title: "Cover",
        blocks: [
          { block_type: "title", card_id: "title", content: "Cover" },
          { block_type: "subtitle", card_id: "sub", content: "Intro" },
        ],
      },
      {
        slide_id: "s2",
        page_number: 2,
        slide_type: "content",
        title: "Body",
        blocks: [
          { block_type: "title", card_id: "title", content: "Body" },
          { block_type: "body", card_id: "body", content: "Point A;Point B" },
        ],
      },
    ],
  };

  try {
    writeFileSync(inputPath, JSON.stringify(payload), "utf-8");
    writeFileSync(
      fakeExecutorPath,
      `import { readFileSync, writeFileSync } from "node:fs";
const raw = readFileSync(0, "utf-8");
const payload = JSON.parse(raw || "{}");
const title = String(payload?.slide_data?.title || "Slide");
writeFileSync(${JSON.stringify(markerPath)}, "called", "utf-8");
process.stdout.write(JSON.stringify({
  ok: true,
  slide_patch: { title: title + " (subagent)", layout_grid: "split_2" },
  load_skills: ["pptx"],
  notes: "patched-by-fake-executor"
}));`,
      "utf-8",
    );
    writeFileSync(
      fakeGeneratorPath,
      `import { readFileSync, writeFileSync } from "node:fs";
const argv = process.argv.slice(2);
const pick = (name) => {
  const idx = argv.indexOf(name);
  return idx >= 0 ? String(argv[idx + 1] || "") : "";
};
const inputPath = pick("--input");
const outputPath = pick("--output");
const renderOutputPath = pick("--render-output");
const targetSlideIds = (pick("--target-slide-ids") || "").split(",").map((v) => v.trim()).filter(Boolean);
const payload = JSON.parse(readFileSync(inputPath, "utf-8"));
const slides = Array.isArray(payload?.slides) ? payload.slides : [];
const effective = targetSlideIds.length > 0
  ? slides.filter((s) => targetSlideIds.includes(String(s?.slide_id || "")))
  : slides;
writeFileSync(outputPath, "pptx-stub", "utf-8");
writeFileSync(renderOutputPath, JSON.stringify({
  mode: "minimax_presentation",
  slides: effective.map((s, i) => ({
    slide_id: String(s?.slide_id || \`s-\${i + 1}\`),
    page_number: i + 1,
    render_path: String(s?.render_path || "pptxgenjs"),
    slide_type: String(s?.slide_type || "content")
  })),
  official_output: {
    slides: effective.map((s, i) => ({
      slide_id: String(s?.slide_id || \`s-\${i + 1}\`),
      title: String(s?.title || "Slide"),
      slide_type: String(s?.slide_type || "content"),
      layout_grid: String(s?.layout_grid || "split_2")
    }))
  }
}), "utf-8");
process.stdout.write(JSON.stringify({ success: true }));`,
      "utf-8",
    );

    const stdout = execFileSync("node", [
      scriptPath,
      "--input",
      inputPath,
      "--modules-dir",
      modulesDir,
      "--render-each",
      "--target-slide-ids",
      "s2",
      "--subagent-exec",
      "--generator-script",
      fakeGeneratorPath,
    ], {
      encoding: "utf-8",
      env: {
        ...process.env,
        PPT_SUBAGENT_EXECUTOR_BIN: "node",
        PPT_SUBAGENT_EXECUTOR_ARGS: JSON.stringify([fakeExecutorPath]),
      },
    });
    const result = JSON.parse(String(stdout || "").trim());
    assert.equal(result.success, true);
    assert.equal(result.render_each?.ok, true);
    assert.equal(existsSync(markerPath), true);
    assert.equal(Array.isArray(result.render_each?.subagent_runs), true);
    assert.equal(Boolean(result.render_each?.subagent_runs?.[0]?.enabled), true);
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});

test("orchestrate-pptx-modules e2e merges retried slide patch then compiles full deck", () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "orchestrate-modules-e2e-"));
  const inputPath = path.join(workDir, "payload.json");
  const modulesDir = path.join(workDir, "slides");
  const outputPath = path.join(workDir, "deck.pptx");
  const renderOutputPath = path.join(workDir, "deck.render.json");
  const fakeGeneratorPath = path.join(workDir, "fake-generator.mjs");
  const scriptPath = fileURLToPath(new URL("../orchestrate-pptx-modules.mjs", import.meta.url));

  const payload = {
    title: "CLI e2e retry demo",
    author: "test",
    retry_scope: "slide",
    target_slide_ids: ["s2"],
    slides: [
      {
        slide_id: "s1",
        page_number: 1,
        slide_type: "cover",
        title: "Cover",
        blocks: [
          { block_type: "title", card_id: "title", content: "Cover" },
          { block_type: "subtitle", card_id: "sub", content: "Intro" },
        ],
      },
      {
        slide_id: "s2",
        page_number: 2,
        slide_type: "content",
        title: "Body",
        blocks: [
          { block_type: "title", card_id: "title", content: "Body" },
          { block_type: "body", card_id: "body", content: "Point A;Point B" },
        ],
      },
    ],
  };

  try {
    writeFileSync(inputPath, JSON.stringify(payload), "utf-8");
    writeFileSync(
      fakeGeneratorPath,
      `import { readFileSync, writeFileSync } from "node:fs";
const argv = process.argv.slice(2);
const pick = (name) => {
  const idx = argv.indexOf(name);
  return idx >= 0 ? String(argv[idx + 1] || "") : "";
};
const inputPath = pick("--input");
const outputPath = pick("--output");
const renderOutputPath = pick("--render-output");
const targetSlideIds = (pick("--target-slide-ids") || "").split(",").map((v) => v.trim()).filter(Boolean);
const payload = JSON.parse(readFileSync(inputPath, "utf-8"));
const slides = Array.isArray(payload?.slides) ? payload.slides : [];
const effective = targetSlideIds.length > 0
  ? slides.filter((s) => targetSlideIds.includes(String(s?.slide_id || "")))
  : slides;
const patched = effective.map((s, i) => ({
  slide_id: String(s?.slide_id || \`s-\${i + 1}\`),
  title: String(s?.title || "Slide") + (targetSlideIds.length > 0 ? " [retry]" : ""),
  slide_type: String(s?.slide_type || "content"),
  layout_grid: String(s?.layout_grid || "split_2")
}));
writeFileSync(outputPath, "pptx-stub", "utf-8");
writeFileSync(renderOutputPath, JSON.stringify({
  mode: "minimax_presentation",
  retry_scope: String(payload?.retry_scope || ""),
  slides: effective.map((s, i) => ({
    slide_id: String(s?.slide_id || \`s-\${i + 1}\`),
    title: String(s?.title || "Slide"),
    page_number: i + 1,
    render_path: String(s?.render_path || "pptxgenjs"),
    slide_type: String(s?.slide_type || "content")
  })),
  official_output: {
    slides: patched
  }
}), "utf-8");
process.stdout.write(JSON.stringify({ success: true }));`,
      "utf-8",
    );

    const stdout = execFileSync("node", [
      scriptPath,
      "--input",
      inputPath,
      "--modules-dir",
      modulesDir,
      "--render-each",
      "--target-slide-ids",
      "s2",
      "--compile",
      "--output",
      outputPath,
      "--render-output",
      renderOutputPath,
      "--generator-script",
      fakeGeneratorPath,
    ], { encoding: "utf-8" });

    const result = JSON.parse(String(stdout || "").trim());
    assert.equal(result.success, true);
    assert.equal(result.render_each?.ok, true);
    assert.equal(result.compile?.ok, true);

    const renderSpec = JSON.parse(readFileSync(renderOutputPath, "utf-8"));
    assert.equal(renderSpec.retry_scope, "deck");
    assert.equal(Array.isArray(renderSpec.slides), true);
    assert.equal(renderSpec.slides.length, 2);
    const byId = new Map(renderSpec.slides.map((item) => [String(item?.slide_id || ""), item]));
    assert.equal(String(byId.get("s1")?.title || ""), "Cover");
    assert.equal(String(byId.get("s2")?.title || ""), "Body");
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});
