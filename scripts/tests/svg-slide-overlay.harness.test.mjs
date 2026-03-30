import test from "node:test";
import assert from "node:assert/strict";

import { addSvgOverlay } from "../minimax/svg-slide.mjs";

function fakeSlide() {
  const calls = [];
  return {
    calls,
    addImage(options) {
      calls.push(options || {});
    },
  };
}

const SIMPLE_SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" viewBox="0 0 960 540"><rect x="80" y="80" width="260" height="140" fill="#2F7BFF"/><text x="110" y="170" font-size="36" fill="#FFFFFF">fallback</text></svg>';

test("svg overlay keeps svg data uri by default", () => {
  const slide = fakeSlide();
  const ok = addSvgOverlay(slide, SIMPLE_SVG);
  assert.equal(ok, true);
  assert.equal(slide.calls.length, 1);
  assert.match(String(slide.calls[0]?.data || ""), /^image\/svg\+xml;base64,/);
});

test("svg overlay uses png data uri when preferPng is enabled", () => {
  const slide = fakeSlide();
  const ok = addSvgOverlay(
    slide,
    SIMPLE_SVG,
    { x: 0, y: 0, w: 10, h: 5.625 },
    { preferPng: true, pngPixelWidth: 1280, pngPixelHeight: 720 },
  );
  assert.equal(ok, true);
  assert.equal(slide.calls.length, 1);
  assert.match(String(slide.calls[0]?.data || ""), /^image\/png;base64,/);
});

