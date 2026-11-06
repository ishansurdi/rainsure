import type { Grid, Meta } from "./types";

/** Nearest grid cell (row j north->south, column i west->east), or null outside the grid. Same rule as api/data.py. */
export function cellIndex(g: Grid, lat: number, lon: number): { j: number; i: number } | null {
  const j = Math.round((g.lat_first - lat) / g.step_deg);
  const i = Math.round((lon - g.lon_first) / g.step_deg);
  if (j < 0 || j >= g.n_lat || i < 0 || i >= g.n_lon) return null;
  return { j, i };
}

/** Centre of a grid cell in degrees. */
export function cellCentre(g: Grid, j: number, i: number): { lat: number; lon: number } {
  return { lat: g.lat_first - j * g.step_deg, lon: g.lon_first + i * g.step_deg };
}

/** Path of the point tile holding cell (j, i), relative to the data root. */
export function tilePath(m: Meta, j: number, i: number): string {
  return `${m.run_id}/points/t${Math.floor(j / m.tile_cells)}_${Math.floor(i / m.tile_cells)}.json`;
}

/** Outer edges of the grid (cell centres +- half a step), for placing the rain image on the map. */
export function gridBounds(g: Grid): { west: number; east: number; north: number; south: number } {
  const h = g.step_deg / 2;
  return {
    west: g.lon_first - h,
    east: g.lon_first + (g.n_lon - 1) * g.step_deg + h,
    north: g.lat_first + h,
    south: g.lat_first - (g.n_lat - 1) * g.step_deg - h,
  };
}

/** Web Mercator y (unitless) of a latitude in degrees. */
export function mercY(latDeg: number): number {
  const r = (latDeg * Math.PI) / 180;
  return Math.log(Math.tan(Math.PI / 4 + r / 2));
}

/**
 * Grid row for each output row of an image that is uniform in Mercator y between the grid's north and south edges.
 * The map stretches images linearly in Mercator space, so a lat/lon grid must be resampled this way or cells shift.
 */
export function mercatorRowMap(g: Grid, outRows: number): Int32Array {
  const b = gridBounds(g);
  const yN = mercY(b.north), yS = mercY(b.south);
  const rows = new Int32Array(outRows);
  for (let r = 0; r < outRows; r++) {
    const y = yN + ((r + 0.5) / outRows) * (yS - yN);
    const lat = (2 * Math.atan(Math.exp(y)) - Math.PI / 2) * (180 / Math.PI);
    rows[r] = Math.min(g.n_lat - 1, Math.max(0, Math.round((g.lat_first - lat) / g.step_deg)));
  }
  return rows;
}
