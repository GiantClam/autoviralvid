import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const WORKER_PATH = path.join(__dirname, "sharp-rasterizer-worker.mjs");
const CACHE = new Map();
const CACHE_LIMIT = 256;

function clampInt(value, fallback, min, max) {
  const raw = Number(value);
  if (!Number.isFinite(raw)) return fallback;
  const rounded = Math.round(raw);
  return Math.max(min, Math.min(max, rounded));
}

function trimCache() {
  while (CACHE.size > CACHE_LIMIT) {
    const first = CACHE.keys().next();
    if (first.done) break;
    CACHE.delete(first.value);
  }
}

function cacheKeyFor(svgText, width, height, density) {
  const hash = createHash("sha1")
    .update(String(svgText || ""))
    .update("\n")
    .update(String(width))
    .update(":")
    .update(String(height))
    .update(":")
    .update(String(density))
    .digest("hex");
  return `svg-png:${hash}`;
}

export function rasterizeSvgToPngDataUri(svgMarkup, options = {}) {
  const svgText = String(svgMarkup || "").trim();
  if (!svgText.startsWith("<svg")) return "";
  if (!existsSync(WORKER_PATH)) return "";

  const width = clampInt(options.width, 0, 0, 4096);
  const height = clampInt(options.height, 0, 0, 4096);
  const density = clampInt(options.density, 384, 72, 1200);
  const key = cacheKeyFor(svgText, width, height, density);
  const cached = CACHE.get(key);
  if (typeof cached === "string" && cached) return cached;

  try {
    const args = [WORKER_PATH, "--density", String(density)];
    if (width > 0) args.push("--width", String(width));
    if (height > 0) args.push("--height", String(height));
    const base64 = execFileSync(process.execPath, args, {
      input: svgText,
      encoding: "utf-8",
      maxBuffer: 24 * 1024 * 1024,
      stdio: ["pipe", "pipe", "pipe"],
    }).trim();
    if (!base64) return "";
    const payload = `image/png;base64,${base64}`;
    CACHE.set(key, payload);
    trimCache();
    return payload;
  } catch {
    return "";
  }
}

