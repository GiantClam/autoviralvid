import test from "node:test";
import assert from "node:assert/strict";

import { getTemplatePreferredLayout } from "../minimax/templates/template-catalog.mjs";

test("template catalog returns preferred layout for known templates", () => {
  assert.equal(getTemplatePreferredLayout("bento_mosaic_dark"), "bento_5");
  assert.equal(getTemplatePreferredLayout("bento_2x2_dark"), "grid_4");
  assert.equal(getTemplatePreferredLayout("neural_blueprint_light"), "grid_4");
  assert.equal(getTemplatePreferredLayout("ops_lifecycle_light"), "timeline");
});

test("template catalog preferred layout falls back for unknown template", () => {
  assert.equal(getTemplatePreferredLayout("unknown_template", "split_2"), "split_2");
});
