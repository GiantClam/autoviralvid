import { normalizeKey } from "../minimax-style-heuristics.mjs";

function normalizeAutoText(value) {
  const text = String(value || "").trim();
  const normalized = normalizeKey(text);
  if (!text) return "";
  if (normalized === "auto" || normalized === "none" || normalized === "null" || normalized === "undefined") return "";
  return text;
}

export function resolveDisableLocalStyleRewritePolicy({
  requestedDisableLocalStyleRewrite = false,
  deckDecision = {},
} = {}) {
  const read = (key) => normalizeAutoText(deckDecision?.[key]);
  return Boolean(
    requestedDisableLocalStyleRewrite
    || read("style_variant")
    || read("palette_key")
    || read("theme_recipe")
    || read("tone"),
  );
}
