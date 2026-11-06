import type { BlockMeta, Meta } from "./types";

const IST_MS = 5.5 * 3600 * 1000;
const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const pad = (n: number) => String(n).padStart(2, "0");

/** IST wall-clock parts of a UTC time (fixed +05:30, no DST), independent of the browser's locale and zone. */
function ist(t: Date) {
  const d = new Date(t.getTime() + IST_MS);
  return { wd: WD[d.getUTCDay()], day: d.getUTCDate(), mon: MON[d.getUTCMonth()], hh: pad(d.getUTCHours()), mm: pad(d.getUTCMinutes()) };
}

/** 'Thu 6 Nov 05:19 IST' */
export function formatIst(utc: string | Date): string {
  const p = ist(new Date(utc));
  return `${p.wd} ${p.day} ${p.mon} ${p.hh}:${p.mm} IST`;
}

/** Short block parts for the timeline: { day: 'Thu', name: 'afternoon', start: '11:30' } from the published label. */
export function blockParts(b: BlockMeta): { day: string; name: string; start: string } {
  const [day, name] = b.label.split(" · ")[0].split(" ");
  return { day, name, start: `${ist(new Date(b.start_utc)).hh}:${ist(new Date(b.start_utc)).mm}` };
}

/** Index of the block containing `now`, or null if now is before or after the run's blocks. */
export function currentBlock(m: Meta, now: Date): number | null {
  const t = now.getTime();
  const k = m.blocks.findIndex((b) => Date.parse(b.start_utc) <= t && t < Date.parse(b.end_utc));
  return k < 0 ? null : k;
}

export type Status = "fresh" | "stale" | "expired";

/** fresh / stale (a run was missed) / expired (no pre-written 48-h summary for now). Mirrors api/data.py. */
export function dataStatus(m: Meta, now: Date): Status {
  const k = currentBlock(m, now);
  if (k === null || k >= m.summary_start_blocks) return "expired";
  const staleMs = (m.stale_after_h ?? 24) * 3600 * 1000;
  return now.getTime() - Date.parse(m.run_time_utc) > staleMs ? "stale" : "fresh";
}

/** Block key that survives a new run (its start time), for URLs: '2026-11-06T06'. */
export function blockKey(b: BlockMeta): string {
  return b.start_utc.slice(0, 13);
}
