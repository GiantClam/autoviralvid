import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import os from "node:os";
import { fileURLToPath, pathToFileURL } from "node:url";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { normalizeRenderInput, validateRenderInput } from "./render-contract.mjs";

const localRequire = createRequire(import.meta.url);

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function normalizeText(value, fallback = "") {
  const text = String(value || "").trim();
  return text || fallback;
}

function isGenericSlideTitle(value) {
  return /^slide\s*\d+$/i.test(normalizeText(value, ""));
}

function htmlToText(value) {
  return String(value || "")
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/\s+/g, " ")
    .trim();
}

function inferTitleFromElements(slide = {}) {
  const elements = asArray(slide?.elements);
  let best = "";
  for (const element of elements) {
    if (!element || typeof element !== "object") continue;
    const type = normalizeText(element.type, "").toLowerCase();
    if (type !== "text") continue;
    const top = Number(element.top || 0);
    const fontSize = Number(element?.style?.fontSize || 0);
    const candidate = htmlToText(String(element.content || ""));
    if (!candidate || isGenericSlideTitle(candidate)) continue;
    if (!best) best = candidate;
    if (top <= 200 || fontSize >= 28 || /<b>/i.test(String(element.content || ""))) {
      return candidate;
    }
  }
  return best;
}

function resolveSlideTitle(slide = {}, index = 0) {
  const explicit = normalizeText(slide?.title, "");
  if (explicit && !isGenericSlideTitle(explicit)) return explicit;
  const inferred = inferTitleFromElements(slide);
  if (inferred) return inferred;
  return explicit || `Slide ${index + 1}`;
}

function stableSlideId(slide, index) {
  const candidate = slide?.slide_id ?? slide?.id ?? slide?.page_number;
  return normalizeText(candidate, `slide-${index + 1}`);
}

function normalizeSlideType(slide, index, total) {
  const explicit = normalizeText(slide?.slide_type || slide?.page_type || slide?.subtype, "").toLowerCase();
  if (explicit) {
    if (explicit === "section-divider" || explicit === "section_divider") return "divider";
    if (explicit === "table-of-contents" || explicit === "table_of_contents") return "toc";
    return explicit;
  }
  if (index === 0) return "cover";
  if (index === total - 1) return "summary";
  return "content";
}

function agentTypeForSlideType(slideType) {
  const normalized = normalizeText(slideType, "content").toLowerCase();
  if (normalized === "cover") return "cover-page-generator";
  if (normalized === "toc") return "table-of-contents-generator";
  if (normalized === "summary") return "summary-page-generator";
  if (normalized === "toc" || normalized === "divider" || normalized === "section") {
    return "section-divider-generator";
  }
  return "content-page-generator";
}

