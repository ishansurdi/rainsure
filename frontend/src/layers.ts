// Decode published map layers and turn them into colours (presentation only: no forecast values are computed).
import type { LayerMeta } from "./types";

export const U8_MISSING = 255;
export const U16_MISSING = 65535;

type RGB = [number, number, number];
const hex = (h: string): RGB => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];

// Chance of >= 2.5 mm, pooled count of 100, binned exactly like the sentence words (DECISIONS.md D50):
// under 25 unlikely (no colour), 25-50 likely, 51-75 very likely, over 75 most likely.
export const CHANCE_BINS = [
  { label: "Likely (25–50)", color: "#8DBFA0" },
  { label: "Very likely (51–75)", color: "#2C7A8C" },
  { label: "Most likely (76–100)", color: "#2A3463" },
];
/** 0 = no colour (under 25 of 100), 1..3 = CHANCE_BINS index + 1, -1 = missing. */
export function chanceBin(count: number): number {
  if (count === U8_MISSING) return -1;
  if (count < 25) return 0;
  if (count <= 50) return 1;
  return count <= 75 ? 2 : 3;
}

// Day total median in tenths of mm, IMD categories applied to the displayed 0.1 mm value (D16, D51).
export const AMOUNT_BINS = [
  { label: "Very light (0.1–2.4 mm)", color: "#C9D8B6", from: 1 },
  { label: "Light (2.5–15.5)", color: "#8DBFA0", from: 25 },
  { label: "Moderate (15.6–64.4)", color: "#4FA096", from: 156 },
  { label: "Heavy (64.5–115.5)", color: "#2C7A8C", from: 645 },
  { label: "Very heavy (115.6–204.4)", color: "#24547A", from: 1156 },
  { label: "Extremely heavy (≥ 204.5)", color: "#2A3463", from: 2045 },
];
/** 0 = under 0.1 mm (no colour), 1..6 = AMOUNT_BINS index + 1, -1 = missing. */
export function amountBin(tenthsMm: number): number {
  if (tenthsMm === U16_MISSING) return -1;
  let bin = 0;
  AMOUNT_BINS.forEach((b, n) => { if (tenthsMm >= b.from) bin = n + 1; });
  return bin;
}

// Gap between the models, published as AIFS count - IFS count + 50 (D57). Differences under 20 points are the D15
// "agree" range and get no colour; then three steps of 20 points, indigo = physics wetter, terracotta = AI wetter.
export const GAP_BINS = [
  { label: "Physics wetter by 60+ points", color: "#2A3463" },
  { label: "40–59", color: "#6C7399" },
  { label: "20–39", color: "#A9AECB" },
  { label: "AI wetter by 20–39", color: "#E2BBA9" },
  { label: "40–59", color: "#C9876A" },
  { label: "60+ points", color: "#B0562F" },
];
/** Colour for a published gap value (0..100, 50 = equal), or null where the models agree or the value is missing. */
export function gapColor(g: number): string | null {
  if (g === U8_MISSING) return null;
  const pts = (g - 50) * 2; // AIFS minus IFS, in points of 100
  const a = Math.abs(pts);
  if (a < 20) return null;
  const step = a >= 60 ? 0 : a >= 40 ? 1 : 2; // strongest first
  return pts < 0 ? GAP_BINS[step].color : GAP_BINS[5 - step].color;
}

/** Opacity from the settled bitmask (decided | agree << 1 | stable << 2): unsettled areas are washed out. */
export function settledAlpha(bits: number): number {
  const n = (bits & 1) + ((bits >> 1) & 1) + ((bits >> 2) & 1);
  return n === 3 ? 0.85 : n === 2 ? 0.7 : 0.45;
}

/** Raw bytes of a published layer; un-gzips when the server did not (gzip magic 1f 8b). */
export async function layerBytes(res: Response): Promise<Uint8Array> {
  const buf = new Uint8Array(await res.arrayBuffer());
  if (buf[0] !== 0x1f || buf[1] !== 0x8b) return buf;
  const stream = new Blob([buf]).stream().pipeThrough(new DecompressionStream("gzip"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/** Typed values of a layer (little-endian u16 read explicitly). */
export function layerValues(bytes: Uint8Array, meta: LayerMeta): Uint8Array | Uint16Array {
  const n = meta.shape.reduce((a, b) => a * b, 1);
  if (meta.dtype === "u8") {
    if (bytes.length !== n) throw new Error(`layer ${meta.file}: ${bytes.length} bytes, expected ${n}`);
    return bytes;
  }
  if (bytes.length !== 2 * n) throw new Error(`layer ${meta.file}: ${bytes.length} bytes, expected ${2 * n}`);
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const out = new Uint16Array(n);
  for (let k = 0; k < n; k++) out[k] = dv.getUint16(2 * k, true);
  return out;
}

/** RGBA pixels (n_lon wide, rowMap.length tall) for one time slot; rowMap from grid.mercatorRowMap. */
export function paintSlot(values: ArrayLike<number>, settled: ArrayLike<number> | null, slot: number, nLat: number,
  nLon: number, rowMap: Int32Array, colorOf: (v: number) => string | null): Uint8ClampedArray {
  const out = new Uint8ClampedArray(nLon * rowMap.length * 4);
  const base = slot * nLat * nLon;
  const cache = new Map<string, RGB>();
  for (let r = 0; r < rowMap.length; r++) {
    const row = base + rowMap[r] * nLon;
    for (let i = 0; i < nLon; i++) {
      const c = colorOf(values[row + i]);
      if (!c) continue;
      let rgb = cache.get(c);
      if (!rgb) { rgb = hex(c); cache.set(c, rgb); }
      const o = (r * nLon + i) * 4;
      out[o] = rgb[0]; out[o + 1] = rgb[1]; out[o + 2] = rgb[2];
      out[o + 3] = Math.round(255 * (settled ? settledAlpha(settled[row + i]) : 0.8));
    }
  }
  return out;
}
