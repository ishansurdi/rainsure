// MapLibre map: OpenFreeMap basemap without its borders, our India-POV borders, and the rain image on top.
// MapLibre is loaded with a dynamic import so the answer sheet never waits for it (D62).
import type { ImageSource, Map as MLMap, Marker, StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
// MapLibre 6 looks for its worker next to its own module file, which bundlers move; ship the worker as an asset.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { indiaView } from "./basemap";
import { STYLE_URL } from "./config";
import { gridBounds, mercatorRowMap } from "./grid";
import type { Grid } from "./types";

const ROWS_PER_CELL = 4;
let rowMap: Int32Array | null = null;
let lib: typeof import("maplibre-gl") | null = null;

/** Load MapLibre and the style once `after` settles (the answer's data first on slow links, D62). */
export function preloadMap(after: Promise<unknown>): { lib: Promise<typeof import("maplibre-gl")>; style: Promise<StyleSpecification> } {
  const go = after.catch(() => undefined);
  return {
    lib: go.then(() => import("maplibre-gl")).then((m) => (lib = m)),
    style: go.then(() => fetch(STYLE_URL)).then((r) => r.json() as Promise<StyleSpecification>),
  };
}

/** Create the map, opening directly at `center`/`zoom` when the place is already known (one set of tiles). */
export async function createMap(container: string, pre: ReturnType<typeof preloadMap>, center: [number, number],
  zoom: number): Promise<MLMap> {
  const [ml, style] = await Promise.all([pre.lib, pre.style]);
  ml.setWorkerUrl(new URL(workerUrl, location.href).href);
  const map = new ml.Map({
    container, style: indiaView(style), center, zoom, minZoom: 3, maxZoom: 11,
    attributionControl: { compact: true }, dragRotate: false, pitchWithRotate: false,
  });
  map.touchZoomRotate.disableRotation();
  await new Promise<void>((ok) => map.once("load", () => ok()));
  const base = import.meta.env.BASE_URL;
  const firstLabel = map.getStyle().layers.find((l: { type: string }) => l.type === "symbol")?.id;
  map.addSource("rain", { type: "image", url: transparentPng(), coordinates: [[0, 1], [1, 1], [1, 0], [0, 0]] });
  map.addLayer({ id: "rain", type: "raster", source: "rain", paint: { "raster-resampling": "nearest", "raster-fade-duration": 0 } }, firstLabel);
  map.addSource("borders", { type: "geojson", data: `${base}geo/borders.json` });
  map.addSource("india", { type: "geojson", data: `${base}geo/india.json` });
  map.addLayer({ id: "borders", type: "line", source: "borders", paint: { "line-color": "#6b645a", "line-width": 0.8 } }, firstLabel);
  map.addLayer({ id: "india", type: "line", source: "india", paint: { "line-color": "#22201c", "line-width": 1.3 } }, firstLabel);
  return map;
}

/** A marker element at lon/lat (MapLibre must already be loaded). */
export function makeMarker(map: MLMap, el: HTMLElement, lon: number, lat: number): Marker | null {
  return lib ? new lib.Marker({ element: el }).setLngLat([lon, lat]).addTo(map) : null;
}

function transparentPng(): string {
  const c = document.createElement("canvas");
  c.width = c.height = 1;
  return c.toDataURL();
}

/** Draw RGBA pixels (from layers.paintSlot) over the grid, stretched in Mercator space. */
export function showRain(map: MLMap, g: Grid, rgba: Uint8ClampedArray | null): void {
  const src = map.getSource("rain") as ImageSource | undefined;
  if (!src) return;
  const b = gridBounds(g);
  const coords: [[number, number], [number, number], [number, number], [number, number]] =
    [[b.west, b.north], [b.east, b.north], [b.east, b.south], [b.west, b.south]];
  if (!rgba) { src.updateImage({ url: transparentPng(), coordinates: coords }); return; }
  const c = document.createElement("canvas");
  c.width = g.n_lon;
  c.height = g.n_lat * ROWS_PER_CELL;
  c.getContext("2d")!.putImageData(new ImageData(rgba as unknown as Uint8ClampedArray<ArrayBuffer>, c.width, c.height), 0, 0);
  src.updateImage({ url: c.toDataURL(), coordinates: coords });
}

export function rowsFor(g: Grid): Int32Array {
  rowMap ??= mercatorRowMap(g, g.n_lat * ROWS_PER_CELL);
  return rowMap;
}
