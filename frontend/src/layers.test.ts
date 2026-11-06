import { gzipSync } from "node:zlib";
import { describe, expect, it } from "vitest";
import { amountBin, chanceBin, layerBytes, layerValues, paintSlot, settledAlpha } from "./layers";

describe("chanceBin matches the sentence words (D50)", () => {
  it.each([[0, 0], [24, 0], [25, 1], [50, 1], [51, 2], [75, 2], [76, 3], [100, 3], [255, -1]])("%i -> %i", (c, b) => {
    expect(chanceBin(c)).toBe(b);
  });
});

describe("amountBin uses IMD bounds on the 0.1 mm value", () => {
  it.each([[0, 0], [1, 1], [24, 1], [25, 2], [155, 2], [156, 3], [644, 3], [645, 4], [1155, 4], [1156, 5],
    [2044, 5], [2045, 6], [65535, -1]])("%i tenths -> %i", (t, b) => {
    expect(amountBin(t)).toBe(b);
  });
});

describe("settledAlpha", () => {
  it("washes out unsettled cells", () => {
    expect(settledAlpha(0b111)).toBe(0.85);
    expect(settledAlpha(0b011)).toBe(0.7);
    expect(settledAlpha(0b001)).toBe(0.45);
  });
});

describe("layer bytes", () => {
  it("un-gzips when needed and reads little-endian u16", async () => {
    const raw = new Uint8Array([0x10, 0x27, 0xff, 0xff]); // 10000, 65535
    for (const body of [raw, gzipSync(raw)]) {
      const bytes = await layerBytes(new Response(body));
      expect(Array.from(layerValues(bytes, { file: "x", dtype: "u16", shape: [2], missing: 65535 }))).toEqual([10000, 65535]);
    }
  });
  it("rejects a truncated layer", () => {
    expect(() => layerValues(new Uint8Array(3), { file: "x", dtype: "u8", shape: [2, 2], missing: 255 })).toThrow();
  });
});

describe("paintSlot", () => {
  it("colours one slot through the row map and leaves no-colour cells transparent", () => {
    // 2 slots of a 2x2 grid; slot 1 = [0, 30, 80, 255]
    const v = new Uint8Array([0, 0, 0, 0, 0, 30, 80, 255]);
    const px = paintSlot(v, null, 1, 2, 2, new Int32Array([0, 1]), (c) => (chanceBin(c) > 0 ? "#102030" : null));
    expect(Array.from(px.slice(0, 4))).toEqual([0, 0, 0, 0]); // 0 of 100
    expect(Array.from(px.slice(4, 8))).toEqual([16, 32, 48, 204]); // 30 -> coloured, alpha 0.8
    expect(px[15]).toBe(0); // missing -> transparent
  });
});
