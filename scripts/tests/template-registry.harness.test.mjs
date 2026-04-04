import test from "node:test";
import assert from "node:assert/strict";

import {
  assessTemplateCapabilityForSlide,
  resolveTemplateFamilyForSlide,
} from "../minimax/templates/template-registry.mjs";

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
  assert.equal(["split_media_dark", "comparison_cards_light"].includes(family), true);
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
  assert.equal(["dashboard_dark", "kpi_dashboard_dark", "ops_lifecycle_light"].includes(family), true);
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

test("template registry: kpi keyword route can select kpi dashboard family", () => {
  const family = resolveTemplateFamilyForSlide({
    sourceSlide: {
      title: "KPI dashboard trend and performance scorecard",
      content_density: "dense",
      blocks: [
        { block_type: "title", content: "KPI Dashboard" },
        { block_type: "kpi", content: "NPS 68" },
        { block_type: "chart", content: "Q1-Q4 trend" },
        { block_type: "table", content: "channel breakdown" },
      ],
    },
    requestedTemplateFamily: "auto",
    explicitType: "content",
    layoutGrid: "grid_3",
    desiredDensity: "dense",
  });
  assert.equal(family, "kpi_dashboard_dark");
});

test("template registry: image showcase keywords can select image_showcase_light", () => {
  const family = resolveTemplateFamilyForSlide({
    sourceSlide: {
      title: "Product gallery image showcase",
      blocks: [
        { block_type: "title", content: "Visual showcase" },
        { block_type: "body", content: "Three hero visuals for launch" },
        { block_type: "image", content: { url: "data:image/png;base64,aa", title: "hero" } },
      ],
    },
    requestedTemplateFamily: "auto",
    explicitType: "content",
    layoutGrid: "split_2",
    desiredDensity: "balanced",
  });
  assert.equal(family, "image_showcase_light");
});

test("template registry: process keywords can select process_flow_dark", () => {
  const family = resolveTemplateFamilyForSlide({
    sourceSlide: {
      title: "Workflow process pipeline roadmap",
      blocks: [
        { block_type: "title", content: "Process roadmap" },
        { block_type: "workflow", content: "capture -> process -> review -> ship" },
        { block_type: "list", content: "step1;step2;step3;step4" },
      ],
    },
    requestedTemplateFamily: "auto",
    explicitType: "workflow",
    layoutGrid: "timeline",
    desiredDensity: "balanced",
  });
  assert.equal(family, "process_flow_dark");
});

test("template registry: comparison keywords can select comparison_cards_light", () => {
  const family = resolveTemplateFamilyForSlide({
    sourceSlide: {
      title: "Feature comparison benchmark",
      blocks: [
        { block_type: "title", content: "Option A vs B vs C" },
        { block_type: "list", content: "cost;latency;quality" },
        { block_type: "chart", content: "comparison trend" },
      ],
    },
    requestedTemplateFamily: "auto",
    explicitType: "comparison",
    layoutGrid: "split_2",
    desiredDensity: "balanced",
  });
  assert.equal(family, "comparison_cards_light");
});

test("template registry: explicit comparison archetype biases template selection", () => {
  const family = resolveTemplateFamilyForSlide({
    sourceSlide: {
      title: "Operating model review",
      archetype: "comparison_2col",
      blocks: [
        { block_type: "title", content: "Workflow comparison" },
        { block_type: "body", content: "handoff heavy and slow" },
        { block_type: "list", content: "automated routing;faster iteration" },
      ],
    },
    requestedTemplateFamily: "auto",
    explicitType: "content",
    layoutGrid: "split_2",
  });
  assert.equal(family, "comparison_cards_light");
});

test("template registry: dashboard archetype biases toward KPI templates", () => {
  const family = resolveTemplateFamilyForSlide({
    sourceSlide: {
      title: "Quarterly KPI review",
      archetype: "dashboard_kpi_4",
      blocks: [
        { block_type: "title", content: "KPI review" },
        { block_type: "kpi", content: "ROI 132%" },
        { block_type: "chart", content: "Q1-Q4 trend" },
        { block_type: "body", content: "CAC down 17%" },
      ],
    },
    requestedTemplateFamily: "auto",
    explicitType: "content",
    layoutGrid: "grid_3",
    desiredDensity: "dense",
  });
  assert.equal(["kpi_dashboard_dark", "dashboard_dark", "ops_lifecycle_light"].includes(family), true);
});

