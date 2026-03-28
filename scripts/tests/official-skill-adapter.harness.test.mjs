import test from "node:test";
import assert from "node:assert/strict";

import {
  fromOfficialOutput,
  toOfficialInput,
} from "../minimax/official_skill_adapter.mjs";

test("official adapter: maps internal payload to official schema", () => {
  const internal = {
    title: "灵创智能",
    author: "AutoViralVid",
    generator_mode: "official",
    slides: [
      {
        slide_id: "s1",
        title: "灵创智能",
        slide_type: "cover",
        elements: [{ block_id: "b1", type: "text", content: "AI营销与数字人" }],
      },
    ],
  };

  const official = toOfficialInput(internal);
  assert.equal(official.generator_mode, "official");
  assert.equal(official.slides.length, 1);
  assert.equal(official.slides[0].page_type, "cover");
  assert.equal(official.theme.primary.length, 6);
});

test("official adapter: maps official output to internal retry-friendly schema", () => {
  const officialOutput = {
    deck_id: "deck-1",
    generator_mode: "official",
    retry_scope: "slide",
    slides: [
      {
        slide_id: "s1",
        page_type: "content",
        title: "灵创智能",
        blocks: [{ block_id: "b1", type: "text", content: "数字人营销闭环" }],
      },
    ],
  };

  const internal = fromOfficialOutput(officialOutput);
  assert.equal(internal.deck_id, "deck-1");
  assert.equal(internal.slides.length, 1);
  assert.equal(internal.slides[0].slide_id, "s1");
  assert.equal(internal.slides[0].elements[0].block_id, "b1");
  assert.equal(internal.slides[0].retry_scope, "slide");
});

test("official adapter: maps blocks to official input when elements are missing", () => {
  const internal = {
    title: "Blocks First Deck",
    generator_mode: "official",
    slides: [
      {
        slide_id: "s-blocks",
        slide_type: "content",
        title: "Growth Trend",
        blocks: [
          {
            block_type: "chart",
            card_id: "trend",
            content: "Revenue growth",
            data: {
              labels: ["2024", "2025E"],
              datasets: [{ label: "Revenue", data: [100, 128] }],
            },
          },
        ],
      },
    ],
  };

  const official = toOfficialInput(internal);
  assert.equal(official.slides.length, 1);
  assert.equal(official.slides[0].page_type, "content");
  assert.equal(
    official.slides[0].blocks.length > 0,
    true,
    "content slide blocks should not be dropped when elements are missing",
  );
});
