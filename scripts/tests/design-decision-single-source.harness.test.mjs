import test from "node:test";
import assert from "node:assert/strict";

import { resolveDisableLocalStyleRewritePolicy } from "../minimax/design-decision-policy.mjs";

function requestedVisualInputs({
  rawRequestedStyle = "auto",
  rawRequestedPalette = "auto",
  rawRequestedThemeRecipe = "auto",
  rawRequestedTone = "auto",
  deckDecision = {},
} = {}) {
  const normalize = (value) => {
    const text = String(value || "").trim();
    if (!text) return "";
    const normalized = text.toLowerCase();
    return ["auto", "none", "null", "undefined"].includes(normalized) ? "" : text;
  };
  return {
    style: normalize(deckDecision.style_variant) || normalize(rawRequestedStyle) || "auto",
    palette: normalize(deckDecision.palette_key) || normalize(rawRequestedPalette) || "auto",
    themeRecipe: normalize(deckDecision.theme_recipe) || normalize(rawRequestedThemeRecipe) || "auto",
    tone: normalize(deckDecision.tone) || normalize(rawRequestedTone) || "auto",
  };
}

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

test("generator policy: design_decision_v1 wins over raw visual inputs", () => {
  assert.deepEqual(
    requestedVisualInputs({
      rawRequestedStyle: "rounded",
      rawRequestedPalette: "business_authority",
      rawRequestedThemeRecipe: "editorial_magazine",
      rawRequestedTone: "dark",
      deckDecision: {
        style_variant: "sharp",
        palette_key: "pure_tech_blue",
        theme_recipe: "classroom_soft",
        tone: "light",
      },
    }),
    {
      style: "sharp",
      palette: "pure_tech_blue",
      themeRecipe: "classroom_soft",
      tone: "light",
    },
  );
});
