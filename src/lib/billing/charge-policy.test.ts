import { describe, expect, it } from "vitest";
import {
  buildNormalizedProxyPath,
  getGenerationChargeRules,
  resolveGenerationChargeRule,
} from "./charge-policy";

describe("billing charge policy", () => {
  it("matches project generation endpoints", () => {
    const storyboard = resolveGenerationChargeRule(
      "POST",
      "/projects/run123/storyboard",
    );
    expect(storyboard?.id).toBe("storyboard-generate");
    expect(storyboard?.units).toBe(1);

    const digitalHuman = resolveGenerationChargeRule(
      "POST",
      "/projects/run123/digital-human",
    );
    expect(digitalHuman?.id).toBe("digital-human-submit");
    expect(digitalHuman?.units).toBe(2);

    const videoRegenerate = resolveGenerationChargeRule(
      "POST",
      "/projects/run123/videos/2/regenerate",
    );
    expect(videoRegenerate?.id).toBe("video-regenerate");

    const finalRender = resolveGenerationChargeRule(
      "POST",
      "/projects/run123/render",
    );
    expect(finalRender?.id).toBe("final-render");
  });

  it("matches ppt generation endpoints", () => {
    const promptGenerate = resolveGenerationChargeRule(
      "POST",
      "/ppt/generate-from-prompt",
    );
    expect(promptGenerate?.id).toBe("ppt-prompt-generate");
    expect(promptGenerate?.units).toBe(1);

    const pptRender = resolveGenerationChargeRule("POST", "/ppt/render");
    expect(pptRender?.id).toBe("ppt-video-render");
  });

  it("does not match non-chargeable requests", () => {
    const getStatus = resolveGenerationChargeRule("GET", "/projects/run123/status");
    const unknown = resolveGenerationChargeRule("POST", "/projects/run123");
    expect(getStatus).toBeNull();
    expect(unknown).toBeNull();
  });

  it("builds normalized proxy paths with optional prefixes", () => {
    expect(buildNormalizedProxyPath(["generate-from-prompt"], ["ppt"])).toBe(
      "/ppt/generate-from-prompt",
    );
    expect(buildNormalizedProxyPath(["projects", "abc", "videos"], [])).toBe(
      "/projects/abc/videos",
    );
  });

  it("keeps a stable non-empty rule set", () => {
    expect(getGenerationChargeRules().length).toBeGreaterThan(0);
  });
});
