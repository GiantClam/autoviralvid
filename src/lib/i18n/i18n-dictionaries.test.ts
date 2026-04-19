import { describe, expect, it } from "vitest";
import en from "./en";
import zh from "./zh";

function flatten(
  value: Record<string, unknown>,
  prefix = "",
  target: Record<string, string> = {},
) {
  for (const [key, entry] of Object.entries(value)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (entry && typeof entry === "object" && !Array.isArray(entry)) {
      flatten(entry as Record<string, unknown>, path, target);
      continue;
    }
    target[path] = String(entry);
  }
  return target;
}

describe("i18n dictionaries", () => {
  it("keeps zh and en key sets aligned", () => {
    const enFlat = flatten(en as unknown as Record<string, unknown>);
    const zhFlat = flatten(zh as unknown as Record<string, unknown>);

    expect(Object.keys(enFlat).sort()).toEqual(Object.keys(zhFlat).sort());
  });

  it("keeps critical project-page copy defined", () => {
    expect(typeof zh.common.loading).toBe("string");
    expect(typeof zh.language.zh).toBe("string");
    expect(typeof zh.assistant.title).toBe("string");
    expect(en.clips.renderVideo).toBe("Render Video");
  });
});
