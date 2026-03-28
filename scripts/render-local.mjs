/**
 * 本地渲染脚本 - 使用 @remotion/renderer 在本机渲染视频
 * 用法: node scripts/render-local.mjs --input <json_file> --output <mp4_file>
 *
 * 不依赖 AWS Lambda，使用本地 Chrome + FFmpeg 渲染
 */

import { parseArgs } from 'node:util';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));

const { values } = parseArgs({
  options: {
    input: { type: 'string' },
    output: { type: 'string' },
  },
});

if (!values.input || !values.output) {
  console.error('Usage: node render-local.mjs --input <json_file> --output <mp4_file>');
  process.exit(1);
}

const input = JSON.parse(readFileSync(values.input, 'utf-8'));
const { slides, config = {} } = input;

const {
  width = 1920,
  height = 1080,
  fps = 30,
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
const transitionSec = compositionId === 'ImageSlideshow' ? Math.max(slides.length - 1, 0) * 0.5 : 0;
const totalDurationSec =
  (compositionId === 'ImageSlideshow' ? imageSlides : slides).reduce(
    (sum, s) => sum + Math.max(0.1, toNumber(s.duration, 6)),
    0,
  ) + transitionSec;
const durationInFrames = Math.max(1, Math.round(totalDurationSec * fps));

console.log(JSON.stringify({
  type: 'start',
  slides: slides.length,
  durationInFrames,
  fps,
  resolution: `${width}x${height}`,
}));

async function main() {
  const { renderMedia, selectComposition } = await import('@remotion/renderer');
  const { bundle } = await import('@remotion/bundler');

  // 先打包 Remotion bundle
  console.log(JSON.stringify({ type: 'bundling' }));
  const serveUrl = await bundle({
    entryPoint: resolve(__dirname, '..', 'src', 'remotion', 'index.tsx'),
    publicDir: resolve(__dirname, '..', 'public'),
  });
  console.log(JSON.stringify({ type: 'bundled', serveUrl }));

  const inputProps =
    compositionId === 'ImageSlideshow'
      ? {
          slides: imageSlides,
        }
      : {
          slides,
          bgmUrl,
          bgmVolume,
          defaultTransition: transition,
        };

  // 选择合成配置
  const composition = await selectComposition({
    serveUrl,
    id: compositionId,
    inputProps,
  });

  // 覆盖尺寸和帧率
  composition.width = width;
  composition.height = height;
  composition.durationInFrames = durationInFrames;
  composition.fps = fps;

  console.log(JSON.stringify({
    type: 'rendering',
    composition: compositionId,
    frames: durationInFrames,
  }));

  // 渲染
  await renderMedia({
    composition,
    serveUrl,
    codec: 'h264',
    outputLocation: values.output,
    inputProps,
    onProgress: ({ progress }) => {
      // 每 10% 输出一次进度
      const pct = Math.round(progress * 100);
      if (pct % 10 === 0) {
        console.log(JSON.stringify({ type: 'progress', progress: pct }));
      }
    },
  });

  console.log(JSON.stringify({
    type: 'done',
    output: values.output,
  }));
}

main().catch(err => {
  console.error(JSON.stringify({
    type: 'error',
    error: err.message || String(err),
  }));
  process.exit(1);
});
