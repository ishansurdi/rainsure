import { describe, expect, it } from "vitest";
import { cellIndex, gridBounds, mercatorRowMap, tilePath } from "./grid";
import type { Grid, Meta } from "./types";

const G: Grid = { lat_first: 37.25, lon_first: 68.0, step_deg: 0.25, n_lat: 124, n_lon: 119 };

describe("cellIndex", () => {
  it("matches the API for Chennai and Delhi", () => {
    // api/data.py: j = round((37.25 - 13.08) / 0.25) = 97, i = round((80.27 - 68) / 0.25) = 49
    expect(cellIndex(G, 13.08, 80.27)).toEqual({ j: 97, i: 49 });
    expect(cellIndex(G, 28.61, 77.21)).toEqual({ j: 35, i: 37 });
  });
  it("returns null outside the grid", () => {
    expect(cellIndex(G, 40, 77)).toBeNull();
    expect(cellIndex(G, 20, 99)).toBeNull();
  });
  it("accepts the grid corners", () => {
    expect(cellIndex(G, 37.25, 68.0)).toEqual({ j: 0, i: 0 });
    expect(cellIndex(G, 6.5, 97.5)).toEqual({ j: 123, i: 118 });
  });
});

describe("tilePath", () => {
  it("uses 4-cell tiles", () => {
    const m = { run_id: "2026110512", tile_cells: 4 } as Meta;
    expect(tilePath(m, 97, 49)).toBe("2026110512/points/t24_12.json");
  });
});

describe("mercator resampling", () => {
  it("covers cell edges and maps the ends to the first and last rows", () => {
    expect(gridBounds(G)).toEqual({ west: 67.875, east: 97.625, north: 37.375, south: 6.375 });
    const rows = mercatorRowMap(G, 496);
    expect(rows[0]).toBe(0);
    expect(rows[495]).toBe(123);
    for (let r = 1; r < rows.length; r++) expect(rows[r]).toBeGreaterThanOrEqual(rows[r - 1]);
  });
  it("gives northern rows more output rows than southern ones (Mercator stretch)", () => {
    const rows = mercatorRowMap(G, 4960);
    const count = (j: number) => rows.filter((x) => x === j).length;
    expect(count(0)).toBeGreaterThan(count(123));
  });
});
