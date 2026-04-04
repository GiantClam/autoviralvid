import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..", "..");
const tempRoot = path.join(repoRoot, "test_outputs", "tmp-theme-recipe-axis");
mkdirSync(tempRoot, { recursive: true });

function runCase(themeRecipe, expectedStyle, expectedTone = "light") {
  const workdir = mkdtempSync(path.join(tempRoot, `${themeRecipe}-`));
  try {
    const inputPath = path.join(workdir, "input.json");
    const outputPath = path.join(workdir, "deck.pptx");
    const renderPath = path.join(workdir, "render.json");
    writeFileSync(
      inputPath,
      JSON.stringify(
        {
          title: "Theme Recipe Deck",
          theme_recipe: themeRecipe,
          tone: "auto",
          slides: [
            {
              page_number: 1,
              slide_id: "s1",
              slide_type: "content",
              title: "课堂流程概览",
              blocks: [
                { block_type: "title", card_id: "title", content: "课堂流程概览" },
                { block_type: "body", card_id: "body", content: "核心结论 32%" },
                { block_type: "list", card_id: "list", content: "步骤一;步骤二" },
              ],
            },
          ],
        },
        null,
        2,
      ),
      "utf-8",
    );

    const result = spawnSync(
      "node",
      [
        "scripts/generate-pptx-minimax.mjs",
        "--input",
        inputPath,
        "--output",
        outputPath,
        "--render-output",
        renderPath,
      ],
      {
        cwd: repoRoot,
        encoding: "utf-8",
      },
    );
    assert.equal(result.status, 0, `${result.stderr || result.stdout}`);
    const render = JSON.parse(readFileSync(renderPath, "utf-8"));
    assert.equal(render.theme_recipe, themeRecipe);
    assert.equal(render.tone, expectedTone);
    assert.equal(render.style_variant, expectedStyle);
  } finally {
    rmSync(workdir, { recursive: true, force: true });
  }
}

runCase("classroom_soft", "rounded");
runCase("editorial_magazine", "soft");

console.log("theme-recipe-axis harness passed");
