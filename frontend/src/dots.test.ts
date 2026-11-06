import { describe, expect, it } from "vitest";
import { decodeDots } from "./dots";

describe("decodeDots", () => {
  it("reads the bit layout written by store/points.py (MSB first)", () => {
    const d = decodeDots("fffffffc" + "00".repeat(9)); // physics members 1-30 wet
    expect(d.filter(Boolean).length).toBe(30);
    expect(d.slice(0, 30).every(Boolean)).toBe(true);
    expect(d[30]).toBe(false);
  });
  it("puts AI members in 50-99", () => {
    // bit 50 = byte 6 (chars 12-13), position 2 from the left -> 0x20
    const d = decodeDots("000000000000200000000000" + "00");
    expect(d.findIndex(Boolean)).toBe(50);
  });
  it("rejects malformed input", () => {
    expect(() => decodeDots("zz")).toThrow();
  });
});
