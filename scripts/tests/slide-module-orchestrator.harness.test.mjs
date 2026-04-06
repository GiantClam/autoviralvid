import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import {
  compileSlideModules,
  loadSlideModules,
  renderSlideModulesInParallel,
  writeSlideModules,
} from "../minimax/slide-module-orchestrator.mjs";

function buildPayload() {
  return {
    title: "Module Orchestration Demo",
    author: "test",
    theme: { style: "soft", palette: "pure_tech_blue" },
    slides: [
      {
        slide_id: "s-cover",
        page_number: 1,
        slide_type: "cover",
        layout_grid: "hero_1",
        title: "Cover",
        blocks: [
          { block_type: "title", card_id: "title", content: "Cover" },
          { block_type: "subtitle", card_id: "subtitle", content: "Opening" },
        ],
      },
      {
        slide_id: "s-content",
        page_number: 2,
        slide_type: "content",
        layout_grid: "split_2",
        title: "Content",
        blocks: [
          { block_type: "title", card_id: "title", content: "Content" },
          { block_type: "body", card_id: "left", content: "Point A;Point B" },
        ],
      },
      {
        slide_id: "s-summary",
        page_number: 3,
        slide_type: "summary",
        layout_grid: "hero_1",
        title: "Summary",
        blocks: [
          { block_type: "title", card_id: "title", content: "Summary" },
          { block_type: "list", card_id: "list", content: "Done" },
        ],
      },
    ],
  };
}

function buildPayloadWithToc() {
  const base = buildPayload();
  return {
    ...base,
    slides: [
      base.slides[0],
      {
        slide_id: "s-toc",
        page_number: 2,
        slide_type: "toc",
        layout_grid: "hero_1",
        title: "Agenda",
        blocks: [
          { block_type: "title", card_id: "title", content: "Agenda" },
          { block_type: "list", card_id: "list", content: "A;B;C" },
        ],
      },
      base.slides[2],
    ],
  };
}

test("slide module orchestrator writes typed slide modules and manifest", async () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "slide-module-harness-"));
  const modulesDir = path.join(workDir, "slides");
  try {
    const { manifest, manifest_path } = writeSlideModules(buildPayload(), modulesDir);
    assert.ok(existsSync(manifest_path));
    assert.equal(Array.isArray(manifest.modules), true);
    assert.equal(manifest.modules.length, 3);
    assert.equal(manifest.modules[0].agent_type, "cover-page-generator");
    assert.equal(manifest.modules[1].agent_type, "content-page-generator");
    assert.equal(manifest.modules[2].agent_type, "summary-page-generator");
    assert.equal(Array.isArray(manifest.modules[0].load_skills), true);
    assert.equal(manifest.modules[0].load_skills.includes("slide-making-skill"), true);
    assert.equal(manifest.modules[1].load_skills.includes("design-style-skill"), true);
    assert.ok(existsSync(manifest.modules[0].module_path));

    const loaded = await loadSlideModules(manifest);
    assert.equal(loaded.modules.length, 3);
    assert.equal(loaded.modules[1].slide_data.slide_id, "s-content");
    assert.equal(loaded.modules[2].slide_config.slide_type, "summary");
    assert.equal(Array.isArray(loaded.modules[2].load_skills), true);
    assert.equal(loaded.modules[2].load_skills.includes("color-font-skill"), true);
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});

test("slide module orchestrator maps toc to table-of-contents agent with orchestra skill", async () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "slide-module-toc-"));
  const modulesDir = path.join(workDir, "slides");
  try {
    const { manifest } = writeSlideModules(buildPayloadWithToc(), modulesDir);
    assert.equal(manifest.modules[1].slide_type, "toc");
    assert.equal(manifest.modules[1].agent_type, "table-of-contents-generator");
    assert.equal(Array.isArray(manifest.modules[1].load_skills), true);
    assert.equal(manifest.modules[1].load_skills.includes("ppt-orchestra-skill"), true);
    assert.equal(manifest.modules[1].load_skills.includes("color-font-skill"), true);
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});

