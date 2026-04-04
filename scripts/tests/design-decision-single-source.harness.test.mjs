import test from "node:test";
import assert from "node:assert/strict";

import { resolveDisableLocalStyleRewritePolicy } from "../minimax/design-decision-policy.mjs";

test("generator policy: design_decision_v1 forces single source for style rewrite", () => {
  assert.equal(
    resolveDisableLocalStyleRewritePolicy({
      requestedDisableLocalStyleRewrite: false,
      deckDecision: {
        style_variant: "rounded",
        palette_key: "platinum_white_gold",
      },
    }),
    true,
  );

  assert.equal(
    resolveDisableLocalStyleRewritePolicy({
      requestedDisableLocalStyleRewrite: false,
      deckDecision: {},
    }),
    false,
  );

  assert.equal(
    resolveDisableLocalStyleRewritePolicy({
      requestedDisableLocalStyleRewrite: true,
      deckDecision: {},
    }),
    true,
  );
});
