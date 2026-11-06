import { describe, expect, it } from "vitest";
import { parseState, stateToSearch } from "./url";

describe("url state", () => {
  it("round-trips place, block and layer", () => {
    const s = { lat: 13.08, lon: 80.27, name: "Chennai, Tamil Nadu", block: "2026-11-06T06", layer: "amount" as const };
    expect(parseState(stateToSearch(s))).toEqual(s);
  });
  it("defaults to the chance layer and drops invalid parts", () => {
    expect(parseState("?lat=abc&lon=80&layer=rainbow&b=tomorrow")).toEqual({
      lat: undefined, lon: undefined, name: undefined, block: undefined, layer: "chance",
    });
  });
  it("needs both coordinates", () => {
    expect(parseState("?lat=13").lat).toBeUndefined();
  });
  it("keeps the default layer out of the URL", () => {
    expect(stateToSearch({ lat: 28.61, lon: 77.21, layer: "chance" })).toBe("?lat=28.610&lon=77.210");
  });
});
