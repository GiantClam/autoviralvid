import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

test("lingchuang new template generation honors per-slide template intent", () => {
  const workDir = mkdtempSync(path.join(tmpdir(), "lingchuang-template-gen-"));
  const scriptPath = fileURLToPath(new URL("./gen-lingchuang-new-templates.mjs", import.meta.url));
  try {
    const stdout = execFileSync(
      "node",
      [scriptPath, "--output-dir", workDir],
      { stdio: "pipe", encoding: "utf-8" },
    );
    const summary = JSON.parse(stdout || "{}");
    assert.equal(summary.ok, true, JSON.stringify(summary, null, 2));
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }
});
