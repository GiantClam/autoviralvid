import test from "node:test";
import assert from "node:assert/strict";

import {
  buildNonStandardChartSvg,
  isNonStandardChartType,
  renderNonStandardChartInCard,
} from "../minimax/svg-chart-converter.mjs";
import { renderCard } from "../minimax/card-renderers.mjs";

function makeSlide() {
  return {
    shapeCalls: [],
    textCalls: [],
    chartCalls: [],
    addShape(type, options) {
      this.shapeCalls.push({ type, options });
    },
    addText(text, options) {
      this.textCalls.push({ text, options });
    },
    addChart(type, data, options) {
      this.chartCalls.push({ type, data, options });
    },
  };
}

test("svg chart converter marks non-standard chart types", () => {
  assert.equal(isNonStandardChartType("funnel"), true);
  assert.equal(isNonStandardChartType("waterfall"), true);
  assert.equal(isNonStandardChartType("sankey"), true);
  assert.equal(isNonStandardChartType("treemap"), true);
  assert.equal(isNonStandardChartType("heatmap"), true);
  assert.equal(isNonStandardChartType("gauge"), true);
  assert.equal(isNonStandardChartType("pyramid"), true);
  assert.equal(isNonStandardChartType("radial-gauge"), true);
  assert.equal(isNonStandardChartType("sun-burst"), true);
  assert.equal(isNonStandardChartType("geo-choropleth"), true);
  assert.equal(isNonStandardChartType("word-cloud"), true);
  assert.equal(isNonStandardChartType("bar"), false);
});

test("svg chart converter builds valid svg for funnel chart", () => {
  const svg = buildNonStandardChartSvg({
    chartType: "funnel",
    labels: ["A", "B", "C"],
    datasets: [{ data: [120, 90, 40] }],
    card: { x: 1, y: 1, w: 4, h: 2.2 },
    theme: { primary: "2F7BFF", secondary: "12B6F5", accent: "18E0D1" },
    title: "Funnel",
  });
  assert.ok(svg.startsWith("<svg"), "should return svg root");
  assert.match(svg, /<path\b/i);
  assert.match(svg, /Funnel/i);
});

test("svg chart converter renders non-standard chart into custom geometry", () => {
  const slide = makeSlide();
  const result = renderNonStandardChartInCard({
    slide,
    pptx: { shapes: { CUSTOM_GEOMETRY: "custGeom" } },
    card: { x: 1.2, y: 1.1, w: 4.8, h: 2.5 },
    theme: { primary: "2F7BFF", secondary: "12B6F5", accent: "18E0D1", darkText: "1E293B" },
    data: {
      chartType: "funnel",
      labels: ["Visit", "Lead", "Proposal", "Deal"],
      datasets: [{ label: "Pipeline", data: [300, 120, 70, 25] }],
    },
  });
  assert.equal(result.applied, true);
  assert.ok(result.customGeometryCount >= 1, "should generate custom geometry for non-standard chart");
  assert.equal(slide.chartCalls.length, 0, "non-standard chart should not call addChart");
});

test("svg chart converter builds gauge chart svg", () => {
  const svg = buildNonStandardChartSvg({
    chartType: "gauge",
    labels: ["Health"],
    datasets: [{ data: [72] }],
    card: { x: 1.2, y: 1.0, w: 4.4, h: 2.4 },
    theme: { primary: "2F7BFF", secondary: "12B6F5", accent: "18E0D1", darkText: "1E293B" },
    title: "KPI Gauge",
  });
  assert.ok(svg.startsWith("<svg"), "should return svg root");
  assert.match(svg, /KPI Gauge/i);
  assert.match(svg, /<path\b/i);
});

test("svg chart converter supports extended non-standard chart aliases", () => {
  const svg = buildNonStandardChartSvg({
    chartType: "radial-gauge",
    labels: ["Health"],
    datasets: [{ data: [72] }],
    card: { x: 1.2, y: 1.0, w: 4.4, h: 2.4 },
    theme: { primary: "2F7BFF", secondary: "12B6F5", accent: "18E0D1", darkText: "1E293B" },
    title: "Radial Gauge",
  });
  assert.ok(svg.startsWith("<svg"), "should return svg root");
  assert.match(svg, /Radial Gauge/i);
  assert.match(svg, /<path\b/i);
});

test("svg chart converter can render extended non-standard chart in card", () => {
  const slide = makeSlide();
  const result = renderNonStandardChartInCard({
    slide,
    pptx: { shapes: { CUSTOM_GEOMETRY: "custGeom" } },
    card: { x: 1.2, y: 1.1, w: 4.8, h: 2.5 },
    theme: { primary: "2F7BFF", secondary: "12B6F5", accent: "18E0D1", darkText: "1E293B" },
    data: {
      chartType: "word-cloud",
      labels: ["Revenue", "Growth", "Pipeline", "Efficiency"],
      datasets: [{ label: "WordCloud", data: [100, 80, 60, 40] }],
    },
  });
  assert.equal(result.applied, true);
  assert.equal(slide.chartCalls.length, 0, "extended non-standard chart should bypass addChart");
  assert.ok(slide.shapeCalls.length >= 1, "extended non-standard chart should emit svg-derived shapes");
  assert.equal(result.chart_type, "wordcloud");
});

test("card renderer routes funnel chart to svg converter", () => {
  const slide = makeSlide();
  renderCard({
    pptx: { shapes: { ROUNDED_RECTANGLE: "roundRect", CUSTOM_GEOMETRY: "custGeom" } },
    slide,
    card: { x: 0.8, y: 0.9, w: 4.6, h: 2.8 },
    block: {
      block_type: "chart",
      data: {
        chartType: "funnel",
        labels: ["Visit", "Lead", "Deal"],
        datasets: [{ label: "Pipeline", data: [300, 120, 42] }],
      },
    },
    theme: {
      primary: "2F7BFF",
      secondary: "12B6F5",
      accent: "18E0D1",
      darkText: "1E293B",
      borderColor: "A8BEDD",
      cardBg: "FFFFFF",
      white: "FFFFFF",
    },
    style: "soft",
  });
  assert.equal(slide.chartCalls.length, 0, "funnel chart should bypass addChart");
  assert.ok(slide.shapeCalls.length >= 2, "should render frame + svg shapes");
});

test("card renderer infers funnel chart from title keyword and routes to svg converter", () => {
  const slide = makeSlide();
  renderCard({
    pptx: { shapes: { ROUNDED_RECTANGLE: "roundRect", CUSTOM_GEOMETRY: "custGeom" } },
    slide,
    card: { x: 0.8, y: 0.9, w: 4.6, h: 2.8 },
    block: {
      block_type: "chart",
      content: { title: "Sales funnel conversion" },
      data: {
        labels: ["Visit", "Lead", "Deal"],
        datasets: [{ label: "Pipeline", data: [300, 120, 42] }],
      },
    },
    theme: {
      primary: "2F7BFF",
      secondary: "12B6F5",
      accent: "18E0D1",
      darkText: "1E293B",
      borderColor: "A8BEDD",
      cardBg: "FFFFFF",
      white: "FFFFFF",
    },
    style: "soft",
  });
  assert.equal(slide.chartCalls.length, 0, "inferred funnel should bypass addChart");
  assert.ok(slide.shapeCalls.length >= 2, "should render frame + svg shapes");
});
