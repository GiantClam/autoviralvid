import { describe, expect, it } from "vitest";
import { getPlanCatalog } from "./plan-catalog";

describe("plan catalog", () => {
  it("contains required base plans", () => {
    const catalog = getPlanCatalog();
    expect(catalog.free.code).toBe("free");
    expect(catalog.pro.code).toBe("pro");
    expect(catalog.enterprise.code).toBe("enterprise");
  });

  it("ensures free plan has finite default quota", () => {
    const catalog = getPlanCatalog();
    expect(catalog.free.quotaTotal).toBeGreaterThan(0);
  });
});

