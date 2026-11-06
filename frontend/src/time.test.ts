import { describe, expect, it } from "vitest";
import { blockKey, blockParts, currentBlock, dataStatus, formatIst } from "./time";
import type { Meta } from "./types";

const blocks = [0, 6, 12, 18, 24, 30].map((h) => {
  const s = new Date(Date.UTC(2026, 10, 5, 12 + h)), e = new Date(s.getTime() + 6 * 3600e3);
  return { start_utc: s.toISOString(), end_utc: e.toISOString(), app_day: "", label: "" };
});
blocks[1].label = "Thu night · 23:30 Thu – 05:30 Fri IST";
const M = { run_time_utc: "2026-11-05T12:00:00+00:00", summary_start_blocks: 6, stale_after_h: 24, blocks } as unknown as Meta;

describe("formatIst", () => {
  it("adds 05:30 and names the IST day", () => {
    expect(formatIst("2026-11-05T23:49:26+00:00")).toBe("Fri 6 Nov 05:19 IST");
    expect(formatIst("2026-11-05T00:00:00Z")).toBe("Thu 5 Nov 05:30 IST");
  });
});

describe("currentBlock", () => {
  it("finds the block containing now, start inclusive, end exclusive", () => {
    expect(currentBlock(M, new Date("2026-11-05T18:00:00Z"))).toBe(1);
    expect(currentBlock(M, new Date("2026-11-05T17:59:59Z"))).toBe(0);
    expect(currentBlock(M, new Date("2026-11-05T11:59:00Z"))).toBeNull();
  });
});

describe("dataStatus", () => {
  it("is fresh, then stale after 24 h, then expired after the summary blocks", () => {
    expect(dataStatus(M, new Date("2026-11-05T20:00:00Z"))).toBe("fresh");
    expect(dataStatus(M, new Date("2026-11-06T11:59:00Z"))).toBe("fresh"); // 23.98 h after run start
    expect(dataStatus(M, new Date("2026-11-06T12:30:00Z"))).toBe("stale"); // 24.5 h, block 4 of 6
    expect(dataStatus({ ...M, summary_start_blocks: 2 } as Meta, new Date("2026-11-06T01:00:00Z"))).toBe("expired"); // block 2
    expect(dataStatus(M, new Date("2026-11-07T01:00:00Z"))).toBe("expired"); // after the last block
  });
});

describe("blocks", () => {
  it("splits the published label and keys blocks by start time", () => {
    expect(blockParts(blocks[1])).toEqual({ day: "Thu", name: "night", start: "23:30" });
    expect(blockKey(blocks[1])).toBe("2026-11-05T18");
  });
});
