// MapLibre map: OpenFreeMap basemap without its borders, our India-POV borders, and the rain image on top.
import { Map as MLMap, setWorkerUrl, type ImageSource, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
// MapLibre 6 looks for its worker next to its own module file, which bundlers move; ship the worker as an asset.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { HIDDEN_STYLE_LAYERS, STYLE_URL } from "./config";
import { gridBounds, mercatorRowMap } from "./grid";
import type { Grid } from "./types";

const ROWS_PER_CELL = 4;
let rowMap: Int32Array | null = null;

export async function createMap(container: string): Promise<MLMap> {
  setWorkerUrl(new URL(workerUrl, location.href).href);
  const style = (await (await fetch(STYLE_URL)).json()) as StyleSpecification;
  style.layers = style.layers.filter((l) => !HIDDEN_STYLE_LAYERS.includes(l.id));
  const map = new MLMap({
    container, style, center: [80, 22], zoom: 3.6, minZoom: 3, maxZoom: 11,
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
