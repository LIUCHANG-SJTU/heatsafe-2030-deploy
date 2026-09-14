import { describe, expect, it } from "vitest";
import { driverLabel, formatPercent, formatPopulation, formatScore, sourceComponentLabel } from "./format";

describe("format helpers", () => {
  it("formats real values and nulls", () => {
    expect(formatPopulation(244915.6)).toBe("244,916");
    expect(formatScore(89.199)).toBe("89.2");
    expect(formatPercent(0.1822)).toBe("18.2%");
    expect(formatPopulation(null)).toBe("—");
  });
  it("maps only supported drivers", () => {
    expect(driverLabel("hazard", "zh-CN")).toBe("热危险度主导");
    expect(driverLabel("hazard", "en")).toBe("Hazard dominant");
    expect(driverLabel("Composite")).toBe("—");
  });
  it("formats population using the requested locale", () => {
    expect(formatPopulation(1234.4, "zh-CN")).toBe("1,234");
    expect(formatPopulation(1234.4, "en")).toBe("1,234");
  });
  it("uses formal product wording for the analysis repository", () => {
    expect(sourceComponentLabel("DEMO_REPOSITORY", "zh-CN")).toBe("HeatSafe 数据仓库");
    expect(sourceComponentLabel("DEMO_REPOSITORY", "en")).toBe("HeatSafe Data Repository");
  });
});
