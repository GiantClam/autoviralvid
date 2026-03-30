import test from "node:test";
import assert from "node:assert/strict";

import { getTemplateCatalog } from "../minimax/templates/template-catalog.mjs";
import {
  hasTemplateContentRenderer,
  hasTemplateCoverRenderer,
  listTemplateContentRenderers,
  listTemplateCoverRenderers,
} from "../minimax/templates/template-renderers.mjs";

const CONTENT_LIKE_SLIDE_TYPES = new Set([
  "content",
  "data",
  "comparison",
  "workflow",
  "timeline",
  "showcase",
]);

const GENERIC_COVER_TEMPLATES = new Set([
  "hero_dark",
]);

test("template renderer ids must all exist in catalog", () => {
  const catalog = getTemplateCatalog();
  const templateIds = new Set(Object.keys(catalog?.templates || {}));
  for (const id of listTemplateContentRenderers()) {
    assert.equal(templateIds.has(id), true, `content renderer template missing in catalog: ${id}`);
  }
  for (const id of listTemplateCoverRenderers()) {
    assert.equal(templateIds.has(id), true, `cover renderer template missing in catalog: ${id}`);
  }
});

test("content-capable templates should have content renderer coverage", () => {
  const catalog = getTemplateCatalog();
  const templates = catalog?.templates && typeof catalog.templates === "object" ? catalog.templates : {};
  for (const [templateId, templateDef] of Object.entries(templates)) {
    const slideTypes = Array.isArray(templateDef?.capabilities?.supported_slide_types)
      ? templateDef.capabilities.supported_slide_types.map((item) => String(item || "").trim().toLowerCase())
      : [];
    const isContentCapable = slideTypes.some((item) => CONTENT_LIKE_SLIDE_TYPES.has(item));
    if (!isContentCapable) continue;
    assert.equal(
      hasTemplateContentRenderer(templateId),
      true,
      `content-capable template missing content renderer: ${templateId}`,
    );
  }
});

test("cover-capable templates should have cover renderer or explicit generic allowance", () => {
  const catalog = getTemplateCatalog();
  const templates = catalog?.templates && typeof catalog.templates === "object" ? catalog.templates : {};
  for (const [templateId, templateDef] of Object.entries(templates)) {
    const slideTypes = Array.isArray(templateDef?.capabilities?.supported_slide_types)
      ? templateDef.capabilities.supported_slide_types.map((item) => String(item || "").trim().toLowerCase())
      : [];
    if (!slideTypes.includes("cover")) continue;
    const covered = hasTemplateCoverRenderer(templateId) || GENERIC_COVER_TEMPLATES.has(templateId);
    assert.equal(
      covered,
      true,
      `cover-capable template missing cover renderer (or generic allowance): ${templateId}`,
    );
  }
});

test("template coverage meets S5 target thresholds", () => {
  const catalog = getTemplateCatalog();
  const templates = catalog?.templates && typeof catalog.templates === "object" ? catalog.templates : {};
  const templateCount = Object.keys(templates).length;
  const contentRendererCount = listTemplateContentRenderers().length;
  assert.ok(templateCount >= 12, `catalog templates should be >= 12, got ${templateCount}`);
  assert.ok(contentRendererCount >= 12, `content renderers should be >= 12, got ${contentRendererCount}`);
});