test("slide module orchestrator backfills missing slide structure and rotates content layouts", async () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "slide-module-fallback-"));
  const modulesDir = path.join(workDir, "slides");
  try {
    const payload = {
      title: "Fallback Layout Demo",
      slides: [
        { slide_id: "s1", title: "封面" },
        { slide_id: "s2", title: "内容一" },
        { slide_id: "s3", title: "内容二" },
        { slide_id: "s4", title: "内容三" },
        { slide_id: "s5", title: "内容四" },
        { slide_id: "s6", title: "内容五" },
        { slide_id: "s7", title: "总结" },
      ],
    };
    const { manifest } = writeSlideModules(payload, modulesDir);
    const loaded = await loadSlideModules(manifest);
    const modules = Array.isArray(loaded.modules) ? loaded.modules : [];
    const content = modules.filter((row) => String(row.slide_type || "").toLowerCase() === "content");
    assert.equal(content.length, 5);
    const layoutSet = new Set(content.map((row) => String(row.layout_grid || "").toLowerCase()).filter(Boolean));
    assert.equal(layoutSet.size >= 2, true, "content layouts should not collapse into a single fallback");
    assert.equal(String(modules[0].layout_grid || "").toLowerCase(), "hero_1");
    assert.equal(String(modules[modules.length - 1].layout_grid || "").toLowerCase(), "hero_1");
    for (const row of content) {
      assert.equal(String(row.slide_data?.slide_type || "").toLowerCase(), "content");
      assert.equal(Boolean(String(row.slide_data?.layout_grid || "").trim()), true);
    }
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});

test("compileSlideModules assembles payload and invokes generator runner once", async () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "slide-module-compile-"));
  const modulesDir = path.join(workDir, "slides");
  const calls = [];
  try {
    const retryPayload = {
      ...buildPayload(),
      retry_scope: "slide",
      target_slide_ids: ["s-content"],
    };
    const { manifest } = writeSlideModules(retryPayload, modulesDir);
    const outputPath = path.join(workDir, "deck.pptx");
    const renderOutputPath = path.join(workDir, "deck.render.json");
    const result = await compileSlideModules({
      manifest,
      outputPath,
      renderOutputPath,
      generatorScriptPath: "scripts/generate-pptx-minimax.mjs",
      runner: (command, args) => {
        calls.push({ command, args });
        return { ok: true };
      },
    });
    assert.equal(result.ok, true);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].command, "node");
    assert.equal(calls[0].args.includes("--input"), true);
    assert.equal(calls[0].args.includes("--output"), true);

    const inputArgIndex = calls[0].args.indexOf("--input");
    assert.ok(inputArgIndex >= 0);
    const inputJsonPath = calls[0].args[inputArgIndex + 1];
    const compileInput = JSON.parse(readFileSync(inputJsonPath, "utf-8"));
    assert.equal(Array.isArray(compileInput.slides), true);
    assert.equal(compileInput.slides.length, 3);
    assert.equal(compileInput.slides[0].slide_id, "s-cover");
    assert.equal(compileInput.slides[2].slide_id, "s-summary");
    assert.equal(compileInput.retry_scope, "deck");
    assert.deepEqual(compileInput.target_slide_ids, []);
    assert.deepEqual(compileInput.target_block_ids, []);
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});

test("compileSlideModules repairs contract deficits before invoking generator", async () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "slide-module-compile-repair-"));
  const modulesDir = path.join(workDir, "slides");
  const calls = [];
  try {
    const payload = {
      ...buildPayload(),
      slides: [
        {
          slide_id: "s-cover",
          page_number: 1,
          slide_type: "cover",
          layout_grid: "hero_1",
          title: "Cover",
          blocks: [
            { block_type: "title", card_id: "title", content: "Cover" },
            { block_type: "subtitle", card_id: "subtitle", content: "Opening" },
          ],
        },
        {
          slide_id: "s-content",
          page_number: 2,
          slide_type: "content",
          layout_grid: "grid_3",
          title: "Market",
          template_family: "dashboard_dark",
          contract_profile: "chart_or_kpi_required",
          blocks: [
            { block_type: "title", card_id: "title", content: "Market" },
            { block_type: "body", card_id: "left", content: "Point A" },
            { block_type: "body", card_id: "mid", content: "Point B" },
            { block_type: "image", card_id: "right", content: { title: "Visual" } },
          ],
        },
        {
          slide_id: "s-summary",
          page_number: 3,
          slide_type: "summary",
          layout_grid: "hero_1",
          title: "Summary",
          blocks: [
            { block_type: "title", card_id: "title", content: "Summary" },
            { block_type: "list", card_id: "list", content: "Done" },
          ],
        },
      ],
    };
    const { manifest } = writeSlideModules(payload, modulesDir);
    const result = await compileSlideModules({
      manifest,
      outputPath: path.join(workDir, "deck.pptx"),
      renderOutputPath: path.join(workDir, "deck.render.json"),
      generatorScriptPath: "scripts/generate-pptx-minimax.mjs",
      runner: (command, args) => {
        calls.push({ command, args });
        return { ok: true };
      },
    });
    assert.equal(result.ok, true);
    assert.equal(calls.length, 1);
    assert.equal(Boolean(result.contract_repair?.attempted), true);

    const inputArgIndex = calls[0].args.indexOf("--input");
    const inputJsonPath = calls[0].args[inputArgIndex + 1];
    const compileInput = JSON.parse(readFileSync(inputJsonPath, "utf-8"));
    const content = compileInput.slides.find((slide) => slide.slide_id === "s-content");
    assert.ok(content);
    const blockTypes = (content.blocks || []).map((block) => String(block?.block_type || "").toLowerCase());
    assert.equal(blockTypes.includes("chart") || blockTypes.includes("kpi"), true);
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});

