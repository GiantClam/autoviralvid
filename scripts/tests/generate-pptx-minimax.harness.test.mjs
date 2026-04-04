import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
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

test("generator harness: cover subtitle dedup and toc expands from downstream slide titles", () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "minimax-cover-toc-"));
  const scriptPath = fileURLToPath(new URL("../generate-pptx-minimax.mjs", import.meta.url));
  const inputPath = path.join(workDir, "input.json");
  const outputPath = path.join(workDir, "out.pptx");
  const renderOutputPath = path.join(workDir, "out.render.json");

  const payload = {
    title: "解码立法过程：理解其对国际关系的影响",
    slides: [
      {
        page_number: 1,
        slide_type: "cover",
        layout_grid: "hero_1",
        title: "解码立法过程：理解其对国际关系的影响",
        narration: "解码立法过程：理解其对国际关系的影响",
        blocks: [
          { block_type: "title", card_id: "title", content: "解码立法过程：理解其对国际关系的影响" },
          { block_type: "body", card_id: "body", content: "解码立法过程：理解其对国际关系的影响" },
        ],
      },
      {
        page_number: 2,
        slide_type: "toc",
        layout_grid: "asymmetric_2",
        title: "内容导航",
        blocks: [
          { block_type: "title", card_id: "title", content: "内容导航" },
          { block_type: "list", card_id: "list", content: "概念;机制;案例;总结" },
        ],
      },
      ...Array.from({ length: 6 }, (_, idx) => ({
        page_number: idx + 3,
        slide_type: "content",
        layout_grid: "split_2",
        title: `章节 ${idx + 1}`,
        blocks: [
          { block_type: "title", card_id: "title", content: `章节 ${idx + 1}` },
          { block_type: "body", card_id: "body", content: `要点 ${idx + 1}` },
        ],
      })),
      {
        page_number: 9,
        slide_type: "summary",
        layout_grid: "hero_1",
        title: "总结与启示",
        blocks: [
          { block_type: "title", card_id: "title", content: "总结与启示" },
          { block_type: "body", card_id: "body", content: "回顾重点" },
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
    const renderSlides = Array.isArray(renderJson?.slides) ? renderJson.slides : [];
    assert.equal(renderSlides.length >= 3, true);
    assert.equal(String(renderSlides[0]?.markdown || "").includes("## 解码立法过程：理解其对国际关系的影响"), false);
    const tocMarkdown = String(renderSlides[1]?.markdown || "");
    assert.equal(tocMarkdown.includes("- 05 章节 5"), true);

    const python = [
      "from zipfile import ZipFile",
      "from xml.etree import ElementTree as ET",
      "import re, sys",
      "ppt=sys.argv[1]",
      "ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}",
      "with ZipFile(ppt) as z:",
      " slide_names=[n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\\d+\\.xml', n)]",
      " slide_names.sort(key=lambda x:int(re.search(r'slide(\\d+)\\.xml$', x).group(1)))",
      " root=ET.fromstring(z.read(slide_names[0]))",
      " texts=[t.text.strip() for t in root.findall('.//a:t', ns) if t.text and t.text.strip()]",
      " print('\\n'.join(texts))",
    ].join("\n");
    const coverText = execFileSync("python3", ["-c", python, outputPath], { encoding: "utf-8" });
    const coverLines = coverText.split(/\r?\n/).filter(Boolean);
    const dupCount = coverLines.filter((line) => line === "解码立法过程：理解其对国际关系的影响").length;
    assert.equal(dupCount <= 1, true, `cover should not duplicate full title in subtitle, got: ${coverText}`);
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});
