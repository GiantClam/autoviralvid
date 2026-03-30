export const SUPPORTED_CHART_TYPES = [
  "bar",
  "bar3d",
  "line",
  "pie",
  "doughnut",
  "area",
  "radar",
  "scatter",
];

export const NON_STANDARD_CHART_TYPES = [
  "funnel",
  "waterfall",
  "sankey",
  "treemap",
  "heatmap",
  "gauge",
  "pyramid",
  "sunburst",
  "radialbar",
  "rose",
  "radar_area",
  "bubble_map",
  "choropleth",
  "marimekko",
  "mekko",
  "boxplot",
  "violin",
  "candlestick",
  "wordcloud",
  "network",
  "alluvial",
  "streamgraph",
  "bullet",
  "variance",
  "pareto",
];

export const CHART_TYPE_ALIASES = {
  column: "bar",
  columns: "bar",
  "clustered-column": "bar",
  "stacked-column": "bar",
  "100-stacked-column": "bar",
  "clustered-bar": "bar",
  "stacked-bar": "bar",
  "100-stacked-bar": "bar",
  histogram: "bar",
  "stacked_column": "bar",
  progress: "bar",
  "3d-bar": "bar3d",
  "3d-column": "bar3d",
  trend: "line",
  spline: "line",
  "step-line": "line",
  "dual-axis": "line",
  combo: "line",
  "combo-line": "line",
  "combo-column-line": "line",
  "stacked-area": "area",
  "100-stacked-area": "area",
  sparkline: "line",
  donut: "doughnut",
  ring: "doughnut",
  polar: "radar",
  "polar-chart": "radar",
  "polar-area": "radar",
  "radar-area": "radar",
  bubble: "scatter",
  bubbles: "scatter",
  "scatter-plot": "scatter",
  scatterplot: "scatter",
  funnel: "funnel",
  "funnel-chart": "funnel",
  waterfall: "waterfall",
  "waterfall-chart": "waterfall",
  sankey: "sankey",
  "sankey-chart": "sankey",
  treemap: "treemap",
  "tree-map": "treemap",
  heatmap: "heatmap",
  "heat-map": "heatmap",
  gauge: "gauge",
  "semi-gauge": "gauge",
  speedometer: "gauge",
  pyramid: "pyramid",
  "pyramid-chart": "pyramid",
  sunburst: "sunburst",
  "sun-burst": "sunburst",
  radialbar: "radialbar",
  "radial-bar": "radialbar",
  "radial-gauge": "radialbar",
  rose: "rose",
  "rose-chart": "rose",
  "nightingale-rose": "rose",
  "radar-area": "radar_area",
  radararea: "radar_area",
  "filled-radar": "radar_area",
  "bubble-map": "bubble_map",
  bubblemap: "bubble_map",
  geoplot: "bubble_map",
  choropleth: "choropleth",
  "geo-choropleth": "choropleth",
  map: "choropleth",
  marimekko: "marimekko",
  mekko: "mekko",
  mosaic: "mekko",
  boxplot: "boxplot",
  "box-plot": "boxplot",
  whisker: "boxplot",
  violin: "violin",
  candlestick: "candlestick",
  candle: "candlestick",
  kline: "candlestick",
  wordcloud: "wordcloud",
  "word-cloud": "wordcloud",
  network: "network",
  graph: "network",
  nodegraph: "network",
  alluvial: "alluvial",
  streamgraph: "streamgraph",
  "stream-graph": "streamgraph",
  bullet: "bullet",
  variance: "variance",
  "variance-chart": "variance",
  pareto: "pareto",
};

function normalizeChartTypeKey(input) {
  return String(input || "")
    .trim()
    .toLowerCase()
    .replace(/[\s_]+/g, "-");
}

export function normalizeChartType(input) {
  const key = normalizeChartTypeKey(input);
  if (!key) return "";
  if (CHART_TYPE_ALIASES[key]) return CHART_TYPE_ALIASES[key];
  return key;
}

export function listSupportedChartSemanticTypes() {
  const set = new Set([
    ...SUPPORTED_CHART_TYPES,
    ...NON_STANDARD_CHART_TYPES,
    ...Object.keys(CHART_TYPE_ALIASES),
  ]);
  return Array.from(set).sort();
}