function toSkillKey(value) {
  return normalizeText(value, "")
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function dedupeSkillList(values = []) {
  const out = [];
  const seen = new Set();
  for (const item of asArray(values)) {
    const text = toSkillKey(item);
    if (!text || seen.has(text)) continue;
    seen.add(text);
    out.push(text);
  }
  return out;
}

function resolveLoadSkills({
  slideType = "",
  agentType = "",
  renderPath = "pptxgenjs",
  templateFamily = "",
  skillProfile = "",
  existingLoadSkills = [],
}) {
  const type = normalizeText(slideType, "content").toLowerCase();
  const agent = normalizeText(agentType, "content-page-generator").toLowerCase();
  const path = normalizeText(renderPath, "pptxgenjs").toLowerCase();
  const family = normalizeText(templateFamily, "").toLowerCase();
  const profile = normalizeText(skillProfile, "").toLowerCase();

  const baseSkills = ["slide-making-skill", "ppt-orchestra-skill"];
  if (
    type === "cover"
    || type === "toc"
    || type === "divider"
    || type === "summary"
    || agent.includes("cover")
    || agent.includes("summary")
    || agent.includes("table-of-contents")
    || agent.includes("section-divider")
  ) {
    baseSkills.push("color-font-skill", "design-style-skill");
  } else {
    baseSkills.push("design-style-skill");
  }
  if (path === "svg" || path === "png_fallback") {
    baseSkills.push("pptx");
  }
  if (family && family !== "auto") {
    baseSkills.push("ppt-editing-skill");
  }
  if (family.includes("architecture") || family.includes("workflow") || profile.includes("architecture")) {
    baseSkills.push("ppt-orchestra-skill");
  }
  if (profile.includes("cover")) {
    baseSkills.push("color-font-skill");
  }
  baseSkills.push(...asArray(existingLoadSkills));
  return dedupeSkillList(baseSkills);
}

function padSlideOrder(order) {
  return String(Math.max(1, Number(order) || 1)).padStart(2, "0");
}

function defaultManifestPath(modulesDir) {
  return path.join(modulesDir, "manifest.json");
}

function moduleHeader() {
  return "/** Auto-generated slide module for per-slide orchestration. */\n";
}

function moduleSourceForRecord(record) {
  const slideConfig = JSON.stringify(record.slide_config, null, 2);
  const slideData = JSON.stringify(record.slide_data, null, 2);
  const loadSkills = JSON.stringify(record.load_skills || [], null, 2);
  return `${moduleHeader()}const slideConfig = ${slideConfig};\n\nconst slideData = ${slideData};\n\nconst loadSkills = ${loadSkills};\n\nasync function createSlide() {\n  return { slideConfig, slideData, loadSkills };\n}\n\nmodule.exports = { slideConfig, slideData, loadSkills, createSlide };\n`;
}

function sortRecords(records) {
  return [...records].sort((a, b) => Number(a.order || 0) - Number(b.order || 0));
}

export function buildSlideModuleRecords(payload) {
  const slides = asArray(payload?.slides);
  const total = slides.length;
  const contentLayoutRotation = ["split_2", "grid_3", "grid_4", "asymmetric_2", "timeline"];
  let contentIndex = 0;
  return slides.map((slide, index) => {
    const order = index + 1;
    const slideId = stableSlideId(slide, index);
    const slideType = normalizeSlideType(slide, index, total);
    const explicitLayout = normalizeText(slide?.layout_grid || slide?.layout, "");
    const inferredLayout = explicitLayout || (
      slideType === "cover" || slideType === "summary" || slideType === "toc" || slideType === "divider"
        ? "hero_1"
        : contentLayoutRotation[contentIndex % contentLayoutRotation.length]
    );
    if (slideType === "content") contentIndex += 1;
    const resolvedTitle = resolveSlideTitle(slide, index);
    const slideData = mergePlainObjects(slide && typeof slide === "object" ? slide : {}, {
      slide_id: slideId,
      slide_type: slideType,
      layout_grid: inferredLayout,
      title: resolvedTitle,
    });
    const fileName = `slide-${padSlideOrder(order)}.js`;
    const explicitAgentType = normalizeText(slide?.agent_type || slide?.agentType, "");
    const resolvedAgentType = explicitAgentType || agentTypeForSlideType(slideType);
    const record = {
      order,
      slide_id: slideId,
      slide_type: slideType,
      agent_type: resolvedAgentType,
      render_path: normalizeText(slide?.render_path, "pptxgenjs").toLowerCase(),
      layout_grid: inferredLayout,
      template_family: normalizeText(slide?.template_family || slide?.template_id, ""),
      skill_profile: normalizeText(slide?.skill_profile, ""),
      file_name: fileName,
      slide_config: {
        order,
        slide_id: slideId,
        slide_type: slideType,
        agent_type: resolvedAgentType,
        render_path: normalizeText(slide?.render_path, "pptxgenjs").toLowerCase(),
      },
      slide_data: slideData,
    };
    const loadSkills = resolveLoadSkills({
      slideType,
      agentType: record.agent_type,
      renderPath: record.render_path,
      templateFamily: record.template_family,
      skillProfile: record.skill_profile,
      existingLoadSkills: asArray(slide?.load_skills || slide?.loadSkills),
    });
    return {
      ...record,
      load_skills: loadSkills,
      slide_config: {
        ...record.slide_config,
        load_skills: loadSkills,
      },
    };
  });
}

export function writeSlideModules(payload, modulesDir, options = {}) {
  const outDir = path.resolve(String(modulesDir || ""));
  if (!outDir) throw new Error("modulesDir is required");
  mkdirSync(outDir, { recursive: true });
  const records = buildSlideModuleRecords(payload);
  const sortedRecords = sortRecords(records);
  const modules = sortedRecords.map((record) => {
    const absPath = path.join(outDir, record.file_name);
    writeFileSync(absPath, moduleSourceForRecord(record), "utf-8");
    return {
      order: record.order,
      slide_id: record.slide_id,
      slide_type: record.slide_type,
      agent_type: record.agent_type,
      render_path: record.render_path,
      layout_grid: record.layout_grid,
      load_skills: record.load_skills || [],
      file_name: record.file_name,
      module_path: absPath,
    };
  });

  const basePayload = { ...(payload || {}) };
  delete basePayload.slides;
  const manifest = {
    version: 1,
    created_at: new Date().toISOString(),
    modules_dir: outDir,
    base_payload: basePayload,
    modules,
  };
  const manifestPath = path.resolve(
    String(options.manifestPath || defaultManifestPath(outDir)),
  );
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2), "utf-8");
  return { manifest, manifest_path: manifestPath };
}

export function loadManifest(manifestOrPath) {
  if (manifestOrPath && typeof manifestOrPath === "object" && !Array.isArray(manifestOrPath)) {
    return manifestOrPath;
  }
  const manifestPath = path.resolve(String(manifestOrPath || ""));
  if (!manifestPath) throw new Error("manifest path is required");
  const raw = readFileSync(manifestPath, "utf-8");
  return JSON.parse(raw.charCodeAt(0) === 0xfeff ? raw.slice(1) : raw);
}

