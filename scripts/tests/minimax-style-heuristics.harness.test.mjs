import test from "node:test";
import assert from "node:assert/strict";
import {
  inferSubtype,
  selectPalette,
  selectStyle,
} from "../minimax-style-heuristics.mjs";

const ZH_ENTERPRISE = "\u7075\u521b\u667a\u80fd \u4f01\u4e1a\u4ecb\u7ecd \u516c\u53f8\u6982\u51b5";
const ZH_BRAND = "\u54c1\u724c\u8425\u9500";
const ZH_EDU = "\u8bfe\u7a0b\u8bbe\u8ba1\u4e0e\u6559\u5b66\u8bc4\u4f30";
const ZH_EDU_CHART = "\u6559\u80b2\u8bfe\u7a0b chart";
const ZH_TECH = "ai cloud \u79d1\u6280\u8def\u7ebf";
const ZH_SECTION = "\u7b2c\u4e00\u90e8\u5206\uff1a\u516c\u53f8\u6218\u7565";
const ZH_COMPARE = "\u65b9\u6848\u5bf9\u6bd4";
const ZH_TIMELINE = "\u8def\u7ebf\u56fe\u4e0e\u9636\u6bb5\u76ee\u6807";
const ZH_DATA = "\u6570\u636e";
const ZH_TABLE = "\u8868\u683c";
const ZH_CASE = "\u6848\u4f8b\u5c55\u793a";
const ZH_NORMAL = "\u666e\u901a\u5185\u5bb9\u9875";

test("style harness: explicit style wins", () => {
  assert.equal(selectStyle("pill", "", ZH_ENTERPRISE), "pill");
  assert.equal(selectStyle("sharp", "", "creative marketing"), "sharp");
});

test("style harness: style hint overrides topic auto", () => {
  assert.equal(selectStyle("auto", "creative", ZH_ENTERPRISE), "pill");
  assert.equal(selectStyle("auto", "education", ZH_ENTERPRISE), "rounded");
  assert.equal(selectStyle("auto", "professional", ZH_BRAND), "soft");
});

test("style harness: chinese and english topic keywords", () => {
  assert.equal(selectStyle("auto", "", ZH_ENTERPRISE), "sharp");
  assert.equal(selectStyle("auto", "", "Q3 finance report"), "sharp");
  assert.equal(selectStyle("auto", "", ZH_EDU), "rounded");
  assert.equal(selectStyle("auto", "", "brand fashion campaign"), "pill");
  assert.equal(selectStyle("auto", "", "random neutral topic"), "soft");
});

test("style harness: preserve original disables topic rewrite", () => {
  assert.equal(selectStyle("auto", "creative", ZH_ENTERPRISE, true), "soft");
  assert.equal(selectPalette("auto", ZH_TECH, true), "business_authority");
});

test("palette harness: explicit palette wins", () => {
  assert.equal(selectPalette("pure_tech_blue", ZH_ENTERPRISE), "pure_tech_blue");
  assert.equal(selectPalette("business_authority", "education"), "business_authority");
});

test("palette harness: topic keyword routing", () => {
  assert.equal(selectPalette("auto", ZH_ENTERPRISE), "business_authority");
  assert.equal(selectPalette("auto", "finance quarterly analysis"), "business_authority");
  assert.equal(selectPalette("auto", "health wellness plan"), "modern_wellness");
  assert.equal(selectPalette("auto", ZH_EDU_CHART), "education_charts");
  assert.equal(selectPalette("auto", "forest eco esg"), "forest_eco");
  assert.equal(selectPalette("auto", "high-end luxury premium"), "platinum_white_gold");
  assert.equal(selectPalette("auto", ZH_TECH), "pure_tech_blue");
  assert.equal(selectPalette("auto", "unclassified topic"), "luxury_mysterious");
});

test("subtype harness: explicit subtype normalization", () => {
  assert.equal(inferSubtype({ slide_type: "table", title: "x" }), "table");
  assert.equal(inferSubtype({ subtype: "summary", title: "x" }), "content");
  assert.equal(inferSubtype({ slideType: "comparison", title: "x" }), "comparison");
});

test("subtype harness: title and elements inference", () => {
  assert.equal(inferSubtype({ title: ZH_SECTION }), "section");
  assert.equal(inferSubtype({ title: ZH_COMPARE }), "comparison");
  assert.equal(inferSubtype({ title: ZH_TIMELINE }), "timeline");
  assert.equal(inferSubtype({ title: ZH_DATA, elements: [{ type: "chart" }] }), "data_visualization");
  assert.equal(inferSubtype({ title: ZH_TABLE, elements: [{ type: "table" }] }), "table");
  assert.equal(inferSubtype({ title: ZH_CASE, elements: [{ type: "image" }] }), "image_showcase");
  assert.equal(inferSubtype({ title: ZH_NORMAL, elements: [{ type: "text" }] }), "content");
});

test("subtype harness: infer from blocks when elements are missing", () => {
  assert.equal(
    inferSubtype({
      title: "Growth Snapshot",
      blocks: [{ block_type: "chart", content: "Revenue trend" }],
    }),
    "data_visualization",
  );
});
