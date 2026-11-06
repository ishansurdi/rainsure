// Fetch published products from Pages (and ping the optional API). No forecast values are computed here.
import { API_BASE, DATA_BASE } from "./config";
import { tilePath } from "./grid";
import { layerBytes, layerValues } from "./layers";
import type { Place } from "./search";
import type { Meta, Tile } from "./types";

async function getJson<T>(url: string, retries = 1): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    try {
      const r = await fetch(url, { cache: "no-cache" });
      if (!r.ok) throw new Error(`HTTP ${r.status} for ${url}`);
      return (await r.json()) as T;
    } catch (e) {
      if (attempt >= retries) throw e;
      await new Promise((ok) => setTimeout(ok, 800));
    }
  }
}

export const loadMeta = () => getJson<Meta>(`${DATA_BASE}/latest.json`);

const tiles = new Map<string, Promise<Tile>>();
/** Point tile for cell (j, i): tried twice, then the error reaches the caller (honest "couldn't load" state). */
export function loadTile(m: Meta, j: number, i: number): Promise<Tile> {
  const path = tilePath(m, j, i);
  if (!tiles.has(path)) {
    const p = getJson<Tile>(`${DATA_BASE}/${path}`);
    p.catch(() => tiles.delete(path));
    tiles.set(path, p);
  }
  return tiles.get(path)!;
}

const layers = new Map<string, Promise<Uint8Array | Uint16Array>>();
export function loadLayer(m: Meta, name: string): Promise<Uint8Array | Uint16Array> {
  const key = `${m.run_id}/${name}`;
  if (!layers.has(key)) {
    const meta = m.layers[name];
    const p = fetch(`${DATA_BASE}/${m.run_id}/layers/${meta.file}`).then(async (r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status} for layer ${name}`);
      return layerValues(await layerBytes(r), meta);
    });
    p.catch(() => layers.delete(key));
    layers.set(key, p);
  }
  return layers.get(key)!;
}

let places: Promise<Place[]> | null = null;
export function loadPlaces(): Promise<Place[]> {
  places ??= getJson<Place[]>(`${import.meta.env.BASE_URL}geo/places.json`).catch((e) => { places = null; throw e; });
  return places;
}

export type ApiState = "awake" | "not-answering";
/**
 * Ping the Render API (this also wakes it). While Render wakes it serves a 503 page without CORS headers, which the
 * browser reports exactly like a network failure, so "waking" and "down" cannot be told apart: both are "not-answering".
 * Never blocks the UI: the app runs from static files.
 */
export async function pingApi(timeoutMs = 8000): Promise<ApiState> {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetch(`${API_BASE}/healthz`, { signal: ctl.signal, cache: "no-store" });
    return r.ok && (r.headers.get("content-type") ?? "").includes("json") ? "awake" : "not-answering";
  } catch {
    return "not-answering";
  } finally {
    clearTimeout(t);
  }
}
