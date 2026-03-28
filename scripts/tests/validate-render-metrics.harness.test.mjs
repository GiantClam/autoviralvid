import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

test("validate-render-metrics: passes when official input is visual-first", () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "render-metrics-"));
  const scriptPath = fileURLToPath(new URL("./validate-render-metrics.mjs", import.meta.url));
  const fixturePath = path.join(workDir, "ok.render.json");
  const payload = {
    slides: [
      { slide_type: "cover", template_family: "hero_tech_cover" },
      { slide_type: "content", template_family: "dashboard_dark" },
      { slide_type: "content", template_family: "split_media_dark" },
      { slide_type: "summary", template_family: "hero_dark" },
    ],
    official_input: {
      slides: [
        { page_type: "cover", blocks: [{ type: "title", content: "t" }] },
        { page_type: "content", blocks: [{ type: "chart", content: "c" }] },
        { page_type: "content", blocks: [{ type: "kpi", content: "k" }] },
        { page_type: "summary", blocks: [{ type: "list", content: "s" }] },
      ],
    },
  };
  writeFileSync(fixturePath, JSON.stringify(payload, null, 2), "utf-8");

  try {
    execFileSync("node", [scriptPath, fixturePath], { stdio: "pipe" });
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});

test("validate-render-metrics: fails when content slides are text-only", () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "render-metrics-"));
  const scriptPath = fileURLToPath(new URL("./validate-render-metrics.mjs", import.meta.url));
  const fixturePath = path.join(workDir, "bad.render.json");
  const payload = {
    slides: [
      { slide_type: "cover", template_family: "hero_tech_cover" },
      { slide_type: "content", template_family: "dashboard_dark" },
      { slide_type: "content", template_family: "dashboard_dark" },
      { slide_type: "summary", template_family: "hero_dark" },
    ],
    official_input: {
      slides: [
        { page_type: "cover", blocks: [{ type: "title", content: "t" }] },
        { page_type: "content", blocks: [{ type: "body", content: "b1" }] },
        { page_type: "content", blocks: [{ type: "list", content: "b2" }] },
        { page_type: "summary", blocks: [{ type: "list", content: "s" }] },
      ],
    },
  };
  writeFileSync(fixturePath, JSON.stringify(payload, null, 2), "utf-8");

  let failed = false;
  try {
    execFileSync("node", [scriptPath, fixturePath], { stdio: "pipe" });
  } catch {
    failed = true;
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
  assert.equal(failed, true);
});
