import { renderBentoSlide, renderCard } from "../minimax/card-renderers.mjs";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function makeFakeSlide() {
  return {
    shapes: [],
    texts: [],
    charts: [],
    addShape(type, options) {
      this.shapes.push({ type, options });
    },
    addText(text, options) {
      this.texts.push({ text, options });
    },
    addChart(type, data, options) {
      this.charts.push({ type, data, options });
    },
  };
}

const fakePptx = {
  shapes: { ROUNDED_RECTANGLE: "ROUNDED_RECTANGLE", OVAL: "OVAL", LINE: "LINE" },
  charts: { BAR: "BAR" },
};

const fakeTheme = {
  primary: "2563EB",
  secondary: "64748B",
  accent: "0EA5E9",
  light: "E2E8F0",
  darkText: "1E293B",
  white: "FFFFFF",
  bg: "FFFFFF",
};

{
  const slide = makeFakeSlide();
  let caught = null;
  try {
    renderCard({
      pptx: fakePptx,
      slide,
      card: { x: 1, y: 1, w: 3, h: 2 },
      block: { block_type: "kpi", data: { number: 120 } },
      theme: fakeTheme,
      style: "soft",
    });
  } catch (err) {
    caught = err;
  }
  assert(caught && caught.code === "kpi_data_missing", "kpi should require number/unit/trend");
}

{
  const slide = makeFakeSlide();
  const ok = renderBentoSlide({
    pptx: fakePptx,
    slide,
    theme: fakeTheme,
    style: "soft",
    sourceSlide: {
      layout_grid: "timeline",
      blocks: [{ block_type: "text", content: "timeline content" }],
      timeline_items: [
        { label: "Q1", description: "Kickoff" },
        { label: "Q2", description: "Build" },
        { label: "Q3", description: "Pilot" },
        { label: "Q4", description: "Scale" },
        { label: "Q5", description: "Optimize" },
        { label: "Q6", description: "Extra" },
      ],
    },
  });
  assert(ok, "timeline slide should render successfully");
  const labelCount = slide.texts.filter((item) => /^Q[1-6]$/.test(String(item.text))).length;
  assert(labelCount === 5, "timeline should render at most 5 items");
}

{
  const slide = makeFakeSlide();
  const ok = renderBentoSlide({
    pptx: fakePptx,
    slide,
    theme: fakeTheme,
    style: "soft",
    sourceSlide: {
      layout_grid: "timeline",
      blocks: [{ block_type: "text", content: "Start;Build;Scale" }],
      timeline_items: [],
    },
  });
  assert(ok, "timeline should fallback from block content when timeline_items missing");
}

console.log("kpi-timeline harness passed");
