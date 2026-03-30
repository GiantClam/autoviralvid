import {
  createChart,
  inferChartTypeFromBlock,
  NON_STANDARD_CHART_TYPES,
  SUPPORTED_CHART_TYPES,
  listSupportedChartSemanticTypes,
  normalizeChartType,
} from "../minimax/chart-factory.mjs";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function makeSlide() {
  return {
    calls: [],
    addChart(type, data, options) {
      this.calls.push({ type, data, options });
    },
  };
}

const fakePptx = {
  charts: {
    BAR: "BAR",
    BAR3D: "BAR3D",
    LINE: "LINE",
    PIE: "PIE",
    DOUGHNUT: "DOUGHNUT",
    AREA: "AREA",
    RADAR: "RADAR",
    SCATTER: "SCATTER",
  },
};

const baseDataset = [{ name: "S1", labels: ["A", "B"], values: [10, 20] }];
const types = ["bar", "bar3d", "line", "pie", "doughnut", "area", "radar", "scatter"];

for (const t of types) {
  const slide = makeSlide();
  const ok = createChart(slide, fakePptx, t, baseDataset, { x: 1, y: 1, w: 2, h: 2 }, {});
  assert(ok, `createChart should succeed for ${t}`);
  assert(slide.calls.length === 1, `addChart should be called for ${t}`);
  assert(slide.calls[0].type === t.toUpperCase(), `chart enum should map for ${t}`);
}

{
  const slide = makeSlide();
  const ok = createChart(slide, fakePptx, "unknown", baseDataset, {}, {});
  assert(ok, "unknown type should fallback to bar");
  assert(slide.calls[0].type === "BAR", "unknown chart type should map to BAR");
}

{
  const slide = makeSlide();
  const ok = createChart(slide, fakePptx, "column", baseDataset, {}, {});
  assert(ok, "semantic alias column should fallback to bar");
  assert(slide.calls[0].type === "BAR", "column alias should map to BAR");
}

{
  const slide = makeSlide();
  const ok = createChart(slide, {}, "bar", baseDataset, {}, {});
  assert(ok, "should support runtime without enum maps");
  assert(slide.calls[0].type === "bar", "runtime fallback should pass string chart type");
}

{
  const slide = makeSlide();
  createChart(slide, fakePptx, "pie", baseDataset, {}, {});
  assert(slide.calls[0].options.valAxisHidden === true, "pie should hide value axis");
}

{
  const slide = makeSlide();
  createChart(slide, fakePptx, "line", baseDataset, {}, {});
  assert(slide.calls[0].options.valAxisHidden === false, "line should keep value axis");
}

{
  const slide = makeSlide();
  let caught = null;
  try {
    createChart(slide, fakePptx, "bar", [], {}, {});
  } catch (err) {
    caught = err;
  }
  assert(caught && caught.code === "chart_data_missing", "empty datasets should raise chart_data_missing");
}

{
  const inferred = inferChartTypeFromBlock({
    content: { title: "Revenue trend by quarter" },
    data: { labels: ["Q1", "Q2", "Q3"], datasets: [{ data: [10, 20, 30] }] },
  });
  assert(inferred === "line", "title keyword trend should infer line chart");
}

{
  const inferred = inferChartTypeFromBlock({
    content: { title: "Conversion funnel overview" },
    data: { labels: ["Visit", "Signup", "Pay"], datasets: [{ data: [100, 40, 10] }] },
  });
  assert(inferred === "funnel", "title keyword funnel should infer non-standard funnel chart");
}

{
  assert(SUPPORTED_CHART_TYPES.length >= 7, "standard chart coverage should be >= 7");
  assert(NON_STANDARD_CHART_TYPES.length >= 25, "non-standard chart coverage should be >= 25");
  const realTypeCoverage = new Set([...SUPPORTED_CHART_TYPES, ...NON_STANDARD_CHART_TYPES]).size;
  assert(realTypeCoverage >= 33, "real chart type coverage should be >= 33");
}

{
  const semanticTypes = listSupportedChartSemanticTypes();
  assert(semanticTypes.length >= 60, "chart semantic type coverage should be >= 60");
}

{
  assert(normalizeChartType("gauge") === "gauge", "gauge should normalize to non-standard gauge chart");
  const inferred = inferChartTypeFromBlock({
    data: {
      chartType: "waterfall-chart",
      labels: ["Revenue", "Cost", "Net"],
      datasets: [{ data: [100, -30, 70] }],
    },
  });
  assert(inferred === "waterfall", "waterfall alias should infer non-standard waterfall chart");
}

{
  const inferred = inferChartTypeFromBlock({
    content: { title: "Market segment treemap" },
    data: { labels: ["A", "B", "C"], datasets: [{ data: [35, 28, 19] }] },
  });
  assert(inferred === "treemap", "title keyword treemap should infer non-standard treemap chart");
}

{
  assert(normalizeChartType("radial-gauge") === "radialbar", "radial-gauge alias should normalize to radialbar");
  assert(normalizeChartType("geo-choropleth") === "choropleth", "geo-choropleth alias should normalize to choropleth");
  assert(normalizeChartType("word-cloud") === "wordcloud", "word-cloud alias should normalize to wordcloud");
}

{
  const inferred = inferChartTypeFromBlock({
    content: { title: "Regional choropleth map" },
    data: { labels: ["华东", "华南", "华北"], datasets: [{ data: [38, 26, 21] }] },
  });
  assert(inferred === "choropleth", "title keyword choropleth should infer choropleth chart");
}

{
  const inferred = inferChartTypeFromBlock({
    content: { title: "Quarterly candlestick trend" },
    data: { labels: ["Q1", "Q2", "Q3"], datasets: [{ data: [10, 14, 12] }] },
  });
  assert(inferred === "candlestick", "title keyword candlestick should infer candlestick chart");
}

console.log("chart-factory harness passed");
