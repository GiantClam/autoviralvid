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