test("renderSlideModulesInParallel honors maxParallel and slide targeting args", async () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "slide-module-render-"));
  const modulesDir = path.join(workDir, "slides");
  let active = 0;
  let maxObserved = 0;
  const calls = [];
  try {
    const { manifest } = writeSlideModules(buildPayload(), modulesDir);
    const result = await renderSlideModulesInParallel({
      manifest,
      maxParallel: 2,
      generatorScriptPath: "scripts/generate-pptx-minimax.mjs",
      outputDir: path.join(workDir, "rendered"),
      runner: async (command, args) => {
        active += 1;
        maxObserved = Math.max(maxObserved, active);
        calls.push({ command, args });
        await new Promise((resolve) => setTimeout(resolve, 20));
        active -= 1;
        return { ok: true };
      },
    });

    assert.equal(result.ok, true);
    assert.equal(result.slide_results.length, 3);
    assert.equal(calls.length, 3);
    assert.equal(maxObserved <= 2, true);
    for (const call of calls) {
      assert.equal(call.command, "node");
      assert.equal(call.args.includes("--retry-scope"), true);
      const scopeIndex = call.args.indexOf("--retry-scope");
      assert.equal(call.args[scopeIndex + 1], "slide");
      assert.equal(call.args.includes("--target-slide-ids"), true);
    }
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});

test("renderSlideModulesInParallel filters to target slide ids", async () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "slide-module-target-"));
  const modulesDir = path.join(workDir, "slides");
  const calls = [];
  try {
    const { manifest } = writeSlideModules(buildPayload(), modulesDir);
    const result = await renderSlideModulesInParallel({
      manifest,
      maxParallel: 3,
      targetSlideIds: ["s-content"],
      generatorScriptPath: "scripts/generate-pptx-minimax.mjs",
      outputDir: path.join(workDir, "rendered"),
      runner: async (command, args) => {
        calls.push({ command, args });
        return { ok: true };
      },
    });
    assert.equal(result.ok, true);
    assert.equal(result.slide_results.length, 1);
    assert.equal(result.slide_results[0].slide_id, "s-content");
    assert.equal(calls.length, 1);
    assert.equal(result.targeted_slide_ids.includes("s-content"), true);
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});

