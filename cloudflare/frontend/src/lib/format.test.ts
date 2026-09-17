import { describe, expect, it } from "vitest";
import { driverLabel, formatGridLabel, formatPercent, formatPopulation, formatScore, sourceComponentLabel } from "./format";

describe("format helpers", () => {
  it("formats real values and nulls", () => {
    expect(formatPopulation(244915.6)).toBe("244,916");
    expect(formatScore(89.199)).toBe("89.2");
    expect(formatPercent(0.1822)).toBe("18.2%");
    expect(formatPopulation(null)).toBe("—");
  });
  it("maps only supported drivers", () => {
    expect(driverLabel("hazard", "zh-CN")).toBe("热危险度");
    expect(driverLabel("hazard", "en")).toBe("Heat Hazard");
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
  it("presents source component identifiers as product labels", () => {
    expect(sourceComponentLabel("LANDSAT_9", "zh-CN")).toBe("Landsat 9 地表温度");
    expect(sourceComponentLabel("SENTINEL_2", "en")).toBe("Sentinel-2 Land Cover");
  });
  it("shows a human-readable grid label while retaining unknown IDs", () => {
    expect(formatGridLabel("M4B-R-5EEC8B7710-G-R16-C13", "zh-CN")).toBe("格网 R16-C13");
    expect(formatGridLabel("M4B-R-5EEC8B7710-G-R16-C13", "en")).toBe("Grid R16-C13");
    expect(formatGridLabel("GRID-1", "zh-CN")).toBe("GRID-1");
  });
});
