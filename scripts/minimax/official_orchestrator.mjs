import { toOfficialInput } from "./official_skill_adapter.mjs";
import { normalizeGeneratorMode } from "./official_skill_contract.mjs";

function asBool(...candidates) {
  for (const candidate of candidates) {
    if (typeof candidate === "boolean") return candidate;
    if (typeof candidate === "string") {
      const normalized = candidate.trim().toLowerCase();
      if (["1", "true", "yes", "on"].includes(normalized)) return true;
      if (["0", "false", "no", "off"].includes(normalized)) return false;
    }
    if (typeof candidate === "number") return candidate !== 0;
  }
  return false;
}

export function resolveOfficialPlan({
  payload,
  cliValues,
  originalStyle,
  disableLocalStyleRewrite,
  retryScope,
}) {
  const requestedMode =
    cliValues?.["generator-mode"] ?? payload?.generator_mode ?? "official";
  const generatorMode = normalizeGeneratorMode(requestedMode, "official");
  const preserveOriginal = asBool(originalStyle, payload?.original_style, false);
  const disableRewrite = asBool(
    disableLocalStyleRewrite,
    payload?.disable_local_style_rewrite,
    false,
  );

  const officialInput = toOfficialInput({
    ...(payload || {}),
    generator_mode: generatorMode,
    original_style: preserveOriginal,
    disable_local_style_rewrite: disableRewrite,
    retry_scope: retryScope,
  });

  return {
    generatorMode,
    preserveOriginal,
    disableLocalStyleRewrite: disableRewrite,
    officialInput,
  };
}