test("renderSlideModulesInParallel repairs full-deck contract before per-slide render", async () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "slide-module-render-repair-"));
  const modulesDir = path.join(workDir, "slides");
  try {
    const payload = {
      ...buildPayload(),
      slides: [
        {
          slide_id: "s-cover",
          page_number: 1,
          slide_type: "cover",
          layout_grid: "hero_1",
          title: "Cover",
          blocks: [
            { block_type: "title", card_id: "title", content: "Cover" },
            { block_type: "subtitle", card_id: "subtitle", content: "Opening" },
          ],
        },
        {
          slide_id: "s-content",
          page_number: 2,
          slide_type: "content",
          layout_grid: "split_2",
          title: "Target Content",
          blocks: [
            { block_type: "title", card_id: "title", content: "Target Content" },
            { block_type: "body", card_id: "left", content: "Point A" },
          ],
        },
        {
          slide_id: "s-bad",
          page_number: 3,
          slide_type: "content",
          layout_grid: "grid_3",
          title: "Needs Visual Contract",
          template_family: "dashboard_dark",
          contract_profile: "chart_or_kpi_required",
          blocks: [
            { block_type: "title", card_id: "title", content: "Needs Visual Contract" },
            { block_type: "body", card_id: "left", content: "Point A" },
            { block_type: "body", card_id: "mid", content: "Point B" },
            { block_type: "image", card_id: "right", content: { title: "Visual" } },
          ],
        },
      ],
    };
    const { manifest } = writeSlideModules(payload, modulesDir);
    const result = await renderSlideModulesInParallel({
      manifest,
      maxParallel: 1,
      targetSlideIds: ["s-content"],
      generatorScriptPath: "scripts/generate-pptx-minimax.mjs",
      outputDir: path.join(workDir, "rendered"),
      runner: async (_command, args) => {
        const inputPath = args[args.indexOf("--input") + 1];
        const renderOutputPath = args[args.indexOf("--render-output") + 1];
        const payloadForRender = JSON.parse(readFileSync(inputPath, "utf-8"));
        const badSlide = payloadForRender.slides.find((slide) => slide.slide_id === "s-bad");
        assert.ok(badSlide);
        const blockTypes = (badSlide.blocks || []).map((block) =>
          String(block?.block_type || "").toLowerCase(),
        );
        assert.equal(blockTypes.includes("chart") || blockTypes.includes("kpi"), true);
        writeFileSync(
          renderOutputPath,
          JSON.stringify({
            slides: [{ slide_id: "s-content", render_path: "pptxgenjs" }],
            official_output: { slides: [{ slide_id: "s-content", title: "Target Content" }] },
          }),
          "utf-8",
        );
        return { ok: true };
      },
    });
    assert.equal(result.ok, true);
    assert.equal(result.slide_results.length, 1);
    assert.equal(Boolean(result.slide_results[0]?.contract_repair?.attempted), true);
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});

test("renderSlideModulesInParallel deep-merges render output into modules for subsequent compile", async () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "slide-module-merge-"));
  const modulesDir = path.join(workDir, "slides");
  const compileCalls = [];
  try {
    const { manifest } = writeSlideModules(buildPayload(), modulesDir);
    const renderResult = await renderSlideModulesInParallel({
      manifest,
      maxParallel: 2,
      targetSlideIds: ["s-content"],
      generatorScriptPath: "scripts/generate-pptx-minimax.mjs",
      outputDir: path.join(workDir, "rendered"),
      runner: async (_command, args) => {
        const renderOutputPath = args[args.indexOf("--render-output") + 1];
        const targetSlideId = args[args.indexOf("--target-slide-ids") + 1];
        writeFileSync(
          renderOutputPath,
          JSON.stringify({
            retry_scope: "slide",
            slides: [
              {
                slide_id: targetSlideId,
                page_number: 2,
                slide_type: "grid_3",
                render_path: "svg",
                svg_render_mode: "custgeom",
                template_family: "dashboard_dark",
              },
            ],
            official_output: {
              slides: [
                {
                  slide_id: targetSlideId,
                  title: "Merged Content Title",
                  slide_type: "content",
                  elements: [
                    {
                      block_id: `${targetSlideId}-b1`,
                      type: "text",
                      content: "Merged evidence line",
                    },
                  ],
                },
              ],
            },
          }),
          "utf-8",
        );
        return { ok: true };
      },
    });

    assert.equal(renderResult.ok, true);
    assert.equal(renderResult.merged_slide_count, 1);
    assert.deepEqual(renderResult.merged_slide_ids, ["s-content"]);

    const loaded = await loadSlideModules(manifest);
    const contentSlide = loaded.modules.find((row) => row.slide_id === "s-content");
    assert.ok(contentSlide);
    assert.equal(contentSlide.slide_data.title, "Content");
    assert.equal(contentSlide.slide_data.render_path, "svg");
    assert.equal(contentSlide.slide_data.__svg_render_mode, "custgeom");
    assert.equal(Array.isArray(contentSlide.slide_data.elements), false);

    await compileSlideModules({
      manifest,
      outputPath: path.join(workDir, "deck.pptx"),
      renderOutputPath: path.join(workDir, "deck.render.json"),
      generatorScriptPath: "scripts/generate-pptx-minimax.mjs",
      runner: (command, args) => {
        compileCalls.push({ command, args });
        return { ok: true };
      },
    });
    assert.equal(compileCalls.length, 1);
    const compileInputPath = compileCalls[0].args[compileCalls[0].args.indexOf("--input") + 1];
    const compileInput = JSON.parse(readFileSync(compileInputPath, "utf-8"));
    const compileContentSlide = compileInput.slides.find((slide) => slide.slide_id === "s-content");
    assert.ok(compileContentSlide);
    assert.equal(compileContentSlide.title, "Content");
    assert.equal(compileContentSlide.render_path, "svg");
    assert.equal(compileContentSlide.__svg_render_mode, "custgeom");
    assert.equal(Array.isArray(compileContentSlide.elements), false);
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});

