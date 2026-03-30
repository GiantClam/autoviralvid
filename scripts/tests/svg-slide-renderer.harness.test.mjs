import test from "node:test";
import assert from "node:assert/strict";

import { parseSvgElements, svgPathToCustomGeometryPoints } from "../minimax/svg-slide-renderer.mjs";

test("svg renderer parses svg primitives from markup", () => {
  const svg = `
    <svg width="960" height="540" viewBox="0 0 960 540">
      <rect x="20" y="30" width="200" height="100" fill="#112233" />
      <path d="M 100 100 L 200 100 L 200 200 Z" fill="#445566" />
      <text x="120" y="240" font-size="24" fill="#FFFFFF">Hello</text>
    </svg>
  `;
  const parsed = parseSvgElements(svg);
  assert.equal(parsed.width, 960);
  assert.equal(parsed.height, 540);
  assert.equal(parsed.elements.length >= 3, true);
});

test("svg path is converted into custom geometry points", () => {
  const points = svgPathToCustomGeometryPoints("M 0 0 L 100 0 L 100 80 Z", {
    svgWidth: 960,
    svgHeight: 540,
  });
  assert.equal(points.length >= 4, true);
  assert.deepEqual(points.at(-1), { close: true });
});

test("svg arc path command A is approximated into cubic geometry points", () => {
  const points = svgPathToCustomGeometryPoints("M 100 100 A 50 50 0 0 1 200 100 Z", {
    svgWidth: 960,
    svgHeight: 540,
  });
  const cubicPoints = points.filter((item) => item?.curve?.type === "cubic");
  assert.equal(cubicPoints.length > 0, true);
  assert.deepEqual(points.at(-1), { close: true });
});

test("svg smooth cubic command S is converted into cubic geometry points", () => {
  const points = svgPathToCustomGeometryPoints(
    "M 80 120 C 120 20 220 20 260 120 S 380 220 420 120 Z",
    { svgWidth: 960, svgHeight: 540 },
  );
  const cubicPoints = points.filter((item) => item?.curve?.type === "cubic");
  assert.equal(cubicPoints.length >= 2, true);
});

test("svg smooth quadratic command T is converted into quadratic geometry points", () => {
  const points = svgPathToCustomGeometryPoints(
    "M 80 200 Q 140 120 220 200 T 360 200 Z",
    { svgWidth: 960, svgHeight: 540 },
  );
  const quadraticPoints = points.filter((item) => item?.curve?.type === "quadratic");
  assert.equal(quadraticPoints.length >= 2, true);
});