test("template registry: quote-heavy content avoids terminal hero templates", () => {
  const family = resolveTemplateFamilyForSlide({
    sourceSlide: {
      title: "Vision quote insight",
      blocks: [
        { block_type: "title", content: "Core insight" },
        { block_type: "quote", content: "Insight drives execution." },
      ],
    },
    requestedTemplateFamily: "auto",
    explicitType: "content",
    layoutGrid: "split_2",
    desiredDensity: "sparse",
  });
  assert.equal(["quote_hero_dark", "hero_dark", "hero_tech_cover"].includes(family), false);
});

test("template registry: whitelist constrains template selection for critic-repair pages", () => {
  const family = resolveTemplateFamilyForSlide({
    sourceSlide: {
      title: "Visual similarity repair page",
      blocks: [
        { block_type: "title", content: "Repair target" },
        { block_type: "body", content: "Layout and geometry stabilization" },
      ],
      template_family_whitelist: ["split_media_dark", "consulting_warm_light"],
    },
    requestedTemplateFamily: "auto",
    explicitType: "content",
    layoutGrid: "split_2",
    desiredDensity: "balanced",
  });
  assert.equal(["split_media_dark", "consulting_warm_light"].includes(family), true);
});

test("template registry: whitelist blocks dashboard fallback when requested template not allowed", () => {
  const family = resolveTemplateFamilyForSlide({
    sourceSlide: {
      title: "Repair page with constrained templates",
      blocks: [{ block_type: "body", content: "Stabilize structure mismatch." }],
      template_candidates: ["ops_lifecycle_light", "comparison_cards_light"],
    },
    requestedTemplateFamily: "dashboard_dark",
    explicitType: "content",
    layoutGrid: "grid_3",
    desiredDensity: "balanced",
  });
  assert.equal(["ops_lifecycle_light", "comparison_cards_light"].includes(family), true);
});

test("template registry: capability assessment flags unsupported constrained blocks", () => {
  const compatibility = assessTemplateCapabilityForSlide({
    templateFamily: "bento_mosaic_dark",
    sourceSlide: {
      title: "Mismatch sample",
      blocks: [
        { block_type: "title", content: "Mismatch sample" },
        { block_type: "body", content: "Body text" },
        { block_type: "chart", content: "Q1-Q4 trend" },
      ],
    },
  });
  assert.equal(compatibility.compatible, false);
  assert.equal(compatibility.unsupported_block_types.includes("chart"), true);
});

test("template registry: capability assessment flags missing required image asset", () => {
  const compatibility = assessTemplateCapabilityForSlide({
    templateFamily: "neural_blueprint_light",
    sourceSlide: {
      title: "Image required template",
      blocks: [
        { block_type: "title", content: "Image required template" },
        { block_type: "body", content: "Workflow summary" },
        { block_type: "image", content: { title: "placeholder only" } },
      ],
    },
  });
  assert.equal(compatibility.compatible, false);
  assert.equal(compatibility.missing_required_image_asset, true);
});

test("template registry: capability assessment flags unsupported slide type", () => {
  const compatibility = assessTemplateCapabilityForSlide({
    templateFamily: "neural_blueprint_light",
    slideType: "timeline",
    layoutGrid: "timeline",
    sourceSlide: {
      title: "Timeline mismatch",
      blocks: [
        { block_type: "title", content: "Timeline mismatch" },
        { block_type: "body", content: "Roadmap snapshot" },
        { block_type: "list", content: "Phase1;Phase2;Phase3" },
      ],
    },
  });
  assert.equal(compatibility.compatible, false);
  assert.equal(compatibility.unsupported_slide_type, true);
});

test("template registry: capability assessment flags unsupported layout", () => {
  const compatibility = assessTemplateCapabilityForSlide({
    templateFamily: "dashboard_dark",
    slideType: "content",
    layoutGrid: "bento_5",
    sourceSlide: {
      title: "Layout mismatch",
      blocks: [
        { block_type: "title", content: "Layout mismatch" },
        { block_type: "body", content: "Body text" },
        { block_type: "list", content: "A;B;C" },
      ],
    },
  });
  assert.equal(compatibility.compatible, false);
  assert.equal(compatibility.unsupported_layout, true);
});