test("renderSlideModulesInParallel ignores generic title/template overwrite from per-slide patch", async () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "slide-module-merge-guard-"));
  const modulesDir = path.join(workDir, "slides");
  try {
    const payload = {
      ...buildPayload(),
      slides: [
        {
          slide_id: "s-cover",
          page_number: 1,
          slide_type: "cover",
          layout_grid: "hero_1",
          title: "Cover",
          blocks: [
            { block_type: "title", card_id: "title", content: "Cover" },
            { block_type: "subtitle", card_id: "subtitle", content: "Opening" },
          ],
        },
        {
          slide_id: "s-content",
          page_number: 2,
          slide_type: "content",
          layout_grid: "grid_4",
          template_family: "bento_2x2_dark",
          title: "真实标题",
          blocks: [
            { block_type: "title", card_id: "title", content: "真实标题" },
            { block_type: "body", card_id: "body", content: "Point A" },
          ],
        },
      ],
    };
    const { manifest } = writeSlideModules(payload, modulesDir);
    const renderResult = await renderSlideModulesInParallel({
      manifest,
      maxParallel: 1,
      targetSlideIds: ["s-content"],
      generatorScriptPath: "scripts/generate-pptx-minimax.mjs",
      outputDir: path.join(workDir, "rendered"),
      runner: async (_command, args) => {
        const targetSlideId = args[args.indexOf("--target-slide-ids") + 1];
        const renderOutputPath = args[args.indexOf("--render-output") + 1];
        writeFileSync(
          renderOutputPath,
          JSON.stringify({
            slides: [
              {
                slide_id: targetSlideId,
                slide_type: "content",
                template_family: "dashboard_dark",
              },
            ],
            official_output: {
              slides: [
                {
                  slide_id: targetSlideId,
                  title: "Slide 1",
                  slide_type: "content",
                },
              ],
            },
          }),
          "utf-8",
        );
        return { ok: true };
      },
    });

    assert.equal(renderResult.ok, true);
    const loaded = await loadSlideModules(manifest);
    const contentSlide = loaded.modules.find((row) => row.slide_id === "s-content");
    assert.ok(contentSlide);
    assert.equal(contentSlide.slide_data.title, "真实标题");
    assert.equal(contentSlide.slide_data.template_family, "bento_2x2_dark");
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});

test("renderSlideModulesInParallel can apply subagent patch before per-slide render", async () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "slide-module-subagent-"));
  const modulesDir = path.join(workDir, "slides");
  const prompts = [];
  try {
    const { manifest } = writeSlideModules(buildPayload(), modulesDir);
    const result = await renderSlideModulesInParallel({
      manifest,
      maxParallel: 1,
      targetSlideIds: ["s-content"],
      enableSubagentExec: true,
      subagentExecutor: async (taskPayload) => {
        prompts.push(String(taskPayload?.prompt || ""));
        return {
          slide_patch: {
            title: "Subagent Revised Title",
            render_path: "svg",
          },
          load_skills: ["ppt-orchestra-skill"],
          notes: "patched in harness",
        };
      },
      generatorScriptPath: "scripts/generate-pptx-minimax.mjs",
      outputDir: path.join(workDir, "rendered"),
      runner: async (_command, args) => {
        const inputPath = args[args.indexOf("--input") + 1];
        const targetSlideId = args[args.indexOf("--target-slide-ids") + 1];
        const renderOutputPath = args[args.indexOf("--render-output") + 1];
        const payload = JSON.parse(readFileSync(inputPath, "utf-8"));
        const targetSlide = payload.slides.find((slide) => slide.slide_id === targetSlideId);
        assert.ok(targetSlide);
        assert.equal(targetSlide.title, "Subagent Revised Title");
        assert.equal(targetSlide.render_path, "svg");
        writeFileSync(
          renderOutputPath,
          JSON.stringify({
            slides: [{ slide_id: targetSlideId, render_path: "svg", svg_render_mode: "custgeom" }],
            official_output: { slides: [{ slide_id: targetSlideId, title: "Subagent Revised Title" }] },
          }),
          "utf-8",
        );
        return { ok: true };
      },
    });

    assert.equal(result.ok, true);
    assert.equal(prompts.length, 1);
    assert.match(prompts[0], /Content rules:/);
    assert.match(prompts[0], /Image rules:/);
    assert.equal(Array.isArray(result.subagent_runs), true);
    assert.equal(Boolean(result.subagent_runs[0]?.applied), true);
    const loaded = await loadSlideModules(manifest);
    const contentSlide = loaded.modules.find((row) => row.slide_id === "s-content");
    assert.ok(contentSlide);
    assert.equal(contentSlide.slide_data.title, "Subagent Revised Title");
    assert.equal(contentSlide.slide_data.render_path, "svg");
    assert.equal(contentSlide.load_skills.includes("ppt-orchestra-skill"), true);
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});

