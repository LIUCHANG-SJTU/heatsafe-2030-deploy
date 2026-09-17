import { describe, expect, it } from "vitest";
import { fillColorExpression, metricProperty } from "./mapStyles";

describe("map semantics", () => {
  it("maps adaptive gap without inventing a backend field", () => expect(metricProperty("adaptive_capacity_gap")).toBe("adaptive_capacity_score"));
  it("uses muted water style", () => expect(JSON.stringify(fillColorExpression("water_fraction_grid"))).toContain("#8496aa"));
  it("uses a dedicated 0-100 domain for risk score", () => {
    const expression = JSON.stringify(fillColorExpression("risk_score"));
    expect(expression).toContain("NON_URBAN_WATER");
    expect(expression).toContain(',50,');
    expect(expression).toContain(',70,');
    expect(expression).toContain(',85,');
    expect(expression).toContain(',100,');
  });
  it("keeps normalized H E V and adaptive metrics on a 0-1 domain", () => {
    for (const metric of ["hazard_score", "exposure_score", "vulnerability_score", "adaptive_capacity_gap"] as const) {
      const expression = JSON.stringify(fillColorExpression(metric));
      expect(expression).toContain(',0.5,');
      expect(expression).toContain(',1,');
      expect(expression).not.toContain(',100,');
    }
  });
  it("keeps excluded water visually distinct on every analytical layer", () => {
    for (const metric of ["risk_score", "hazard_score", "exposure_score", "vulnerability_score", "adaptive_capacity_gap", "population_total", "lst_median_c", "green_fraction_land"] as const) {
      const expression = JSON.stringify(fillColorExpression(metric));
      expect(expression).toContain("NON_URBAN_WATER");
      expect(expression).toContain("#8496aa");
    }
  });
});