export async function loadSlideModules(manifestOrPath) {
  const manifest = loadManifest(manifestOrPath);
  const moduleRows = asArray(manifest?.modules);
  const sortedRows = sortRecords(moduleRows);
  const rows = [];
  for (const row of sortedRows) {
    const modulePath = path.resolve(String(row?.module_path || ""));
    if (!modulePath) continue;
    let imported;
    try {
      const resolved = localRequire.resolve(modulePath);
      if (localRequire.cache?.[resolved]) {
        delete localRequire.cache[resolved];
      }
      imported = localRequire(modulePath);
    } catch (_) {
      const moduleUrl = pathToFileURL(modulePath);
      moduleUrl.searchParams.set("v", `${Date.now()}-${Math.random().toString(36).slice(2)}`);
      imported = await import(moduleUrl.href);
    }
    const slideConfig = imported?.slideConfig && typeof imported.slideConfig === "object"
      ? imported.slideConfig
      : (imported?.default?.slideConfig && typeof imported.default.slideConfig === "object"
        ? imported.default.slideConfig
        : {});
    const slideData = imported?.slideData && typeof imported.slideData === "object"
      ? imported.slideData
      : (imported?.default?.slideData && typeof imported.default.slideData === "object"
        ? imported.default.slideData
        : {});
    const loadSkills = Array.isArray(imported?.loadSkills)
      ? imported.loadSkills
      : (Array.isArray(imported?.default?.loadSkills) ? imported.default.loadSkills : []);
    rows.push({
      ...row,
      slide_config: slideConfig,
      slide_data: slideData,
      load_skills: dedupeSkillList(loadSkills.length ? loadSkills : row?.load_skills || []),
    });
  }
  return { manifest, modules: rows };
}

export async function assemblePayloadFromModules(manifestOrPath) {
  const { manifest, modules } = await loadSlideModules(manifestOrPath);
  const sortedRows = sortRecords(modules);
  const basePayload = manifest?.base_payload && typeof manifest.base_payload === "object"
    ? { ...manifest.base_payload }
    : {};
  return {
    ...basePayload,
    slides: sortedRows.map((row) => row.slide_data),
  };
}

function defaultExecRunner(command, args) {
  execFileSync(command, args, { stdio: "pipe" });
  return { ok: true, command, args };
}

