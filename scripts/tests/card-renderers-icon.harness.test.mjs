import test from "node:test";
import assert from "node:assert/strict";

import { renderCard } from "../minimax/card-renderers.mjs";

function makeSlide(withImage = true) {
  const calls = {
    shape: [],
    text: [],
    image: [],
  };
  const slide = {
    addShape(type, options) {
      calls.shape.push({ type, options });
    },
    addText(text, options) {
      calls.text.push({ text, options });
    },
  };
  if (withImage) {
    slide.addImage = (options) => {
      calls.image.push(options);
    };
  }
  return { slide, calls };
}

const baseTheme = {
  primary: "2F7BFF",
  darkText: "1E293B",
  cardBg: "FFFFFF",
  borderColor: "D9E2F2",
  white: "FFFFFF",
};

test("card renderer uses icon factory for icon_text blocks", () => {
  const { slide, calls } = makeSlide(true);
  renderCard({
    pptx: { shapes: { ROUNDED_RECTANGLE: "roundRect" } },
    slide,
    card: { x: 1.1, y: 1.0, w: 3.8, h: 1.8 },
    block: {
      block_type: "icon_text",
      content: {
        icon: "growth",
        title: "增长动能",
        body: "保持高增速并优化获客结构。",
      },
    },
    theme: baseTheme,
    style: "soft",
  });
  assert.equal(calls.shape.length, 1, "card frame should be rendered");
  assert.equal(calls.image.length, 1, "icon should be rendered as image");
  assert.match(String(calls.image[0]?.data || ""), /^image\/png;base64,/);
  assert.ok(calls.text.length >= 2, "title and body text should be rendered");
});

test("card renderer icon_text degrades to text when addImage is unavailable", () => {
  const { slide, calls } = makeSlide(false);
  renderCard({
    pptx: { shapes: { ROUNDED_RECTANGLE: "roundRect" } },
    slide,
    card: { x: 1.1, y: 1.0, w: 3.8, h: 1.8 },
    block: {
      block_type: "icon_text",
      content: "流程效率提升与风险前置",
    },
    theme: baseTheme,
    style: "soft",
  });
  assert.equal(calls.image.length, 0, "no image call without addImage capability");
  assert.ok(calls.text.length >= 1, "text fallback should still render");
});

test("card renderer infers icon from chinese title when icon is missing", () => {
  const { slide, calls } = makeSlide(true);
  renderCard({
    pptx: { shapes: { ROUNDED_RECTANGLE: "roundRect" } },
    slide,
    card: { x: 1.1, y: 1.0, w: 3.8, h: 1.8 },
    block: {
      block_type: "icon_text",
      content: {
        title: "风险预警",
        body: "建立多层风险识别与处置流程",
      },
    },
    theme: baseTheme,
    style: "soft",
  });
  assert.equal(calls.shape.length, 1, "card frame should be rendered");
  assert.equal(calls.image.length, 1, "icon should be inferred and rendered");
  assert.match(String(calls.image[0]?.data || ""), /^image\/png;base64,/);
});
