import { createChart } from "../minimax/chart-factory.mjs";

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

console.log("chart-factory harness passed");
