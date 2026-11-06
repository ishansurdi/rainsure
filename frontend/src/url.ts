// View state kept in the URL so any view can be shared exactly: place, block and layer.

export type LayerId = "chance" | "amount" | "agree" | "change";
export const LAYERS: LayerId[] = ["chance", "amount", "agree", "change"];

export type ModelView = "gap" | "ifs" | "aifs";
export const MODEL_VIEWS: ModelView[] = ["gap", "ifs", "aifs"];

export interface ViewState { lat?: number; lon?: number; name?: string; block?: string; layer: LayerId; models?: ModelView }

/** Parse '?lat=13.08&lon=80.27&name=Chennai&b=2026-11-06T06&layer=amount'; invalid parts are ignored. */
export function parseState(search: string): ViewState {
  const q = new URLSearchParams(search);
  const num = (k: string, lo: number, hi: number) => {
    const v = Number(q.get(k));
    return q.has(k) && Number.isFinite(v) && v >= lo && v <= hi ? v : undefined;
  };
  const lat = num("lat", -90, 90), lon = num("lon", -180, 180);
  const layer = q.get("layer") as LayerId | null;
  const block = q.get("b") ?? undefined;
  return {
    lat: lat !== undefined && lon !== undefined ? lat : undefined,
    lon: lat !== undefined && lon !== undefined ? lon : undefined,
    name: q.get("name")?.slice(0, 80) || undefined,
    block: block && /^\d{4}-\d{2}-\d{2}T\d{2}$/.test(block) ? block : undefined,
    layer: layer && LAYERS.includes(layer) ? layer : "chance",
    models: MODEL_VIEWS.includes(q.get("mv") as ModelView) ? (q.get("mv") as ModelView) : undefined,
  };
}

/** Inverse of parseState; coordinates rounded to 3 decimals (~100 m). */
export function stateToSearch(s: ViewState): string {
  const q = new URLSearchParams();
  if (s.lat !== undefined && s.lon !== undefined) {
    q.set("lat", s.lat.toFixed(3));
    q.set("lon", s.lon.toFixed(3));
  }
  if (s.name) q.set("name", s.name);
  if (s.block) q.set("b", s.block);
  if (s.layer !== "chance") q.set("layer", s.layer);
  if (s.layer === "agree" && s.models && s.models !== "gap") q.set("mv", s.models);
  const out = q.toString();
  return out ? `?${out}` : "";
}