test("renderSlideModulesInParallel preserves visual identity fields when template_lock is enabled", async () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "slide-module-subagent-lock-"));
  const modulesDir = path.join(workDir, "slides");
  try {
    const payload = {
      ...buildPayload(),
      slides: [
        {
          slide_id: "s-cover",
          page_number: 1,
          slide_type: "cover",
          layout_grid: "hero_1",
          title: "Cover",
          blocks: [
            { block_type: "title", card_id: "title", content: "Cover" },
            { block_type: "subtitle", card_id: "subtitle", content: "Opening" },
          ],
        },
        {
          slide_id: "s-content",
          page_number: 2,
          slide_type: "content",
          layout_grid: "split_2",
          title: "Locked Slide",
          template_lock: true,
          template_family: "bento_2x2_dark",
          template_id: "bento_2x2_dark",
          style_variant: "soft",
          palette_key: "pure_tech_blue",
          skill_profile: "bento-general",
          blocks: [
            { block_type: "title", card_id: "title", content: "Locked Slide" },
            { block_type: "body", card_id: "body", content: "Point A" },
          ],
        },
        {
          slide_id: "s-summary",
          page_number: 3,
          slide_type: "summary",
          layout_grid: "hero_1",
          title: "Summary",
          blocks: [
            { block_type: "title", card_id: "title", content: "Summary" },
            { block_type: "list", card_id: "list", content: "Done" },
          ],
        },
      ],
    };

    const { manifest } = writeSlideModules(payload, modulesDir);
    const result = await renderSlideModulesInParallel({
      manifest,
      maxParallel: 1,
      targetSlideIds: ["s-content"],
      enableSubagentExec: true,
      subagentExecutor: async () => ({
        slide_patch: {
          title: "Patched Title",
          template_family: "dashboard_dark",
          template_id: "dashboard_dark",
          style_variant: "sharp",
          palette_key: "business_authority",
          skill_profile: "cover-default",
        },
      }),
      generatorScriptPath: "scripts/generate-pptx-minimax.mjs",
      outputDir: path.join(workDir, "rendered"),
      runner: async (_command, args) => {
        const inputPath = args[args.indexOf("--input") + 1];
        const targetSlideId = args[args.indexOf("--target-slide-ids") + 1];
        const renderOutputPath = args[args.indexOf("--render-output") + 1];
        const compileInput = JSON.parse(readFileSync(inputPath, "utf-8"));
        const targetSlide = compileInput.slides.find((slide) => slide.slide_id === targetSlideId);
        assert.ok(targetSlide);
        assert.equal(targetSlide.title, "Patched Title");
        assert.equal(targetSlide.template_family, "bento_2x2_dark");
        assert.equal(targetSlide.template_id, "bento_2x2_dark");
        assert.equal(targetSlide.style_variant, "soft");
        assert.equal(targetSlide.palette_key, "pure_tech_blue");
        assert.equal(targetSlide.skill_profile, "bento-general");
        writeFileSync(
          renderOutputPath,
          JSON.stringify({
            slides: [{ slide_id: targetSlideId, render_path: "pptxgenjs" }],
            official_output: { slides: [{ slide_id: targetSlideId, title: "Patched Title" }] },
          }),
          "utf-8",
        );
        return { ok: true };
      },
    });

    assert.equal(result.ok, true);
    const loaded = await loadSlideModules(manifest);
    const contentSlide = loaded.modules.find((row) => row.slide_id === "s-content");
    assert.ok(contentSlide);
    assert.equal(contentSlide.slide_data.title, "Patched Title");
    assert.equal(contentSlide.slide_data.template_family, "bento_2x2_dark");
    assert.equal(contentSlide.slide_data.template_id, "bento_2x2_dark");
    assert.equal(contentSlide.slide_data.style_variant, "soft");
    assert.equal(contentSlide.slide_data.palette_key, "pure_tech_blue");
    assert.equal(contentSlide.slide_data.skill_profile, "bento-general");
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});

