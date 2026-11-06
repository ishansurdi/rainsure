// Details below the answer (lazy-loaded): is it changing, 100 dots, meteogram, day totals. Picks published numbers and
// strings only; the SVG scales are presentation.
import { decodeDots } from "./dots";
import { blockParts } from "./time";
import type { Cell, Meta, Tile } from "./types";

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
const METEO_BLOCKS = 16; // 4 days from the current block

function changing(cell: Cell, k: number): string {
  const prev = cell.b[k][2];
  const now = cell.b[k][0] + cell.b[k][1];
  if (prev < 0) return `<p class="note">No earlier forecast to compare for this block.</p>`;
  const arrow = now > prev ? "▲" : now < prev ? "▼" : "=";
  return `<p class="changing"><b>Is it changing?</b> Previous forecast ${prev} → now ${now} of 100 forecasts with ≥ 2.5 mm <span aria-hidden="true">${arrow}</span></p>`;
}

function dotGrid(cell: Cell, k: number): string {
  const d = decodeDots(cell.b[k][3]);
  const row = (from: number, cls: string) =>
    Array.from({ length: 25 }, (_, n) => `<i class="dot ${cls}${d[from + n] ? " wet" : ""}"></i>`).join("");
  return `<figure class="dots" aria-label="Physics ${cell.b[k][0]} of 50 and AI ${cell.b[k][1]} of 50 forecasts give at least 2.5 mm">
    <div class="dots-model"><span class="lbl phys">Physics</span><div class="dots-rows"><div>${row(0, "phys")}</div><div>${row(25, "phys")}</div></div></div>
    <div class="dots-model"><span class="lbl ai">AI</span><div class="dots-rows"><div>${row(50, "ai")}</div><div>${row(75, "ai")}</div></div></div>
    <figcaption>Physics ${cell.b[k][0]} of 50, AI ${cell.b[k][1]} of 50 give ≥ 2.5 mm. One dot = one forecast.</figcaption></figure>`;
}

function meteogram(m: Meta, cell: Cell, sel: number, kNow: number): string {
  const ks = Array.from({ length: METEO_BLOCKS }, (_, n) => kNow + n).filter((k) => k < m.blocks.length);
  const top = Math.max(5, ...ks.map((k) => cell.b[k][5])); // p90 in mm, at least 5 mm so 2.5 mm is visible
  const W = 340, H = 140, padL = 28, padB = 22, bw = (W - padL) / ks.length;
  const y = (mm: number) => (H - padB) * (1 - Math.min(mm, top) / top);
  let svg = "";
  ks.forEach((k, n) => {
    const [, , , , p10, p90, mi, ma] = cell.b[k];
    const x = padL + n * bw;
    if (k === sel) svg += `<rect x="${x}" y="0" width="${bw}" height="${H - padB}" class="sel"/>`;
    svg += `<rect x="${x + bw * 0.2}" y="${y(p90)}" width="${bw * 0.6}" height="${Math.max(1, y(p10) - y(p90))}" class="band"/>`;
    // medians side by side at their exact heights (physics left half, AI right half) rather than offset
    svg += `<line x1="${x + bw * 0.12}" x2="${x + bw * 0.5}" y1="${y(mi)}" y2="${y(mi)}" class="phys"/>`;
    svg += `<line x1="${x + bw * 0.5}" x2="${x + bw * 0.88}" y1="${y(ma)}" y2="${y(ma)}" class="ai"/>`;
    const p = blockParts(m.blocks[k]);
    if (p.name === "morning") svg += `<text x="${x + 2}" y="${H - 6}" class="tick">${p.day}</text>`;
  });
  svg += `<line x1="${padL}" x2="${W}" y1="${y(2.5)}" y2="${y(2.5)}" class="thr"/><text x="2" y="${y(2.5) + 4}" class="tick">2.5</text>`;
  svg += `<text x="2" y="10" class="tick">${top.toFixed(0)}</text><text x="2" y="${H - padB}" class="tick">0</text>`;
  svg += `<line x1="${padL}" x2="${padL}" y1="0" y2="${H - padB}" class="now"/><text x="${padL + 2}" y="10" class="tick b">now</text>`;
  return `<figure class="meteo"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Rain per 6-hour block, mm: range of 100 forecasts and each model's median">${svg}</svg>
    <figcaption><span class="key band"></span>10–90 % of 100 forecasts <span class="key phys"></span>physics median <span class="key ai"></span>AI median · mm per 6 hours</figcaption></figure>`;
}

function dayTotals(m: Meta, tile: Tile, cell: Cell): string {
  return `<h3 class="h3">Day totals</h3>` + m.days.slice(0, 5).map((_, k) =>
    `<p class="day">${esc(tile.strings[cell.dt[k][0]])}</p>`).join("");
}

export function renderDetails(m: Meta, tile: Tile, cell: Cell, sel: number, kNow: number): string {
  const p = blockParts(m.blocks[sel]);
  return `<section class="details" aria-label="Details">
    <h3 class="h3">${esc(p.day)} ${esc(p.name)} in detail</h3>
    ${changing(cell, sel)}
    ${dotGrid(cell, sel)}
    ${meteogram(m, cell, sel, kNow)}
    ${dayTotals(m, tile, cell)}
    <p class="note">Days run 05:30–05:30 IST; IMD rain categories are applied to that window. The data is 6-hourly, so shorter bursts are not shown.</p>
  </section>`;
}
