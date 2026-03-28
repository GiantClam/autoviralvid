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

export function safeChartType(input) {
  const key = String(input || "").trim().toLowerCase();
  if (SUPPORTED_CHART_TYPES.includes(key)) return key;
  return "bar";
}

export function resolveChartEnum(pptx, chartType) {
  const key = safeChartType(chartType).toUpperCase();
  return pptx?.charts?.[key] || pptx?.charts?.BAR;
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