test("renderSlideModulesInParallel injects scene-specific rulebook guidance into subagent prompt", async () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "slide-module-scene-guidance-"));
  const modulesDir = path.join(workDir, "slides");
  try {
    const payload = buildPayload();
    payload.slides[1].quality_profile = "training_deck";
    payload.slides[1].title = "知识点讲解";
    const { manifest } = writeSlideModules(payload, modulesDir);
    const prompts = [];
    const result = await renderSlideModulesInParallel({
      manifest,
      maxParallel: 1,
      targetSlideIds: ["s-content"],
      enableSubagentExec: true,
      subagentExecutor: async (taskPayload) => {
        prompts.push(String(taskPayload?.prompt || ""));
        return { slide_patch: { title: "知识点讲解" } };
      },
      generatorScriptPath: "scripts/generate-pptx-minimax.mjs",
      outputDir: path.join(workDir, "rendered"),
      runner: async (_command, args) => {
        const renderOutputPath = args[args.indexOf("--render-output") + 1];
        writeFileSync(
          renderOutputPath,
          JSON.stringify({
            slides: [{ slide_id: "s-content", render_path: "pptxgenjs" }],
            official_output: { slides: [{ slide_id: "s-content", title: "知识点讲解" }] },
          }),
          "utf-8",
        );
        return { ok: true };
      },
    });
    assert.equal(result.ok, true);
    assert.equal(prompts.length, 1);
    assert.match(prompts[0], /Scene rules:/);
    assert.match(prompts[0], /课程讲义/);
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});

test("renderSlideModulesInParallel ignores generic subagent title downgrade", async () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "slide-module-subagent-generic-"));
  const modulesDir = path.join(workDir, "slides");
  try {
    const { manifest } = writeSlideModules(buildPayload(), modulesDir);
    const result = await renderSlideModulesInParallel({
      manifest,
      maxParallel: 1,
      targetSlideIds: ["s-content"],
      enableSubagentExec: true,
      subagentExecutor: async () => ({
        slide_patch: {
          title: "Slide 9",
          render_path: "svg",
        },
      }),
      generatorScriptPath: "scripts/generate-pptx-minimax.mjs",
      outputDir: path.join(workDir, "rendered"),
      runner: async (_command, args) => {
        const inputPath = args[args.indexOf("--input") + 1];
        const targetSlideId = args[args.indexOf("--target-slide-ids") + 1];
        const renderOutputPath = args[args.indexOf("--render-output") + 1];
        const payload = JSON.parse(readFileSync(inputPath, "utf-8"));
        const targetSlide = payload.slides.find((slide) => slide.slide_id === targetSlideId);
        assert.ok(targetSlide);
        assert.equal(targetSlide.title, "Content");
        assert.equal(targetSlide.render_path, "svg");
        writeFileSync(
          renderOutputPath,
          JSON.stringify({
            slides: [{ slide_id: targetSlideId, render_path: "svg", svg_render_mode: "custgeom" }],
            official_output: { slides: [{ slide_id: targetSlideId, title: "Slide 9" }] },
          }),
          "utf-8",
        );
        return { ok: true };
      },
    });

    assert.equal(result.ok, true);
    const loaded = await loadSlideModules(manifest);
    const contentSlide = loaded.modules.find((row) => row.slide_id === "s-content");
    assert.ok(contentSlide);
    assert.equal(contentSlide.slide_data.title, "Content");
    assert.equal(contentSlide.slide_data.render_path, "svg");
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});
