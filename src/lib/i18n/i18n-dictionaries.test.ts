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

  it("keeps critical project-page copy readable", () => {
    expect(zh.common.loading).toBe("加载中...");
    expect(zh.language.zh).toBe("中文");
    expect(zh.assistant.title).toBe("AI 创意助手");
    expect(zh.workspace.pptV7WorkspaceTitle).toBe("PPT V7 工作台");
    expect(en.gallery.tplPptV7Desc).toContain("Dual-agent PPT generation");
    expect(en.clips.renderVideo).toBe("Render Video");
  });
});