function inferChartTypeByTitle(title) {
  const text = String(title || "").trim().toLowerCase();
  if (!text) return "";
  if (/funnel/.test(text)) return "funnel";
  if (/waterfall/.test(text)) return "waterfall";
  if (/sankey/.test(text)) return "sankey";
  if (/(treemap|tree\s*map)/.test(text)) return "treemap";
  if (/(heatmap|heat\s*map)/.test(text)) return "heatmap";
  if (/(gauge|speedometer)/.test(text)) return "gauge";
  if (/pyramid/.test(text)) return "pyramid";
  if (/sunburst/.test(text)) return "sunburst";
  if (/(radial\s*bar|radial\s*gauge)/.test(text)) return "radialbar";
  if (/(rose\s*chart|nightingale|coxcomb)/.test(text)) return "rose";
  if (/(radar\s*area|filled\s*radar)/.test(text)) return "radar_area";
  if (/(bubble\s*map|geo\s*bubble|map\s*bubble)/.test(text)) return "bubble_map";
  if (/(choropleth|geo\s*map|heat\s*map\s*by\s*region)/.test(text)) return "choropleth";
  if (/(marimekko|mekko|mosaic)/.test(text)) return "marimekko";
  if (/(box\s*plot|boxplot|whisker)/.test(text)) return "boxplot";
  if (/violin/.test(text)) return "violin";
  if (/(candlestick|kline|ohlc)/.test(text)) return "candlestick";
  if (/(word\s*cloud|tag\s*cloud)/.test(text)) return "wordcloud";
  if (/(network|node\s*graph|relationship\s*graph)/.test(text)) return "network";
  if (/alluvial/.test(text)) return "alluvial";
  if (/stream\s*graph/.test(text)) return "streamgraph";
  if (/bullet/.test(text)) return "bullet";
  if (/variance/.test(text)) return "variance";
  if (/pareto/.test(text)) return "pareto";
  if (/pie/.test(text)) return "pie";
  if (/trend/.test(text)) return "line";
  if (/radar/.test(text)) return "radar";
  if (/scatter/.test(text)) return "scatter";
  if (/area/.test(text)) return "area";
  return "";
}

export function inferChartTypeFromBlock(block = {}) {
  const data = block?.data && typeof block.data === "object" ? block.data : {};
  const content = block?.content && typeof block.content === "object" ? block.content : {};
  const requested = normalizeChartType(data.chartType || data.type || content.chartType || content.type || "");
  if (requested) return requested;

  const title = String(content.title || block?.title || "").trim();
  const fromTitle = inferChartTypeByTitle(title);
  if (fromTitle) return fromTitle;

  const labels = Array.isArray(data.labels) ? data.labels : [];
  const datasets = Array.isArray(data.datasets) ? data.datasets : [];
  if (datasets.length === 1 && labels.length <= 3) return "pie";
  if (datasets.length >= 2 && labels.length >= 4) return "line";
  return "bar";
}

export function safeChartType(input) {
  const key = normalizeChartType(input);
  if (SUPPORTED_CHART_TYPES.includes(key)) return key;
  return "bar";
}

export function resolveChartEnum(pptx, chartType) {
  const safeType = safeChartType(chartType);
  const upper = safeType.toUpperCase();
  const lower = safeType.toLowerCase();
  const viaChartType =
    pptx?.ChartType?.[safeType]
    || pptx?.ChartType?.[upper]
    || pptx?.ChartType?.[lower];
  if (viaChartType) return viaChartType;
  const viaLegacyCharts =
    pptx?.charts?.[upper]
    || pptx?.charts?.[safeType]
    || pptx?.charts?.[lower];
  if (viaLegacyCharts) return viaLegacyCharts;
  // Modern PptxGenJS accepts string chart types directly ("bar", "line", ...).
  return safeType;
}

function isPieLike(chartType) {
  const t = safeChartType(chartType);
  return t === "pie" || t === "doughnut";
}

function validateDatasets(datasets) {
  if (!Array.isArray(datasets) || datasets.length === 0) return false;
  return datasets.every((item) => Array.isArray(item?.values) && item.values.length > 0);
}

function validateChartContract(datasets) {
  if (!validateDatasets(datasets)) return false;
  return datasets.every((series) => Array.isArray(series.labels) && series.labels.length === series.values.length);
}

export function createChart(slide, pptx, chartType, datasets, options = {}, theme = {}) {
  if (!slide || typeof slide.addChart !== "function") return false;
  if (!validateChartContract(datasets)) {
    const err = new Error("chart contract invalid: labels/datasets mismatch");
    err.code = "chart_data_missing";
    throw err;
  }

  const safeType = safeChartType(chartType);
  const chartEnum = resolveChartEnum(pptx, safeType);
  const textColor = theme.darkText || "E8F0FF";
  const gridColor = theme.borderColor || theme.light || "1E335E";
  const palette = [
    theme.primary || "2F7BFF",
    theme.secondary || "12B6F5",
    theme.accent || "18E0D1",
    "6EA8FF",
    "2B4E8D",
  ];
  const merged = {
    showLegend: true,
    legendPos: "b",
    legendFontSize: 9,
    legendColor: textColor,
    showValue: true,
    catAxisLabelFontSize: 9,
    catAxisLabelColor: textColor,
    valAxisLabelFontSize: 9,
    valAxisLabelColor: textColor,
    dataLabelFontSize: 8,
    dataLabelColor: textColor,
    catAxisLineColor: gridColor,
    valAxisLineColor: gridColor,
    catAxisMajorUnit: 1,
    catAxisMajorTickMark: "none",
    valAxisMajorGridLine: { color: gridColor, pt: 0.6 },
    chartColors: palette,
    valAxisHidden: isPieLike(safeType),
    ...options,
  };
  slide.addChart(chartEnum, datasets, merged);
  return true;
}
