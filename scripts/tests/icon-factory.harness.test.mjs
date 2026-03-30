import test from "node:test";
import assert from "node:assert/strict";

import {
  getIconLibraryStats,
  renderIconDataForPptx,
  renderIconSvgMarkup,
  resolveIconName,
} from "../minimax/icon-factory.mjs";

test("icon factory resolves icon name by explicit alias and keyword", () => {
  assert.equal(resolveIconName({ icon: "FiTarget" }), "FiTarget");
  assert.equal(resolveIconName({ icon: "MdOutlineSecurity" }), "MdOutlineSecurity");
  assert.equal(resolveIconName({ icon: "growth" }), "arrow-trend-up");
  assert.equal(resolveIconName({ title: "Risk control plan" }), "triangle-exclamation");
});

test("icon factory resolves ppt-master explicit icon names", () => {
  assert.equal(resolveIconName({ icon: "rocket" }), "rocket");
  assert.equal(resolveIconName({ title: "Rocket launch plan" }), "rocket");
});

test("icon factory resolves chinese semantic keywords to ppt-master icons", () => {
  assert.equal(resolveIconName({ title: "增长策略" }), "arrow-trend-up");
  assert.equal(resolveIconName({ title: "风险预警机制" }), "triangle-exclamation");
  assert.equal(resolveIconName({ title: "流程优化方案" }), "route");
  assert.equal(resolveIconName({ title: "目标达成路径" }), "target-arrow");
});

test("icon factory falls back to default icon for unknown tokens", () => {
  assert.equal(resolveIconName({ icon: "unknown_icon_foo" }), "FiCircle");
});

test("icon factory renders svg markup and pptx image payload", () => {
  const svg = renderIconSvgMarkup({ icon: "FiUsers", size: 42, color: "12B6F5" });
  assert.match(svg, /<svg/i);
  assert.match(svg, /stroke=/i);
  const payload = renderIconDataForPptx({ icon: "FiUsers", size: 42, color: "12B6F5" });
  assert.match(payload, /^image\/png;base64,/);
  assert.ok(payload.length > 80);
});

test("icon factory renders ppt-master svg icon and png payload", () => {
  const svg = renderIconSvgMarkup({ icon: "rocket", size: 48, color: "12B6F5" });
  assert.match(svg, /<svg/i);
  assert.match(svg, /viewBox="0 0 16 16"/i);
  assert.match(svg, /fill="#12B6F5"/i);
  const payload = renderIconDataForPptx({ icon: "rocket", size: 48, color: "12B6F5" });
  assert.match(payload, /^image\/png;base64,/);
  assert.ok(payload.length > 80);
});

test("icon factory exposes 4000+ icon library scale with multi-pack react-icons", () => {
  const stats = getIconLibraryStats();
  assert.ok(Number(stats.react_pack_count) >= 5);
  assert.ok(Number(stats.react_icon_count) >= 4000);
  assert.ok(Number(stats.total_icon_count) >= 4500);
});
