import sharp from "sharp";

function readNumericArg(name, fallback) {
  const idx = process.argv.indexOf(name);
  if (idx < 0 || idx + 1 >= process.argv.length) return fallback;
  const raw = Number(process.argv[idx + 1]);
  return Number.isFinite(raw) ? raw : fallback;
}

function clampInt(value, fallback, min, max) {
  const raw = Number(value);
  if (!Number.isFinite(raw)) return fallback;
  const rounded = Math.round(raw);
  return Math.max(min, Math.min(max, rounded));
}

async function main() {
  const width = clampInt(readNumericArg("--width", 0), 0, 0, 4096);
  const height = clampInt(readNumericArg("--height", 0), 0, 0, 4096);
  const density = clampInt(readNumericArg("--density", 384), 384, 72, 1200);

  const chunks = [];
  for await (const chunk of process.stdin) {
    if (Buffer.isBuffer(chunk)) chunks.push(chunk);
    else chunks.push(Buffer.from(chunk));
  }
  const svgBuffer = Buffer.concat(chunks);
  if (!svgBuffer.length) {
    throw new Error("svg_input_empty");
  }

  let pipeline = sharp(svgBuffer, { density });
  if (width > 0 || height > 0) {
    pipeline = pipeline.resize(width || null, height || null, {
      fit: "contain",
      withoutEnlargement: false,
    });
  }

  const pngBuffer = await pipeline
    .png({
      compressionLevel: 9,
      adaptiveFiltering: true,
      effort: 7,
    })
    .toBuffer();
  process.stdout.write(pngBuffer.toString("base64"));
}

main().catch((error) => {
  const message = String(error?.message || error || "unknown_error");
  process.stderr.write(message);
  process.exit(2);
});

