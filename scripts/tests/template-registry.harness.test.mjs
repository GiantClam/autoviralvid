import test from "node:test";
import assert from "node:assert/strict";

import { resolveTemplateFamilyForSlide } from "../minimax/templates/template-registry.mjs";

test("template registry: weak orchestration keyword should not force architecture template", () => {
  const family = resolveTemplateFamilyForSlide({
    sourceSlide: {
      title: "AI orchestration overview",
      blocks: [{ block_type: "body", content: "Product highlights" }],
    },
    requestedTemplateFamily: "auto",
    explicitType: "content",
    layoutGrid: "split_2",
  });
  assert.equal(family, "split_media_dark");
});

test("template registry: strong architecture signal should select architecture template", () => {
  const family = resolveTemplateFamilyForSlide({
    sourceSlide: {
      title: "Orchestration sandbox workflow engine",
      blocks: [
        { block_type: "body", content: "dsl orchestration workflow engine" },
        { block_type: "workflow", content: "planner -> executor -> validator" },
      ],
    },
    requestedTemplateFamily: "auto",
    explicitType: "content",
    layoutGrid: "split_2",
  });
  assert.equal(family, "architecture_dark_panel");
});

test("template registry: mixed deck should not collapse to one architecture family", () => {
  const slides = [
    {
      sourceSlide: { title: "AI orchestration overview", blocks: [{ block_type: "body", content: "Intro" }] },
      explicitType: "content",
      layoutGrid: "split_2",
    },
    {
      sourceSlide: { title: "Growth metrics", blocks: [{ block_type: "chart", content: "Trend" }] },
      explicitType: "content",
      layoutGrid: "grid_3",
    },
    {
      sourceSlide: { title: "Implementation roadmap", blocks: [{ block_type: "list", content: "Step 1;Step 2" }] },
      explicitType: "content",
      layoutGrid: "timeline",
    },
  ];
  const families = slides.map((slide) =>
    resolveTemplateFamilyForSlide({
      ...slide,
      requestedTemplateFamily: "auto",
    }),
  );
  assert.equal(families.every((family) => family === "architecture_dark_panel"), false);
  assert.ok(new Set(families).size >= 2);
});

test("template registry: dense data slide prefers data-capable template", () => {
  const family = resolveTemplateFamilyForSlide({
    sourceSlide: {
      title: "Quarterly KPI review",
      content_density: "dense",
      blocks: [
        { block_type: "title", content: "KPI snapshot" },
        { block_type: "kpi", content: "ROI 132%" },
        { block_type: "chart", content: "Q1-Q4 trend" },
        { block_type: "table", content: "channel breakdown" },
      ],
    },
    requestedTemplateFamily: "auto",
    explicitType: "content",
    layoutGrid: "grid_3",
    desiredDensity: "dense",
  });
  assert.equal(["dashboard_dark", "ops_lifecycle_light"].includes(family), true);
});

test("template registry: no image asset should avoid image-required templates", () => {
  const family = resolveTemplateFamilyForSlide({
    sourceSlide: {
      title: "Workflow platform overview",
      blocks: [
        { block_type: "title", content: "Platform overview" },
        { block_type: "body", content: "Orchestration and observability" },
        { block_type: "list", content: "Planner;Executor;Guardrail" },
        { block_type: "image", content: { title: "visual intent only" } },
      ],
    },
    requestedTemplateFamily: "auto",
    explicitType: "content",
    layoutGrid: "split_2",
  });
  assert.equal(["neural_blueprint_light", "consulting_warm_light"].includes(family), false);
});
