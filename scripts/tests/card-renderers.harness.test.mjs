import { canRenderBentoSlide, renderBentoSlide, renderCard } from "../minimax/card-renderers.mjs";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function makeFakeSlide() {
  return {
    shapes: [],
    texts: [],
    charts: [],
    tables: [],
    images: [],
    addShape(type, options) {
      this.shapes.push({ type, options });
    },
    addText(text, options) {
      this.texts.push({ text, options });
    },
    addChart(type, data, options) {
      this.charts.push({ type, data, options });
    },
    addTable(rows, options) {
      this.tables.push({ rows, options });
    },
    addImage(options) {
      this.images.push(options);
    },
  };
}

const fakePptx = {
  shapes: { ROUNDED_RECTANGLE: "ROUNDED_RECTANGLE" },
  charts: { BAR: "BAR" },
};

const fakeTheme = {
  primary: "2563EB",
  secondary: "64748B",
  accent: "0EA5E9",
  light: "E2E8F0",
  darkText: "1E293B",
  white: "FFFFFF",
};

{
  const slide = makeFakeSlide();
  renderCard({
    pptx: fakePptx,
    slide,
    card: { x: 1, y: 1, w: 3, h: 2 },
    block: { block_type: "text", content: "Hello Bento" },
    theme: fakeTheme,
    style: "soft",
  });
  assert(slide.shapes.length > 0, "renderCard should add card frame");
  assert(slide.texts.length > 0, "renderCard should add text");
}

{
  const sourceSlide = {
    layout_grid: "split_2",
    blocks: [
      { block_type: "kpi", card_id: "left", data: { number: 120, unit: "%", trend: 12 } },
      {
        block_type: "chart",
        card_id: "right",
        data: {
          labels: ["A", "B", "C"],
          datasets: [{ label: "Series 1", data: [30, 45, 60] }],
        },
      },
    ],
  };
  assert(canRenderBentoSlide(sourceSlide), "split_2 slide with blocks should be renderable");
  const slide = makeFakeSlide();
  const ok = renderBentoSlide({
    pptx: fakePptx,
    slide,
    sourceSlide,
    theme: fakeTheme,
    style: "soft",
  });
  assert(ok, "renderBentoSlide should return true");
  assert(slide.shapes.length >= 2, "bento renderer should draw at least two cards");
}

{
  const sourceSlide = {
    layout_grid: "split_2",
    blocks: [
      { block_type: "title", card_id: "title", content: "增长总览" },
      { block_type: "body", card_id: "left", content: "A" },
      { block_type: "list", card_id: "left", content: "A;B" },
      { block_type: "body", card_id: "right", content: "C" },
      { block_type: "list", card_id: "right", content: "C;D" },
    ],
  };
  const slide = makeFakeSlide();
  const ok = renderBentoSlide({
    pptx: fakePptx,
    slide,
    sourceSlide,
    theme: fakeTheme,
    style: "soft",
  });
  assert(ok, "duplicate-card slide should render");
  const frameCount = slide.shapes.filter((shape) => shape.type === "ROUNDED_RECTANGLE").length;
  assert(frameCount === 2, `each split slot should render once, got frameCount=${frameCount}`);
}

{
  const sourceSlide = {
    layout_grid: "hero_1",
    blocks: [
      {
        block_type: "table",
        card_id: "main",
        data: {
          headers: ["Metric", "Value", "Change"],
          rows: [
            ["Revenue", 1200, "12%"],
            ["Cost", 320, "-3%"],
          ],
        },
      },
    ],
  };
  const slide = makeFakeSlide();
  const ok = renderBentoSlide({
    pptx: fakePptx,
    slide,
    sourceSlide,
    theme: fakeTheme,
    style: "soft",
  });
  assert(ok, "table bento slide should render");
  assert(slide.tables.length === 1, "table block should render addTable");
}

{
  const slide = makeFakeSlide();
  renderCard({
    pptx: fakePptx,
    slide,
    card: { x: 1, y: 1, w: 3, h: 2 },
    block: { block_type: "image", content: { title: "Missing image" } },
    theme: fakeTheme,
    style: "soft",
  });
  assert(slide.images.length >= 1 || slide.texts.length >= 1, "image block without url should use placeholder");
}

console.log("card-renderers harness passed");
