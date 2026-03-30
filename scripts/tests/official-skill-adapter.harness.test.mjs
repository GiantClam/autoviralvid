import test from "node:test";
import assert from "node:assert/strict";

import {
  fromOfficialOutput,
  toOfficialInput,
} from "../minimax/official_skill_adapter.mjs";
import {
  validateOfficialInputContract,
} from "../minimax/official_skill_contract.mjs";

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

test("official adapter: preserves layout/subtype hints in unified contract", () => {
  const internal = {
    title: "Layout Hints Deck",
    author: "AutoViralVid",
    generator_mode: "official",
    slides: [
      {
        slide_id: "s-cover",
        title: "Cover",
        slide_type: "cover",
        elements: [{ block_id: "bc", type: "text", content: "Deck opener" }],
      },
      {
        slide_id: "s-layout",
        title: "Market Dynamics",
        slide_type: "grid_3",
        elements: [{ block_id: "b1", type: "text", content: "Signal A" }],
      },
      {
        slide_id: "s-timeline",
        title: "Roadmap",
        subtype: "timeline",
        elements: [{ block_id: "b2", type: "text", content: "Milestone 1" }],
      },
    ],
  };

  const official = toOfficialInput(internal);
  assert.equal(official.slides[1].page_type, "content");
  assert.equal(official.slides[1].layout_grid, "grid_3");
  assert.equal(official.slides[1].subtype, "grid_3");
  assert.equal(official.slides[2].subtype, "timeline");
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

test("official adapter: preserves visual block image url metadata", () => {
  const internal = {
    title: "Image Deck",
    generator_mode: "official",
    slides: [
      {
        slide_id: "s-image",
        slide_type: "content",
        title: "Factory",
        blocks: [
          {
            block_type: "image",
            card_id: "img1",
            content: { title: "Factory floor", url: "https://example.com/factory.png" },
          },
        ],
      },
    ],
  };
  const official = toOfficialInput(internal);
  assert.equal(official.slides.length, 1);
  assert.equal(official.slides[0].blocks.length, 1);
  assert.equal(official.slides[0].blocks[0].type, "image");
  assert.equal(official.slides[0].blocks[0].data?.url, "https://example.com/factory.png");
});

test("official adapter: strips supporting-point prefix from content lines", () => {
  const internal = {
    title: "Prefix Deck",
    generator_mode: "official",
    slides: [
      {
        slide_id: "s-prefix",
        slide_type: "content",
        title: "Roadmap",
        elements: [
          { block_id: "b1", type: "text", content: "补充要点：阶段一完成需求澄清" },
          { block_id: "b2", type: "text", content: "Supporting point: Stage two validates design" },
        ],
      },
    ],
  };
  const official = toOfficialInput(internal);
  const lines = (official.slides[0].blocks || []).map((item) => String(item.content || ""));
  assert.equal(lines.some((line) => /^补充要点|^Supporting point/i.test(line)), false);
});

test("official adapter: does not force fallback Slide N title when official output title is missing", () => {
  const officialOutput = {
    generator_mode: "official",
    retry_scope: "slide",
    slides: [
      {
        slide_id: "s1",
        page_type: "content",
        blocks: [{ block_id: "b1", type: "body", content: "Point A" }],
      },
    ],
  };
  const internal = fromOfficialOutput(officialOutput);
  assert.equal(internal.slides.length, 1);
  assert.equal(internal.slides[0].title, "");
});

test("official contract: validates and normalizes official input", () => {
  const draft = {
    title: "Contract Deck",
    author: "AutoViralVid",
    generator_mode: "unknown",
    retry_scope: "unknown",
    slides: [
      {
        slide_id: "s1",
        page_type: "content",
        title: "Content",
        blocks: [{ type: "body", content: "Point A" }],
      },
    ],
  };
  const result = validateOfficialInputContract(draft);
  assert.equal(result.ok, true);
  assert.equal(result.normalized.generator_mode, "official");
  assert.equal(result.normalized.retry_scope, "deck");
  assert.equal(result.normalized.slides[0].blocks.length, 1);
});

test("official contract: rejects empty slides", () => {
  const result = validateOfficialInputContract({ title: "X", author: "Y", slides: [] });
  assert.equal(result.ok, false);
  assert.equal(result.errors.some((item) => String(item).includes("slides")), true);
});

test("official adapter: throws when required contract is violated", () => {
  assert.throws(
    () => toOfficialInput({ title: "No slides", author: "X", slides: [] }),
    /official_input_contract_invalid/,
  );
});
