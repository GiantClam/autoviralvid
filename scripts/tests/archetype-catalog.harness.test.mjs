import test from "node:test";
import assert from "node:assert/strict";

import { listArchetypes, resolveSlideArchetype } from "../minimax/templates/archetype-catalog.mjs";

test("archetype catalog exposes at least 16 archetypes", () => {
  const archetypes = listArchetypes();
  assert.equal(archetypes.length >= 16, true);
});

test("archetype resolver prefers semantic and layout overrides", () => {
  assert.equal(
    resolveSlideArchetype({ pageRole: "content", layoutGrid: "timeline", semanticType: "workflow" }),
    "process_flow_4step",
  );
  assert.equal(
    resolveSlideArchetype({ pageRole: "content", layoutGrid: "grid_4", semanticType: "" }),
    "dashboard_kpi_4",
  );
  assert.equal(
    resolveSlideArchetype({ pageRole: "summary", layoutGrid: "hero_1", semanticType: "" }),
    "cover_hero",
  );
});
