import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const isWindows = process.platform === "win32";
const maxRetries = Number(process.env.PRISMA_GENERATE_RETRIES || (isWindows ? 6 : 2));
const baseDelayMs = Number(process.env.PRISMA_GENERATE_RETRY_DELAY_MS || 1200);
const configuredEngineType = (process.env.PRISMA_GENERATE_ENGINE_TYPE || "").trim().toLowerCase();
const staleEngineTempFilePatterns = [
  /^query_engine-windows\.dll\.node\.tmp\d*$/i,
  /^libquery_engine-windows\.dll\.node\.tmp\d*$/i,
  /^query-engine-windows\.exe\.tmp\d*$/i,
];
const windowsEngineLockMarkers = [
  "query_engine-windows.dll.node",
  "libquery_engine-windows.dll.node",
  "query-engine-windows.exe",
];

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function getPrismaClientDir() {
  return path.resolve(process.cwd(), "node_modules", ".prisma", "client");
}

function cleanupStaleTempFiles() {
  const clientDir = getPrismaClientDir();
  if (!fs.existsSync(clientDir)) return;

  const entries = fs.readdirSync(clientDir, { withFileTypes: true });
  for (const entry of entries) {
    if (!entry.isFile()) continue;
    if (!staleEngineTempFilePatterns.some((pattern) => pattern.test(entry.name))) continue;

    const target = path.join(clientDir, entry.name);
    try {
      fs.rmSync(target, { force: true });
      console.warn(`[prisma-generate-safe] Removed stale temp engine file: ${entry.name}`);
    } catch {
      // Best effort cleanup; lock may persist until next retry.
    }
  }
}

function runPrismaGenerate() {
  const env = { ...process.env };
  if (configuredEngineType === "binary" || configuredEngineType === "library") {
    env.PRISMA_CLIENT_ENGINE_TYPE = configuredEngineType;
    env.PRISMA_CLI_QUERY_ENGINE_TYPE = configuredEngineType;
  }

  const result = spawnSync("npx", ["prisma", "generate"], {
    shell: isWindows,
    encoding: "utf8",
    env,
  });

  if (result.stdout) process.stdout.write(result.stdout);
  if (result.stderr) process.stderr.write(result.stderr);

  return result;
}

function isLikelyWindowsEngineLock(result) {
  const combined = `${result.stdout || ""}\n${result.stderr || ""}\n${result.error?.message || ""}`;
  const normalized = combined.toLowerCase();
  const hasEngineMarker = windowsEngineLockMarkers.some((marker) => normalized.includes(marker));
  const hasLockSignal =
    normalized.includes("rename") ||
    normalized.includes("eperm") ||
    normalized.includes("ebusy") ||
    normalized.includes("eacces");

  return (
    isWindows &&
    hasEngineMarker &&
    hasLockSignal
  );
}

function printWindowsEngineLockHint() {
  if (!isWindows) return;
  console.error(
    "[prisma-generate-safe] Windows file lock detected. Stop active dev processes (for example `npm run dev` / `next dev`) and retry.",
  );
  console.error(
    "[prisma-generate-safe] If antivirus is scanning node_modules/.prisma/client, add a local exclusion and retry.",
  );
}

async function main() {
  cleanupStaleTempFiles();

  for (let attempt = 1; attempt <= maxRetries; attempt += 1) {
    const result = runPrismaGenerate();
    if (result.status === 0) return;

    if (!isLikelyWindowsEngineLock(result) || attempt === maxRetries) {
      if (isLikelyWindowsEngineLock(result)) {
        printWindowsEngineLockHint();
      }
      process.exit(typeof result.status === "number" ? result.status : 1);
    }

    const delay = baseDelayMs * attempt;
    console.warn(
      `[prisma-generate-safe] Prisma engine appears locked on Windows (attempt ${attempt}/${maxRetries}). Retrying in ${delay}ms...`,
    );
    cleanupStaleTempFiles();
    // eslint-disable-next-line no-await-in-loop
    await sleep(delay);
  }
}

main().catch((error) => {
  console.error("[prisma-generate-safe] Unexpected error:", error);
  process.exit(1);
});
