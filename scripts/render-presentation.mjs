/**
 * Remotion Lambda render script.
 * Usage: node scripts/render-presentation.mjs --input <json_file> [--webhook <url>]
 */

import { parseArgs } from 'node:util';
import { readFileSync } from 'node:fs';

const { values } = parseArgs({
  options: {
    input: { type: 'string' },
    webhook: { type: 'string', default: undefined },
  },
});

if (!values.input) {
  console.error('Usage: node render-presentation.mjs --input <json_file> [--webhook <url>]');
  process.exit(1);
}

const input = JSON.parse(readFileSync(values.input, 'utf-8'));
const { slides, config = {} } = input;

const {
  transition = 'fade',
  bgmUrl,
  bgmVolume = 0.15,
  composition,
} = config;

const toNumber = (value, fallback) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
};
const isImageSlide = (slide) =>
  Boolean(String(slide?.imageUrl || slide?.image_url || '').trim());
const normalizeImageSlides = (items) =>
  items.map((slide) => {
    const imageUrl = String(slide?.imageUrl || slide?.image_url || '').trim();
    const audioUrl = String(slide?.audioUrl || slide?.audio_url || '').trim();
    const duration = Math.max(3, toNumber(slide?.duration, 6));
    return {
      imageUrl,
      audioUrl: audioUrl || undefined,
      duration,
    };
  });

const hasImageSlides = slides.length > 0 && slides.every((slide) => isImageSlide(slide));
const imageSlides = hasImageSlides ? normalizeImageSlides(slides) : [];
const compositionId = composition || (hasImageSlides ? 'ImageSlideshow' : 'SlidePresentation');

const functionName = process.env.REMOTION_LAMBDA_FUNCTION;
const region = process.env.AWS_REGION || 'us-east-1';
const serveUrl = process.env.REMOTION_SERVE_URL;

if (!functionName || !serveUrl) {
  console.error(
    JSON.stringify({
      error: 'Missing REMOTION_LAMBDA_FUNCTION or REMOTION_SERVE_URL environment variables',
    }),
  );
  process.exit(1);
}

try {
  let renderMediaOnLambda;
  try {
    const lambda = await import('@remotion/lambda-client');
    renderMediaOnLambda = lambda.renderMediaOnLambda;
  } catch {
    try {
      const lambda = await import('@remotion/lambda');
      renderMediaOnLambda = lambda.renderMediaOnLambda;
    } catch {
      throw new Error('@remotion/lambda-client is not installed. Run: npm install @remotion/lambda-client');
    }
  }

  const result = await renderMediaOnLambda({
    functionName,
    region,
    serveUrl,
    composition: compositionId,
    inputProps:
      compositionId === 'ImageSlideshow'
        ? {
            slides: imageSlides,
          }
        : {
            slides,
            bgmUrl,
            bgmVolume,
            defaultTransition: transition,
          },
    codec: 'h264',
    outName: `ppt-video-${Date.now()}.mp4`,
    framesPerLambda: 100,
    maxRetriesPerLambda: 2,
    privacy: 'public',
    webhook: values.webhook ? { url: values.webhook } : undefined,
  });

  process.stdout.write(
    JSON.stringify({
      renderId: result.renderId,
      videoUrl: result.outputFile,
      costsInDollars: result.costsInDollars,
    }),
  );
} catch (error) {
  console.error(
    JSON.stringify({
      error: error.message || String(error),
    }),
  );
  process.exit(1);
}