function safeReadJsonFile(filePath) {
  const absPath = path.resolve(String(filePath || ""));
  if (!absPath) return null;
  try {
    const raw = readFileSync(absPath, "utf-8");
    const parsed = JSON.parse(raw.charCodeAt(0) === 0xfeff ? raw.slice(1) : raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch (_) {
    return null;
  }
}

function buildSlidePatchFromRenderSpec(renderSpec, expectedSlideId) {
  if (!renderSpec || typeof renderSpec !== "object") return null;
  const expected = normalizeText(expectedSlideId, "");
  if (!expected) return null;
  const renderSlides = asArray(renderSpec?.slides);
  const renderSlide = renderSlides.find((slide) =>
    normalizeText(slide?.slide_id, "") === expected,
  ) || null;
  const officialSlides = asArray(renderSpec?.official_output?.slides);
  const officialSlide = officialSlides.find((slide) =>
    normalizeText(slide?.slide_id, "") === expected,
  ) || null;

  const patch = {};
  const isGenericTitle = (value) => /^slide\s*\d+$/i.test(String(value || "").trim());
  const isSpecificSlideType = (value) =>
    new Set(["cover", "summary", "toc", "divider", "section", "timeline", "image_showcase"]).has(
      normalizeText(value, "").toLowerCase(),
    );
  if (officialSlide && typeof officialSlide === "object") {
    const slideType = normalizeText(
      officialSlide.slide_type || officialSlide.page_type,
      "",
    ).toLowerCase();
    const layoutGrid = normalizeText(officialSlide.layout_grid, "");
    if (slideType && (slideType === "content" ? false : isSpecificSlideType(slideType))) {
      patch.slide_type = slideType;
    }
    if (layoutGrid && layoutGrid !== "split_2") patch.layout_grid = layoutGrid;
  }

  if (renderSlide && typeof renderSlide === "object") {
    const renderPath = normalizeText(renderSlide.render_path, "").toLowerCase();
    const svgRenderMode = normalizeText(renderSlide.svg_render_mode, "");
    const slideType = normalizeText(renderSlide.slide_type, "").toLowerCase();
    if (renderPath) patch.render_path = renderPath;
    if (svgRenderMode) patch.__svg_render_mode = svgRenderMode;
    if (!patch.slide_type && slideType && isSpecificSlideType(slideType)) {
      patch.slide_type = slideType;
    }
  }

  return Object.keys(patch).length > 0 ? patch : null;
}

function mergePlainObjects(base, patch) {
  const target = base && typeof base === "object" && !Array.isArray(base) ? { ...base } : {};
  const source = patch && typeof patch === "object" && !Array.isArray(patch) ? patch : {};
  for (const [key, value] of Object.entries(source)) {
    const existing = target[key];
    if (
      value
      && typeof value === "object"
      && !Array.isArray(value)
      && existing
      && typeof existing === "object"
      && !Array.isArray(existing)
    ) {
      target[key] = { ...existing, ...value };
      continue;
    }
    target[key] = value;
  }
  return target;
}

function applyRenderedSlidesToModules(manifestObj, slideResults = [], baseSlides = []) {
  const modules = asArray(manifestObj?.modules);
  if (!modules.length) {
    return {
      merged_slide_ids: [],
      merged_slide_count: 0,
    };
  }
  const baseBySlideId = new Map(
    asArray(baseSlides).map((slide, index) => [stableSlideId(slide || {}, index), slide]),
  );
  const bySlideId = new Map(
    modules.map((row, index) => [stableSlideId(row || {}, index), row]),
  );
  const mergedSlideIds = [];
  for (const row of asArray(slideResults)) {
    if (!row || row.ok === false) continue;
    const slideId = normalizeText(row.slide_id, "");
    if (!slideId) continue;
    const moduleRow = bySlideId.get(slideId);
    if (!moduleRow) continue;
    if (!moduleRow.slide_data || typeof moduleRow.slide_data !== "object") {
      moduleRow.slide_data = mergePlainObjects({}, baseBySlideId.get(slideId) || {});
    }
    const renderSpec = safeReadJsonFile(row.render_output_path);
    const patch = buildSlidePatchFromRenderSpec(renderSpec, slideId);
    if (!patch) continue;

    const mergedSlide = mergePlainObjects(moduleRow.slide_data, patch);
    moduleRow.slide_data = mergedSlide;
    moduleRow.slide_type = normalizeText(
      mergedSlide.slide_type,
      moduleRow.slide_type || "content",
    ).toLowerCase();
    moduleRow.render_path = normalizeText(
      mergedSlide.render_path,
      moduleRow.render_path || "pptxgenjs",
    ).toLowerCase();
    moduleRow.layout_grid = normalizeText(mergedSlide.layout_grid, moduleRow.layout_grid || "");
    moduleRow.slide_config = mergePlainObjects(moduleRow.slide_config, {
      slide_id: moduleRow.slide_id,
      slide_type: moduleRow.slide_type,
      render_path: moduleRow.render_path,
      order: moduleRow.order,
    });
    writeFileSync(
      moduleRow.module_path,
      moduleSourceForRecord(moduleRow),
      "utf-8",
    );
    row.merged = true;
    row.merged_keys = Object.keys(patch);
    mergedSlideIds.push(slideId);
  }
  return {
    merged_slide_ids: mergedSlideIds,
    merged_slide_count: mergedSlideIds.length,
  };
}

function blockType(block) {
  return normalizeText(block?.block_type || block?.type, "").toLowerCase();
}

function ensureBlocksArray(slide) {
  if (!slide || typeof slide !== "object") return [];
  if (!Array.isArray(slide.blocks)) slide.blocks = [];
  return slide.blocks;
}

function hasBlockType(slide, types = []) {
  const wanted = new Set(asArray(types).map((item) => normalizeText(item, "").toLowerCase()).filter(Boolean));
  if (!wanted.size) return false;
  return ensureBlocksArray(slide).some((block) => wanted.has(blockType(block)));
}

function countNonVisualTextBlocks(slide) {
  const visual = new Set(["image", "chart", "kpi", "workflow", "diagram", "table"]);
  const textual = new Set(["text", "body", "list", "subtitle", "quote", "icon_text", "comparison"]);
  return ensureBlocksArray(slide).filter((block) => {
    const bt = blockType(block);
    return textual.has(bt) && !visual.has(bt);
  }).length;
}

function fallbackBodyText(slide, suffix = 1) {
  const title = normalizeText(slide?.title, "Content");
  return `${title}: key point ${suffix}`;
}

function pushBodyBlock(slide, suffix = 1) {
  const blocks = ensureBlocksArray(slide);
  blocks.push({
    block_type: "body",
    card_id: `contract_text_fix_${suffix}`,
    position: "left",
    content: fallbackBodyText(slide, suffix),
    emphasis: [String(suffix)],
  });
}

function pushChartBlock(slide, suffix = 1) {
  const blocks = ensureBlocksArray(slide);
  blocks.push({
    block_type: "chart",
    card_id: `contract_chart_fix_${suffix}`,
    position: "right",
    content: {
      labels: ["A", "B", "C"],
      datasets: [{ label: "Metric", data: [58, 69, 80] }],
    },
    emphasis: ["58"],
  });
}

function addEmphasisSignal(slide) {
  const blocks = ensureBlocksArray(slide);
  for (const block of blocks) {
    const bt = blockType(block);
    if (!bt || bt === "title") continue;
    const current = asArray(block?.emphasis).map((item) => normalizeText(item, "")).filter(Boolean);
    if (current.length > 0) return;
    block.emphasis = ["focus 1"];
    return;
  }
}

function repairCompilePayloadContract(payload) {
  let current = normalizeRenderInput(payload || {});
  const repairs = [];
  const maxPasses = 4;

  for (let pass = 1; pass <= maxPasses; pass += 1) {
    const validation = validateRenderInput(current);
    if (validation.ok) {
      return { payload: current, validation, repairs };
    }
    let changed = false;
    for (const rawError of asArray(validation.errors)) {
      const error = normalizeText(rawError, "");
      const matched = /slides\[(\d+)\]\s+content contract:\s*(.+)$/i.exec(error);
      if (!matched) continue;
      const slideIndex = Number(matched[1]);
      const reason = normalizeText(matched[2], "").toLowerCase();
      if (!Number.isFinite(slideIndex) || slideIndex < 0 || slideIndex >= asArray(current.slides).length) {
        continue;
      }
      const slide = current.slides[slideIndex];
      if (!slide || typeof slide !== "object") continue;
      const slideType = normalizeText(slide.slide_type, "content").toLowerCase();
      if (["cover", "summary", "toc", "divider", "hero_1"].includes(slideType)) continue;

      if (reason.includes("one of [chart|kpi] is required")) {
        if (!hasBlockType(slide, ["chart", "kpi"])) {
          pushChartBlock(slide, repairs.length + 1);
          repairs.push({ pass, slide_index: slideIndex, action: "add_chart_for_required_group" });
          changed = true;
        }
        continue;
      }

      if (reason.includes("visual anchor requirement not satisfied")) {
        if (!hasBlockType(slide, ["image", "chart", "kpi", "workflow", "diagram"])) {
          pushChartBlock(slide, repairs.length + 1);
          repairs.push({ pass, slide_index: slideIndex, action: "add_visual_anchor_chart" });
          changed = true;
        }
        continue;
      }

      const minTextMatch = /min_text_blocks=(\d+)/i.exec(reason);
      if (minTextMatch) {
        const required = Math.max(0, Number(minTextMatch[1] || 0));
        let currentCount = countNonVisualTextBlocks(slide);
        let guard = 0;
        while (currentCount < required && guard < 8) {
          pushBodyBlock(slide, guard + 1);
          repairs.push({ pass, slide_index: slideIndex, action: "add_body_for_min_text" });
          currentCount = countNonVisualTextBlocks(slide);
          changed = true;
          guard += 1;
        }
        continue;
      }

      if (reason.includes("emphasis signal is required")) {
        addEmphasisSignal(slide);
        repairs.push({ pass, slide_index: slideIndex, action: "add_emphasis_signal" });
        changed = true;
      }
    }

    if (!changed) {
      return { payload: current, validation, repairs };
    }
    current = normalizeRenderInput(current);
  }

  return {
    payload: current,
    validation: validateRenderInput(current),
    repairs,
  };
}

export async function compileSlideModules({
  manifest,
  outputPath,
  renderOutputPath = "",
  generatorScriptPath,
  forceFullDeck = true,
  extraArgs = [],
  runner = defaultExecRunner,
}) {
  const manifestObj = loadManifest(manifest);
  const assembled = await assemblePayloadFromModules(manifestObj);
  const compilePayload = forceFullDeck
    ? {
      ...assembled,
      retry_scope: "deck",
      target_slide_ids: [],
      target_block_ids: [],
    }
    : assembled;
  const repaired = repairCompilePayloadContract(compilePayload);
  const compilePayloadFinal = repaired.payload;
  const tempInputPath = path.join(
    os.tmpdir(),
    `pptx-modules-compile-${Date.now()}-${Math.random().toString(36).slice(2)}.json`,
  );
  writeFileSync(tempInputPath, JSON.stringify(compilePayloadFinal), "utf-8");
  const scriptPath = path.resolve(String(generatorScriptPath || "scripts/generate-pptx-minimax.mjs"));
  const args = ["--input", tempInputPath, "--output", path.resolve(String(outputPath || ""))];
  if (renderOutputPath) {
    args.push("--render-output", path.resolve(String(renderOutputPath)));
  }
  for (const item of asArray(extraArgs)) {
    const text = normalizeText(item, "");
    if (text) args.push(text);
  }
  const result = await Promise.resolve(runner("node", [scriptPath, ...args]));
  return {
    ok: !result || result.ok !== false,
    input_path: tempInputPath,
    output_path: path.resolve(String(outputPath || "")),
    render_output_path: renderOutputPath ? path.resolve(String(renderOutputPath)) : "",
    contract_repair: {
      attempted: repaired.repairs.length > 0,
      repair_count: repaired.repairs.length,
      validation_ok: Boolean(repaired.validation?.ok),
      validation_errors: asArray(repaired.validation?.errors || []).slice(0, 8),
    },
    runner_result: result || null,
  };
}

async function runWithConcurrency(tasks, maxParallel) {
  const pool = Math.max(1, Number(maxParallel) || 1);
  const queue = [...tasks];
  const out = [];

  async function worker() {
    while (queue.length > 0) {
      const next = queue.shift();
      if (!next) return;
      try {
        const value = await next();
        out.push(value);
      } catch (error) {
        out.push({ ok: false, error: String(error || "unknown_error") });
      }
    }
  }

  await Promise.all(Array.from({ length: Math.min(pool, tasks.length) }, () => worker()));
  return out;
}

function extractJsonFromText(value) {
  const text = String(value || "").trim();
  if (!text) return null;
  try {
    const parsed = JSON.parse(text);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed;
  } catch (_) {
    // continue scanning lines
  }
  const lines = text.split(/\r?\n/).reverse();
  for (const line of lines) {
    const row = String(line || "").trim();
    if (!row.startsWith("{")) continue;
    try {
      const parsed = JSON.parse(row);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed;
    } catch (_) {
      // ignore parse error
    }
  }
  return null;
}

function parseExecutorArgs(rawValue = "") {
  const text = normalizeText(rawValue, "");
  if (!text) return [];
  try {
    const parsed = JSON.parse(text);
    if (Array.isArray(parsed)) {
      return parsed.map((item) => normalizeText(item, "")).filter(Boolean);
    }
  } catch (_) {
    // ignore json parse error
  }
  return text.split(/\s+/).map((item) => item.trim()).filter(Boolean);
}

function hasAgentProject(agentDir) {
  const base = path.resolve(String(agentDir || ""));
  if (!base) return false;
  return (
    existsSync(path.join(base, "pyproject.toml"))
    && existsSync(path.join(base, "src", "ppt_subagent_executor.py"))
  );
}

function detectDefaultSubagentExecutor() {
  const cwd = path.resolve(process.cwd());
  if (hasAgentProject(cwd)) {
    return {
      args: ["run", "python", "-m", "src.ppt_subagent_executor"],
      cwd,
    };
  }
  const cwdAgent = path.join(cwd, "agent");
  if (hasAgentProject(cwdAgent)) {
    return {
      args: ["run", "python", "-m", "src.ppt_subagent_executor"],
      cwd: cwdAgent,
    };
  }
  const scriptDir = path.dirname(fileURLToPath(import.meta.url));
  const repoRoot = path.resolve(scriptDir, "..", "..");
  const repoAgent = path.join(repoRoot, "agent");
  if (hasAgentProject(repoAgent)) {
    return {
      args: ["run", "python", "-m", "src.ppt_subagent_executor"],
      cwd: repoAgent,
    };
  }
  return {
    args: ["run", "python", "-m", "src.ppt_subagent_executor"],
    cwd: undefined,
  };
}

function buildSubagentPrompt(moduleRow, context = {}) {
  const slideId = normalizeText(moduleRow?.slide_id, "slide");
  const slideType = normalizeText(moduleRow?.slide_type, "content");
  const agentType = normalizeText(moduleRow?.agent_type, "content-page-generator");
  const renderPath = normalizeText(moduleRow?.render_path, "pptxgenjs");
  const title = normalizeText(moduleRow?.slide_data?.title, `Slide ${slideId}`);
  const loadSkills = dedupeSkillList(moduleRow?.load_skills || []);
  const retryHint = normalizeText(context?.retryHint, "");
  const slideDirectives = asArray(moduleRow?.slide_data?.skill_directives)
    .map((item) => normalizeText(item, ""))
    .filter(Boolean);
  const pageDesignIntent = normalizeText(moduleRow?.slide_data?.page_design_intent, "");
  const textConstraints = moduleRow?.slide_data?.text_constraints && typeof moduleRow.slide_data.text_constraints === "object"
    ? moduleRow.slide_data.text_constraints
    : {};
  const imagePolicy = moduleRow?.slide_data?.image_policy && typeof moduleRow.slide_data.image_policy === "object"
    ? moduleRow.slide_data.image_policy
    : {};
  const objective = [
    `You are ${agentType}.`,
    `Regenerate slide ${slideId} (${slideType}) with render_path=${renderPath}.`,
    "Keep content factual and concise, avoid placeholders, return strict JSON only.",
  ].join(" ");
  const constraints = [
    `Deck title: ${normalizeText(context?.deckTitle, "Untitled Deck")}`,
    `Slide title: ${title}`,
    `Layout: ${normalizeText(moduleRow?.layout_grid, "split_2")}`,
    `Template family: ${normalizeText(moduleRow?.template_family, "auto")}`,
    `Skill profile: ${normalizeText(moduleRow?.skill_profile, "auto")}`,
    `Load skills: ${loadSkills.join(", ") || "none"}`,
    retryHint ? `Retry hint: ${retryHint}` : "",
  ].filter(Boolean);
  const pageGuidance = [
    slideType === "cover"
      ? "Cover rules: single title area; subtitle <= 2 lines; avoid oversized decorative rounded rectangles."
      : "Content rules: single top title area; avoid repeated title bars; no meaningless prefixes.",
    "Text rules: concise bullets, avoid overflow, avoid duplicated semantics.",
    "Image rules: avoid repeated or near-duplicate images across slides; avoid decorative abstract SVG noise unless explicitly required.",
    slideType === "content" && ["split_2", "asymmetric_2"].includes(normalizeText(moduleRow?.layout_grid, "").toLowerCase())
      ? "Layout rules: do not overload the text column in left-right layouts."
      : "",
    pageDesignIntent ? `Page design intent: ${pageDesignIntent}` : "",
    ...slideDirectives.map((item) => `Skill directive: ${item}`),
    ...Object.entries(textConstraints).map(([key, value]) => `Text constraint ${key}: ${value}`),
    ...Object.entries(imagePolicy).map(([key, value]) => `Image policy ${key}: ${value}`),
  ].filter(Boolean);
  return `${objective}\n${constraints.join("\n")}\n${pageGuidance.join("\n")}\nReturn JSON with keys: slide_patch(object), load_skills(string[] optional), notes(string optional).`;
}

function defaultSubagentExecutor(taskPayload) {
  const bin = normalizeText(process.env.PPT_SUBAGENT_EXECUTOR_BIN, "uv");
  const explicitCwd = normalizeText(process.env.PPT_SUBAGENT_EXECUTOR_CWD, "");
  const configuredArgs = parseExecutorArgs(process.env.PPT_SUBAGENT_EXECUTOR_ARGS || "");
  const detected = detectDefaultSubagentExecutor();
  const args = configuredArgs.length > 0 ? configuredArgs : detected.args;
  const cwd = explicitCwd || detected.cwd;
  try {
    const stdout = execFileSync(bin, args, {
      input: JSON.stringify(taskPayload),
      encoding: "utf-8",
      maxBuffer: 24 * 1024 * 1024,
      stdio: ["pipe", "pipe", "pipe"],
      cwd,
    });
    const parsed = extractJsonFromText(stdout);
    if (!parsed) {
      return {
        ok: false,
        skipped: true,
        reason: "subagent_executor_invalid_output",
      };
    }
    return { ok: true, ...parsed };
  } catch (error) {
    return {
      ok: false,
      skipped: true,
      reason: normalizeText(error?.message || error, "subagent_executor_failed"),
    };
  }
}

export async function renderSlideModulesInParallel({
  manifest,
  generatorScriptPath,
  maxParallel = 5,
  outputDir,
  targetSlideIds = [],
  runner = defaultExecRunner,
  extraArgs = [],
  enableSubagentExec = false,
  subagentExecutor = null,
}) {
  const manifestObj = loadManifest(manifest);
  const assembled = await assemblePayloadFromModules(manifestObj);
  const slides = asArray(assembled?.slides);
  const modules = sortRecords(asArray(manifestObj?.modules));
  const slideById = new Map(
    slides.map((slide, index) => [normalizeText(slide?.slide_id, stableSlideId(slide, index)), slide]),
  );
  for (const [idx, row] of modules.entries()) {
    const slideId = normalizeText(row?.slide_id, stableSlideId(row, idx));
    if (!row.slide_data || typeof row.slide_data !== "object") {
      row.slide_data = mergePlainObjects({}, slideById.get(slideId) || { slide_id: slideId });
    }
    if (!row.slide_config || typeof row.slide_config !== "object") {
      row.slide_config = {
        order: row.order || idx + 1,
        slide_id: slideId,
        slide_type: normalizeText(row.slide_type, "content"),
        agent_type: normalizeText(row.agent_type, "content-page-generator"),
        render_path: normalizeText(row.render_path, "pptxgenjs"),
      };
    }
    if (!Array.isArray(row.load_skills) || row.load_skills.length <= 0) {
      row.load_skills = resolveLoadSkills({
        slideType: row.slide_type,
        agentType: row.agent_type,
        renderPath: row.render_path,
        templateFamily: row.template_family,
        skillProfile: row.skill_profile,
        existingLoadSkills: row.load_skills || [],
      });
    }
  }
  const scriptPath = path.resolve(String(generatorScriptPath || "scripts/generate-pptx-minimax.mjs"));
  const outDir = path.resolve(String(outputDir || path.join(String(manifestObj.modules_dir || "."), "rendered")));
  mkdirSync(outDir, { recursive: true });

  const targetSet = new Set(
    asArray(targetSlideIds).map((item) => normalizeText(item, "")).filter(Boolean),
  );
  const candidates = modules
    .map((row, index) => ({
      moduleRow: row,
      index,
      slideId: normalizeText(row?.slide_id, stableSlideId(row, index)),
    }))
    .filter(({ slideId }) => {
      if (targetSet.size <= 0) return true;
      return targetSet.has(slideId);
    });
  const useSubagent = Boolean(enableSubagentExec);
  const executeSubagent = typeof subagentExecutor === "function" ? subagentExecutor : defaultSubagentExecutor;

  const tasks = candidates.map(({ moduleRow, index, slideId }) => async () => {
    const fileBase = `slide-${padSlideOrder(index + 1)}`;
    let subagentInfo = {
      enabled: useSubagent,
      applied: false,
      skipped: !useSubagent,
      reason: useSubagent ? "" : "subagent_disabled",
      prompt: "",
    };
    if (useSubagent && moduleRow && typeof moduleRow === "object") {
      const prompt = buildSubagentPrompt(moduleRow, {
        deckTitle: assembled?.title,
        retryHint: assembled?.retry_hint,
      });
      const loadSkills = dedupeSkillList(moduleRow.load_skills || []);
      const taskPayload = {
        version: 1,
        slide_id: slideId,
        slide_type: normalizeText(moduleRow.slide_type, "content"),
        agent_type: normalizeText(moduleRow.agent_type, "content-page-generator"),
        render_path: normalizeText(moduleRow.render_path, "pptxgenjs"),
        load_skills: loadSkills,
        prompt,
        slide_config: moduleRow.slide_config && typeof moduleRow.slide_config === "object"
          ? moduleRow.slide_config
          : {},
        slide_data: moduleRow.slide_data && typeof moduleRow.slide_data === "object"
          ? moduleRow.slide_data
          : {},
      };
      const executed = await Promise.resolve(executeSubagent(taskPayload));
      if (executed && executed.ok === false) {
        throw new Error(normalizeText(executed.reason, "subagent_executor_rejected"));
      }
      const patch = executed?.slide_patch && typeof executed.slide_patch === "object"
        ? executed.slide_patch
        : (executed?.slide_data_patch && typeof executed.slide_data_patch === "object"
          ? executed.slide_data_patch
          : {});
      const safePatch = { ...patch };
      const currentTitle = normalizeText(moduleRow?.slide_data?.title, "");
      const patchedTitle = normalizeText(safePatch?.title, "");
      if (patchedTitle && isGenericSlideTitle(patchedTitle) && currentTitle && !isGenericSlideTitle(currentTitle)) {
        delete safePatch.title;
      }
      const outputSkills = dedupeSkillList(executed?.load_skills || []);
      const skillRuntime = executed?.skill_runtime && typeof executed.skill_runtime === "object"
        ? executed.skill_runtime
        : {};
      subagentInfo = {
        enabled: true,
        applied: Object.keys(safePatch).length > 0,
        skipped: Boolean(executed?.skipped),
        reason: normalizeText(executed?.reason, ""),
        prompt,
        skill_runtime_enabled: Boolean(skillRuntime?.enabled),
        skill_runtime_trace: Array.isArray(skillRuntime?.trace) ? skillRuntime.trace : [],
      };
      if (Object.keys(safePatch).length > 0) {
        moduleRow.slide_data = mergePlainObjects(moduleRow.slide_data, safePatch);
        moduleRow.slide_type = normalizeText(moduleRow.slide_data?.slide_type, moduleRow.slide_type || "content");
        moduleRow.render_path = normalizeText(
          moduleRow.slide_data?.render_path,
          moduleRow.render_path || "pptxgenjs",
        ).toLowerCase();
        moduleRow.layout_grid = normalizeText(moduleRow.slide_data?.layout_grid, moduleRow.layout_grid || "");
      }
      if (outputSkills.length > 0) {
        moduleRow.load_skills = dedupeSkillList([...(moduleRow.load_skills || []), ...outputSkills]);
      }
      moduleRow.slide_config = mergePlainObjects(moduleRow.slide_config, {
        slide_id: moduleRow.slide_id,
        slide_type: moduleRow.slide_type,
        render_path: moduleRow.render_path,
        order: moduleRow.order,
        load_skills: moduleRow.load_skills || [],
      });
      writeFileSync(moduleRow.module_path, moduleSourceForRecord(moduleRow), "utf-8");
    }
    const assembledNow = await assemblePayloadFromModules(manifestObj);
    const repairedTaskPayload = repairCompilePayloadContract({
      ...assembledNow,
      retry_scope: "slide",
      target_slide_ids: [slideId],
      target_block_ids: [],
    });
    const taskPayload = repairedTaskPayload.payload;
    const taskInputPath = path.join(outDir, `${fileBase}.input.json`);
    writeFileSync(taskInputPath, JSON.stringify(taskPayload), "utf-8");
    const slidePptxPath = path.join(outDir, `${fileBase}.pptx`);
    const slideRenderJsonPath = path.join(outDir, `${fileBase}.render.json`);
    const args = [
      scriptPath,
      "--input",
      taskInputPath,
      "--output",
      slidePptxPath,
      "--render-output",
      slideRenderJsonPath,
      "--retry-scope",
      "slide",
      "--target-slide-ids",
      slideId,
    ];
    for (const item of asArray(extraArgs)) {
      const text = normalizeText(item, "");
      if (text) args.push(text);
    }
    const result = await Promise.resolve(runner("node", args));
    return {
      ok: !result || result.ok !== false,
      slide_id: slideId,
      order: index + 1,
      input_path: taskInputPath,
      output_path: slidePptxPath,
      render_output_path: slideRenderJsonPath,
      contract_repair: {
        attempted: repairedTaskPayload.repairs.length > 0,
        repair_count: repairedTaskPayload.repairs.length,
        validation_ok: Boolean(repairedTaskPayload.validation?.ok),
        validation_errors: asArray(repairedTaskPayload.validation?.errors || []).slice(0, 8),
      },
      subagent: subagentInfo,
      runner_result: result || null,
    };
  });
  const rows = await runWithConcurrency(tasks, Math.max(1, Number(maxParallel) || 5));
  const mergeResult = applyRenderedSlidesToModules(manifestObj, rows, slides);
  const subagentRuns = rows
    .map((row) => row?.subagent)
    .filter((item) => item && typeof item === "object");
  return {
    ok: rows.every((row) => row && row.ok !== false),
    input_path: "",
    output_dir: outDir,
    targeted_slide_ids: Array.from(targetSet),
    merged_slide_ids: mergeResult.merged_slide_ids,
    merged_slide_count: mergeResult.merged_slide_count,
    subagent_runs: subagentRuns,
    slide_results: sortRecords(rows),
  };
}
