import { normalizeRenderInput, validateRenderInput } from "../minimax/render-contract.mjs";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const basePayload = normalizeRenderInput({
  title: "Contract Test",
  theme: { palette: "slate_minimal", style: "soft" },
  slides: [
    {
      page_number: 1,
      slide_type: "content",
      layout_grid: "split_2",
      contract_profile: "default",
      blocks: [
        { block_type: "title", card_id: "title", content: "Core value" },
        { block_type: "body", card_id: "body", content: "Efficiency +80%", emphasis: ["80%"] },
        { block_type: "list", card_id: "list", content: "Evidence A;Evidence B" },
        { block_type: "image", card_id: "image", content: { title: "Diagram", url: "image/png;base64,AA==" } },
      ],
    },
  ],
});

{
  const result = validateRenderInput(basePayload);
  assert(result.ok, `base payload should pass, got: ${result.errors?.join("; ")}`);
  assert(basePayload.presentation_contract_v2, "presentation_contract_v2 should be generated");
  assert(Array.isArray(basePayload.presentation_contract_v2.slides), "contract slides should be array");
  assert(basePayload.presentation_contract_v2.slides.length === 1, "contract slides length should match");
  assert(basePayload.slides[0].archetype, "slide archetype should be assigned");
  assert(basePayload.slides[0].archetype_plan && typeof basePayload.slides[0].archetype_plan === "object", "slide archetype_plan should be assigned");
  assert(basePayload.slides[0].page_role === "content", "content page role expected");
  assert(basePayload.theme_recipe, "theme_recipe should be normalized");
  assert(basePayload.tone, "tone should be normalized");
  assert(basePayload.slides[0].theme_recipe, "slide theme_recipe should be normalized");
  assert(basePayload.slides[0].tone, "slide tone should be normalized");
  const row = basePayload.presentation_contract_v2.slides[0];
  assert(row.archetype_plan && typeof row.archetype_plan === "object", "row archetype_plan should exist");
  assert(row.archetype_plan.selected === row.archetype, "archetype_plan.selected should match row archetype");
  assert(Array.isArray(row.archetype_plan.candidates) && row.archetype_plan.candidates.length > 0, "archetype candidates required");
  assert(row.content_channel && typeof row.content_channel === "object", "content_channel should exist");
  assert(row.visual_channel && typeof row.visual_channel === "object", "visual_channel should exist");
  assert(row.visual_channel.layout === row.layout_grid, "visual_channel.layout should mirror layout_grid");
  assert(row.visual_channel.render_path === row.render_path, "visual_channel.render_path should mirror render_path");
  assert(row.semantic_constraints && typeof row.semantic_constraints === "object", "semantic constraints required");
  assert(typeof row.semantic_constraints.media_required === "boolean", "media_required should be boolean");
  assert(typeof row.semantic_constraints.chart_required === "boolean", "chart_required should be boolean");
  assert(typeof row.semantic_constraints.diagram_type === "string", "diagram_type should be string");
}

{
  const payload = normalizeRenderInput({
    title: "Layout Hint",
    slides: [
      {
        page_number: 1,
        slide_type: "grid_4",
        blocks: [{ block_type: "body", card_id: "b1", content: "Signal 1" }],
      },
    ],
  });
  assert(payload.slides[0].layout_grid === "grid_4", "layout_grid should inherit from slide_type hint");
  assert(payload.slides[0].archetype === "dashboard_kpi_4", "grid_4 should map to dashboard archetype");
}

{
  const payload = JSON.parse(JSON.stringify(basePayload));
  payload.slides[0].contract_profile = "default";
  payload.slides[0].blocks = [
    { block_type: "title", card_id: "title", content: "Title" },
    { block_type: "body", card_id: "left", content: "Core fact 32%", emphasis: ["32%"] },
    { block_type: "list", card_id: "right", content: "Evidence A;Evidence B" },
  ];
  const result = validateRenderInput(payload);
  assert(result.ok, `default contract should allow no visual anchor, got: ${result.errors?.join("; ")}`);
}

{
  const payload = JSON.parse(JSON.stringify(basePayload));
  payload.slides[0].contract_profile = "visual_anchor_required";
  payload.slides[0].blocks = [
    { block_type: "title", card_id: "title", content: "Title" },
    { block_type: "body", card_id: "left", content: "Core fact 32%", emphasis: ["32%"] },
    { block_type: "list", card_id: "right", content: "Evidence A;Evidence B" },
  ];
  const result = validateRenderInput(payload);
  assert(!result.ok, "visual_anchor_required should reject non-visual slides");
  assert(
    result.errors.some((msg) => msg.includes("visual anchor")),
    `expected visual anchor error, got: ${result.errors?.join("; ")}`,
  );
}

{
  const payload = JSON.parse(JSON.stringify(basePayload));
  delete payload.presentation_contract_v2.slides[0].semantic_constraints.diagram_type;
  const result = validateRenderInput(payload);
  assert(!result.ok, "missing semantic_constraints.diagram_type should fail");
  assert(
    result.errors.some((msg) => msg.includes("semantic_constraints.diagram_type")),
    `expected semantic constraint error, got: ${result.errors?.join("; ")}`,
  );
}

{
  const payload = JSON.parse(JSON.stringify(basePayload));
  payload.slides[0].blocks[1].content = "same text";
  payload.slides[0].blocks.push({ block_type: "list", card_id: "list", content: "same text" });
  const result = validateRenderInput(payload);
  assert(!result.ok, "duplicate text payload should fail");
  assert(
    result.errors.some((msg) => msg.includes("duplicate")),
    `expected duplicate error, got: ${result.errors?.join("; ")}`,
  );
}

{
  const payload = JSON.parse(JSON.stringify(basePayload));
  payload.slides[0].blocks = [
    { block_type: "title", card_id: "title", content: "Title" },
    { block_type: "body", card_id: "body", content: "alpha beta gamma" },
    { block_type: "image", card_id: "image", content: { title: "Diagram", url: "image/png;base64,AA==" } },
  ];
  const result = validateRenderInput(payload);
  assert(!result.ok, "weak emphasis payload should fail");
  assert(
    result.errors.some((msg) => msg.includes("emphasis signal")),
    `expected emphasis error, got: ${result.errors?.join("; ")}`,
  );
}

console.log("render-contract harness passed");
