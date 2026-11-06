import { describe, expect, it } from "vitest";
import { indiaView } from "./basemap";
import type { StyleSpecification } from "maplibre-gl";

const style = {
  version: 8, sources: {},
  layers: [
    { id: "boundary_2", type: "line", source: "openmaptiles", "source-layer": "boundary" },
    { id: "boundary_disputed", type: "line", source: "openmaptiles", "source-layer": "boundary" },
    { id: "label_state", type: "symbol", source: "openmaptiles", "source-layer": "place", filter: ["==", ["get", "class"], "state"] },
    { id: "label_city", type: "symbol", source: "openmaptiles", "source-layer": "place", layout: { "text-font": ["Noto Sans Bold"], "text-size": 12 } },
    { id: "waterway_label", type: "symbol", source: "openmaptiles", "source-layer": "waterway" },
  ],
} as unknown as StyleSpecification;

describe("indiaView", () => {
  const out = indiaView(style);
  it("removes every OpenFreeMap border layer", () => {
    expect(out.layers.map((l) => l.id)).toEqual(["label_state", "label_city", "waterway_label"]);
  });
  it("keeps the original filter and adds the disputed-name filter to place labels only", () => {
    const f = JSON.stringify((out.layers[0] as { filter: unknown }).filter);
    expect(f.startsWith('["all",["==",["get","class"],"state"],["!",["any"')).toBe(true);
    expect(f).toContain("Azad Kashmir");
    expect(f).toContain("Gilgit-Baltistan");
    expect(JSON.stringify((out.layers[1] as { filter: unknown }).filter).startsWith('["!",')).toBe(true);
    expect((out.layers[2] as { filter?: unknown }).filter).toBeUndefined();
  });
  it("uses one label font and keeps the rest of the layout", () => {
    expect((out.layers[1] as { layout: unknown }).layout).toEqual({ "text-font": ["Noto Sans Regular"], "text-size": 12 });
  });
});
