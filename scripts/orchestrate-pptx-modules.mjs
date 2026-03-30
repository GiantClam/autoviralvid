import { parseArgs } from "node:util";
import { readFileSync } from "node:fs";
import path from "node:path";
import {
  compileSlideModules,
  renderSlideModulesInParallel,
  writeSlideModules,
} from "./minimax/slide-module-orchestrator.mjs";

const { values } = parseArgs({
  options: {
    input: { type: "string" },
    "modules-dir": { type: "string" },
    manifest: { type: "string" },
    compile: { type: "boolean" },
    "render-each": { type: "boolean" },
    output: { type: "string" },
    "render-output": { type: "string" },
    "max-parallel": { type: "string" },
    "generator-script": { type: "string" },
    "target-slide-ids": { type: "string" },
    "subagent-exec": { type: "boolean" },
  },
});

if (!values.input || !values["modules-dir"]) {
  console.error(
    "Usage: node scripts/orchestrate-pptx-modules.mjs --input <render_payload.json> --modules-dir <dir> [--manifest <manifest.json>] [--render-each] [--target-slide-ids s1,s2] [--max-parallel 5] [--compile --output <deck.pptx> --render-output <deck.render.json>] [--generator-script scripts/generate-pptx-minimax.mjs]",
  );
  process.exit(1);
}

const inputPath = path.resolve(String(values.input));
const modulesDir = path.resolve(String(values["modules-dir"]));
const manifestPath = values.manifest ? path.resolve(String(values.manifest)) : "";
const raw = readFileSync(inputPath, "utf-8");
const payload = JSON.parse(raw.charCodeAt(0) === 0xfeff ? raw.slice(1) : raw);

async function main() {
  const generated = writeSlideModules(payload, modulesDir, {
    manifestPath: manifestPath || undefined,
  });
  const result = {
    success: true,
    stage: "modules_generated",
    manifest_path: generated.manifest_path,
    module_count: Array.isArray(generated.manifest?.modules) ? generated.manifest.modules.length : 0,
  };

  if (values["render-each"]) {
    const targetSlideIds = String(values["target-slide-ids"] || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const renderResult = await renderSlideModulesInParallel({
      manifest: generated.manifest,
      generatorScriptPath: values["generator-script"] || "scripts/generate-pptx-minimax.mjs",
      maxParallel: Number(values["max-parallel"] || 5),
      targetSlideIds,
      enableSubagentExec: Boolean(values["subagent-exec"]),
    });
    result.render_each = renderResult;
    if (!renderResult.ok) {
      result.success = false;
    }
  }

  if (values.compile) {
    if (!values.output) {
      throw new Error("--output is required when --compile is set");
    }
    const compileResult = await compileSlideModules({
      manifest: generated.manifest,
      outputPath: String(values.output),
      renderOutputPath: String(values["render-output"] || ""),
      generatorScriptPath: values["generator-script"] || "scripts/generate-pptx-minimax.mjs",
    });
    result.compile = compileResult;
    if (!compileResult.ok) {
      result.success = false;
    }
  }

  console.log(JSON.stringify(result));
  if (!result.success) {
    process.exit(2);
  }
}

main().catch((error) => {
  console.error(
    JSON.stringify({
      success: false,
      error: String(error?.message || error || "unknown_error"),
    }),
  );
  process.exit(2);
});
