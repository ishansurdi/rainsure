import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "./style.css";
import type { Map as MLMap, MapMouseEvent, Marker } from "maplibre-gl";
import { API_BASE, REPO_URL } from "./config";
import { loadLayer, loadMeta, loadPlaces, loadTile, pingApi, type ApiState } from "./data";
import { cellCentre, cellIndex } from "./grid";
import { AMOUNT_BINS, CHANCE_BINS, GAP_BINS, amountBin, chanceBin, gapColor, paintSlot } from "./layers";
import { createMap, makeMarker, preloadMap, rowsFor, showRain } from "./map";
import { nearestPlace, searchPlaces } from "./search";
import { initSheet, setFirstSnap } from "./sheet";
import { blockKey, blockParts, currentBlock, dataStatus, formatIst } from "./time";
import type { Cell, Meta, Tile } from "./types";
import { parseState, stateToSearch, type LayerId, type ModelView, type ViewState } from "./url";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
const LAST_PLACE = "rain-trust:last-place";
const DEBUG = new URLSearchParams(location.search).has("debug"); // read before the URL is rewritten by syncUrl
// ?now=2026-11-08T06:00:00Z views the forecast as of that time (states and demos), like the API's at=; kept in the URL
const NOW_PARAM = new URLSearchParams(location.search).get("now");
const NOW_FIXED = NOW_PARAM && !Number.isNaN(Date.parse(NOW_PARAM)) ? new Date(NOW_PARAM) : null;
const now = (): Date => NOW_FIXED ?? new Date();
let locationNote = "";

let meta: Meta;
let map: MLMap | null = null;
let marker: Marker | null = null;
let view: ViewState = parseState(location.search);
let place: { lat: number; lon: number; name: string } | null = null;
let cellData: { tile: Tile; cell: Cell; j: number; i: number } | null = null;
let placeError: "outside" | "tile" | null = null;
let sel = 0;
let kNow: number | null = null;
let apiState: ApiState | "checking" = "checking";

// ---------- rendering ----------
function renderIssued(): void {
  // The forecast's age is its ECMWF run start, not when we last rebuilt the site (a frontend deploy changes that).
  const el = $("issued");
  el.textContent = `Forecast run ${formatIst(meta.run_time_utc)}`;
  const banner = $("banner"), status = dataStatus(meta, now());
  banner.hidden = status === "fresh";
  banner.textContent = status === "stale"
    ? `Showing the forecast from the run of ${formatIst(meta.run_time_utc)}. A newer one is not available yet.`
    : status === "expired" ? "No current forecast: the newest one we have is more than 72 hours old." : "";
  el.title = `ECMWF run ${meta.run_id.slice(8)} UTC on ${meta.run_id.slice(6, 8)}/${meta.run_id.slice(4, 6)}; products built ${formatIst(meta.processed_at_utc)}`;
}

function dayIndexOf(k: number): number {
  return meta.days.findIndex((d) => d.app_day === meta.blocks[k].app_day);
}

function renderLegend(): void {
  const el = $("legend");
  if (dataStatus(meta, now()) === "expired") { el.innerHTML = "<b>No current forecast</b>"; return; }
  const swatch = (color: string, short: string, long: string) =>
    `<span class="row"><i style="background:${color}"></i>${short}<span class="long">&nbsp;${long}</span></span>`;
  if (view.layer === "agree") {
    const mv = view.models ?? "gap";
    if (mv === "gap") {
      const row = (title: string, bins: typeof GAP_BINS, labels: string[]) =>
        `<div class="gaprow">${title}: ${bins.map((b, n) => `<span class="row"><i style="background:${b.color}"></i>${labels[n]}</span>`).join("")}</div>`;
      el.innerHTML = `<b>Physics vs AI gap<span class="long"> · ${esc(meta.blocks[sel].label)}</span></b>` +
        row("Physics wetter", GAP_BINS.slice(0, 3), ["60+", "40–59", "20–39"]) +
        row("AI wetter", GAP_BINS.slice(3), ["20–39", "40–59", "60+"]) +
        `<div class="note">Difference in chance of ≥ 2.5 mm, points of 100. Under 20 points: the models agree, no colour.</div>`;
    } else {
      el.innerHTML = `<b>${mv === "ifs" ? "Physics model (IFS)" : "AI model (AIFS)"} · chance of ≥ 2.5 mm<span class="long"> · ${esc(meta.blocks[sel].label)}</span></b><div class="swatches">` +
        CHANCE_BINS.map((b) => swatch(b.color, b.label.split(" (")[1].replace(")", ""), b.label.split(" (")[0].toLowerCase())).join("") +
        `</div><div class="note">Same scale for both models: share of each model's 50 forecasts. Switch to compare.</div>`;
    }
    return;
  }
  if (view.layer === "chance") {
    el.innerHTML = `<b>Chance of ≥ 2.5 mm<span class="long"> · ${esc(meta.blocks[sel].label)}</span></b><div class="swatches">` +
      CHANCE_BINS.map((b) => swatch(b.color, b.label.split(" (")[1].replace(")", ""), b.label.split(" (")[0].toLowerCase())).join("") +
      `</div><div class="note">Forecasts of 100 with ≥ 2.5 mm. Under 25: no colour. Faded = forecast unsettled.</div>`;
  } else {
    const d = dayIndexOf(sel);
    const title = d < 0 ? "Day total · not available for this part-day"
      : `Day total · ${esc(meta.days[d].label.split(" · ")[0])}<span class="long"> · ${esc(meta.days[d].label.split(" · ")[1] ?? "")}</span>`;
    el.innerHTML = `<b>${title}</b><div class="swatches">` +
      AMOUNT_BINS.map((b) => swatch(b.color, b.label.split(" (")[0], `(${b.label.split(" (")[1]}`)).join("") +
      `</div><div class="note">Median of 100 forecasts, IMD categories. Same for every block of the day.</div>`;
  }
}

async function renderMap(): Promise<void> {
  if (!map) return;
  const g = meta.grid;
  if (dataStatus(meta, now()) === "expired") { showRain(map, g, null); return; }
  if (view.layer === "agree") {
    const mv = view.models ?? "gap";
    if (mv === "gap") {
      const v = await loadLayer(meta, "block_gap");
      showRain(map, g, paintSlot(v, null, sel, g.n_lat, g.n_lon, rowsFor(g), gapColor));
    } else {
      const v = await loadLayer(meta, mv === "ifs" ? "block_ifs" : "block_aifs");
      showRain(map, g, paintSlot(v, null, sel, g.n_lat, g.n_lon, rowsFor(g), (c) => {
        const b = c === 255 ? -1 : chanceBin(c * 2); // count of 50 -> of 100, same bins as the pooled map
        return b > 0 ? CHANCE_BINS[b - 1].color : null;
      }));
    }
    return;
  }
  if (view.layer === "chance") {
    const [v, s] = await Promise.all([loadLayer(meta, "block_pooled"), loadLayer(meta, "block_settled")]);
    showRain(map, g, paintSlot(v, s, sel, g.n_lat, g.n_lon, rowsFor(g), (c) => {
      const b = chanceBin(c);
      return b > 0 ? CHANCE_BINS[b - 1].color : null;
    }));
  } else {
    const d = dayIndexOf(sel);
    if (d < 0) { showRain(map, g, null); return; }
    const [v, s] = await Promise.all([loadLayer(meta, "day_median"), loadLayer(meta, "day_settled")]);
    showRain(map, g, paintSlot(v, s, d, g.n_lat, g.n_lon, rowsFor(g), (t) => {
      const b = amountBin(t);
      return b > 0 ? AMOUNT_BINS[b - 1].color : null;
    }));
  }
}

function timelineHtml(cell: Cell): string {
  const start = kNow ?? 0;
  let html = "", lastDay = "";
  for (let k = start; k < meta.blocks.length; k++) {
    const p = blockParts(meta.blocks[k]);
    const n = cell.b[k][0] + cell.b[k][1];
    const dayStart = meta.blocks[k].app_day !== lastDay && k !== start;
    lastDay = meta.blocks[k].app_day;
    const differ = (cell.bt[k][2] ?? -1) >= 0;
    const h = n === 0 ? 2 : 3 + n * 0.27; // visible from 1 forecast, still ordered: 8 -> 5.2 px, 18 -> 7.9 px, 100 -> 30 px
    // accessible name = visible text + a hidden full description, so voice control ("tap 31") still matches
    html += `<button class="tb${dayStart ? " daystart" : ""}" data-k="${k}" aria-pressed="${k === sel}">
      <span class="now">${k === kNow ? "now" : differ ? '<i class="mark" aria-hidden="true"></i>' : ""}</span><span class="bar${n >= 25 ? " wet" : ""}" style="height:${h}px"></span>
      <span class="n">${n}</span><span class="d">${p.day} ${p.name.slice(0, 3)}</span><span class="t">${p.start}</span>
      <span class="sr">: ${esc(meta.blocks[k].label)}, ${n} of 100 forecasts give at least 2.5 mm${differ ? "; physics and AI models disagree" : ""}</span></button>`;
  }
  return `<div class="timeline" id="timeline" aria-label="Chance of at least 2.5 mm per 6-hour block, of 100 forecasts">${html}</div>`;
}

function renderSheet(): void {
  const body = $("sheet-body");
  const status = dataStatus(meta, now());
  if (!place) {
    body.innerHTML = `<h2 class="place">Will it rain where you are?</h2>
      <p class="summary">Search for a place in India, tap the map, or use your location.</p>
      <div><button class="btn dark" id="use-loc">Use my location</button></div>
      ${locationNote ? `<p class="note" role="status">${esc(locationNote)}</p>` : ""}
      <p class="note">100 forecasts from ECMWF: 50 from the physics model (IFS) and 50 from the AI model (AIFS).</p>`;
    $("use-loc").onclick = locate;
    return;
  }
  const head = `<h2 class="place">${esc(place.name)}</h2>`;
  if (placeError === "outside") {
    const g = meta.grid, south = g.lat_first - (g.n_lat - 1) * g.step_deg, east = g.lon_first + (g.n_lon - 1) * g.step_deg;
    const near = { lat: Math.min(g.lat_first, Math.max(south, place.lat)), lon: Math.min(east, Math.max(g.lon_first, place.lon)) };
    body.innerHTML = `${head}<p class="summary">We cover India and nearby areas (${south}–${g.lat_first} N, ${g.lon_first}–${east} E). This point (${place.lat.toFixed(2)} N, ${place.lon.toFixed(2)} E) is outside.</p>
      <div><button class="btn dark" id="go-near">Go to the nearest covered point (${near.lat.toFixed(2)} N, ${near.lon.toFixed(2)} E)</button></div>`;
    $("go-near").onclick = () => void setPlace(near.lat, near.lon, "Selected point");
    return;
  }
  if (placeError === "tile") {
    body.innerHTML = `${head}<p class="summary">Couldn’t load the forecast for this area. We tried twice; this is usually the connection.</p>
      <div><button class="btn dark" id="retry">Try again</button></div>`;
    $("retry").onclick = () => setPlace(place!.lat, place!.lon, place!.name);
    return;
  }
  if (!cellData) { body.innerHTML = `${head}<div class="skeleton"><span></span><span></span><span></span></div>`; return; }
  const { tile, cell, j, i } = cellData;
  const c = cellCentre(meta.grid, j, i);
  const S = tile.strings;
  const coords = `<p class="coords">${place.lat.toFixed(2)} N, ${place.lon.toFixed(2)} E · forecast grid point ${c.lat.toFixed(2)} N, ${c.lon.toFixed(2)} E · next 48 hours</p>`;
  if (status === "expired" || kNow === null) {
    body.innerHTML = `${head}${coords}<p class="summary">Forecast out of date. The newest forecast we have is from the run of ${formatIst(meta.run_time_utc)}, more than 72 hours ago. We don’t show old numbers as a forecast.</p>`;
    return;
  }
  if (!performance.getEntriesByName("answer-visible").length) performance.mark("answer-visible"); // speed check, D62
  const settled = S[cell.bt[sel][1]];
  const models = (cell.bt[sel][2] ?? -1) >= 0 ? `<p class="models">${esc(S[cell.bt[sel][2]])}</p>` : "";
  const ok = settled.startsWith("Forecast settled.");
  const chip = settled.split(/[:.]/)[0]; // "Forecast settled" / "Forecast fairly settled" / "Forecast unsettled"
  // At the 40 % snap: name + trust chip, summary, timeline. The selected block's sentences follow the timeline.
  body.innerHTML = `<div class="head-row"><h2 class="place">${esc(place.name)}</h2>
      <span class="trust ${ok ? "settled" : "unsettled"}" title="${esc(settled)}">${esc(chip)}</span></div>${coords}
    <p class="summary">${esc(S[cell.s[kNow]])}</p>
    ${timelineHtml(cell)}
    <p class="block-answer">${esc(S[cell.bt[sel][0]])}</p>
    <p class="pill ${ok ? "settled" : "unsettled"}">${esc(settled)}</p>
    ${models}
    <div id="details"><div class="skeleton"><span></span><span></span></div></div>`;
  fitSheet();
  $("timeline").querySelectorAll<HTMLButtonElement>(".tb").forEach((b) => (b.onclick = () => selectBlock(Number(b.dataset.k))));
  const tl = $("timeline"), pressed = tl.querySelector<HTMLElement>('[aria-pressed="true"]');
  if (pressed) tl.scrollLeft = pressed.offsetLeft - tl.offsetLeft - tl.clientWidth / 2 + pressed.clientWidth / 2; // sideways only
  const want = { tile, cell, sel, kNow };
  void import("./details").then(({ renderDetails }) => {
    if (cellData?.cell !== want.cell || sel !== want.sel) return; // something newer was rendered
    const el = document.getElementById("details");
    if (el) el.innerHTML = renderDetails(meta, want.tile, want.cell, want.sel, want.kNow);
  }).catch(() => {
    const el = document.getElementById("details");
    if (el) el.innerHTML = `<p class="note">Details didn’t load. Check the connection.</p>`;
  });
}

/** Phone: raise the first snap just enough that the whole timeline shows (never above 55 % of the screen). */
function fitSheet(): void {
  if (innerWidth >= 1024) return;
  const tl = document.getElementById("timeline");
  if (!tl) return;
  const sheetTop = $("sheet").getBoundingClientRect().top;
  const need = tl.getBoundingClientRect().bottom - sheetTop + $("sheet-body").scrollTop + 12; // px below the sheet top
  setFirstSnap(Math.max(0.45, Math.min(0.6, 1 - need / innerHeight)));
}

function syncUrl(): void {
  view = { ...view, lat: place?.lat, lon: place?.lon, name: place?.name, block: blockKey(meta.blocks[sel]) };
  const q = stateToSearch(view);
  const keep = NOW_FIXED ? `${q ? "&" : "?"}now=${encodeURIComponent(NOW_PARAM!)}` : "";
  history.replaceState(null, "", `${location.pathname}${q}${keep}`);
}

function renderAll(): void {
  renderLegend();
  renderSheet();
  void renderMap().catch(() => showRain(map!, meta.grid, null));
  document.querySelectorAll<HTMLButtonElement>(".chip").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.layer === view.layer)));
  $("models-seg").hidden = view.layer !== "agree";
  document.querySelectorAll<HTMLButtonElement>("#models-seg button").forEach((b) =>
    b.setAttribute("aria-checked", String(b.dataset.mv === (view.models ?? "gap"))));
  syncUrl();
}

// ---------- actions ----------
function selectBlock(k: number): void {
  sel = k;
  renderAll();
  // bring the tapped block's sentence, pill and model note into view (the sheet may be at 40 %)
  const body = $("sheet-body"), ans = body.querySelector<HTMLElement>(".block-answer");
  if (ans) body.scrollTo({ top: ans.offsetTop - body.offsetTop - 8, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
}

const UNNAMED = new Set(["Selected point", "Your location"]);

/** Name a tapped or located point after the nearest place in our list (GeoNames), else its coordinates. */
async function nameFor(lat: number, lon: number): Promise<string> {
  try {
    const hit = nearestPlace(await loadPlaces(), lat, lon);
    if (hit) return `${hit.km < 5 ? "" : "Near "}${hit.place[0]}, ${hit.place[1]}`;
  } catch { /* place list unavailable: fall back to coordinates */ }
  return `${lat.toFixed(2)} N, ${lon.toFixed(2)} E`;
}

async function setPlace(lat: number, lon: number, name: string): Promise<void> {
  place = { lat, lon, name };
  cellData = null;
  placeError = null;
  placeMarker(lat, lon);
  if (UNNAMED.has(name)) {
    void nameFor(lat, lon).then((n) => {
      if (place?.lat === lat && place.lon === lon) {
        place.name = n;
        try { localStorage.setItem(LAST_PLACE, JSON.stringify(place)); } catch { /* fine */ }
        renderAll();
      }
    });
  }
  try { localStorage.setItem(LAST_PLACE, JSON.stringify(place)); } catch { /* storage unavailable: fine */ }
  const ji = cellIndex(meta.grid, lat, lon);
  if (!ji) { placeError = "outside"; renderAll(); return; }
  renderAll();
  try {
    const tile = await loadTile(meta, ji.j, ji.i);
    if (place.lat !== lat || place.lon !== lon) return; // a newer choice won
    cellData = { tile, cell: tile.cells[`${ji.j}_${ji.i}`], ...ji };
  } catch {
    placeError = "tile";
  }
  renderAll();
  answerDataReady();
}

function placeMarker(lat: number, lon: number, animate = true): void {
  marker?.remove();
  if (!map) return;
  const el = document.createElement("div");
  el.className = "marker";
  marker = makeMarker(map, el, lon, lat);
  const phone = innerWidth < 1024;
  const cam = { center: [lon, lat] as [number, number], zoom: Math.max(map.getZoom(), 6.5),
    padding: { bottom: phone ? innerHeight * 0.4 : 0, top: phone ? 150 : 0, left: 0, right: 0 } };
  if (animate && !matchMedia("(prefers-reduced-motion: reduce)").matches) map.flyTo(cam); else map.jumpTo(cam);
}

function locate(): void {
  const off = () => { // denied or unavailable: one quiet line, never a repeated prompt
    locationNote = "Location is off or unavailable. Search for a place or tap the map.";
    if (!place) renderSheet();
  };
  if (!navigator.geolocation) return off();
  navigator.geolocation.getCurrentPosition(
    (p) => void setPlace(p.coords.latitude, p.coords.longitude, "Your location"),
    off,
    { timeout: 10000, maximumAge: 600000 },
  );
}

function initSearch(): void {
  const q = $<HTMLInputElement>("q"), list = $<HTMLUListElement>("results");
  q.addEventListener("focus", () => void loadPlaces().catch(() => undefined));
  q.addEventListener("input", async () => {
    const text = q.value;
    if (text.trim().length < 2) { list.hidden = true; return; }
    let hits;
    try { hits = searchPlaces(await loadPlaces(), text); } catch { list.innerHTML = `<li class="none">Place list didn’t load. Tap the map instead.</li>`; list.hidden = false; return; }
    if (q.value !== text) return;
    list.innerHTML = hits.length
      ? hits.map((p, n) => `<li role="option" data-n="${n}">${esc(p[0])} <small>${esc(p[1])}</small></li>`).join("")
      : `<li class="none">No place called “${esc(text)}” in our list of Indian places. Try a nearby town, or tap the map.</li>`;
    list.hidden = false;
    list.querySelectorAll<HTMLLIElement>("li[data-n]").forEach((li) => (li.onclick = () => {
      const p = hits[Number(li.dataset.n)];
      list.hidden = true; q.value = ""; q.blur();
      void setPlace(p[2], p[3], `${p[0]}, ${p[1]}`);
    }));
  });
  q.addEventListener("keydown", (e) => { if (e.key === "Escape") { list.hidden = true; q.blur(); } });
}

function renderAbout(): void {
  const dot = apiState === "awake" ? "up" : "waking";
  const word = { awake: "awake", "not-answering": "not answering right now. It may be waking up: the free plan sleeps after 15 minutes idle and takes about a minute to wake", checking: "checking…" }[apiState];
  $("about").innerHTML = `<h2>About rain-trust</h2>
    <p>Rain chances for India from 100 ECMWF forecasts: 50 from the IFS physics ensemble and 50 from the AIFS AI ensemble.
    The app answers first and shows how far to trust it: how many forecasts agree, whether physics and AI agree, and how much it changed since the previous forecast.</p>
    <h3>How to read it</h3>
    <p><b>100 forecasts.</b> ECMWF runs its forecast many times with slightly different starting conditions. We use 50 runs of the physics model (IFS) and 50 of the AI model (AIFS). “54 of 100 forecasts give ≥ 2.5 mm” means 54 of those runs bring at least 2.5 mm in that 6-hour block.</p>
    <p><b>Settled or unsettled.</b> This is about trust, not about rain: a forecast is settled when it is clear-cut (under 20 or over 80 of 100), the two models agree, and it changed little since the previous forecast.</p>
    <p><b>Physics and AI.</b> Where the two models differ by 20 points or more, we say how, from the numbers only: one model’s rain is lighter, earlier or later, or a little further away. Which model is drier varies; in our data the physics model is often the lighter one. As background only, one ECMWF case study (Storm Hans, Alps, April 2025) found: “The underprediction of AIFS ENS seems more pronounced than in the case of IFS ENS.” and “Nevertheless, both AIFS ENS and IFS ENS gave early indication of the possibility of an extreme event.” That is one storm, not a rule. <a href="https://www.ecmwf.int/sites/default/files/elibrary/102025/81687-aifs-ens-becomes-operational.pdf" target="_blank" rel="noopener">ECMWF Newsletter 185, Lang et al., doi:10.21957/hg1z-pe65</a>.</p>
    <p><b>Days and times.</b> Days run 05:30–05:30 IST (00–00 UTC) because the AI model only gives 6-hourly steps, so IMD’s 08:30 IST day can’t be built from it. All times are IST.</p>
    <h3>Backend</h3>
    <p><span class="status-dot ${dot}"></span>API: ${word}. <a href="${API_BASE}" target="_blank" rel="noopener">${API_BASE}</a> ·
    <a href="${API_BASE}/docs" target="_blank" rel="noopener">API docs (/docs)</a> · <a href="${REPO_URL}" target="_blank" rel="noopener">Source on GitHub</a></p>
    <p class="note">The map and answers load from static files, so the app works while the API sleeps.</p>
    <h3>Credits</h3>
    <p>This service is based on data and products of the European Centre for Medium-Range Weather Forecasts (ECMWF). Source: <a href="https://www.ecmwf.int" target="_blank" rel="noopener">www.ecmwf.int</a>.
    This ECMWF data is published under a Creative Commons Attribution 4.0 International (CC BY 4.0) licence, <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">creativecommons.org/licenses/by/4.0</a>.
    ECMWF does not accept any liability whatsoever for any error or omission in the data, their availability, or for any loss or damage arising from their use.
    Changes made: precipitation de-accumulated, converted to mm, totalled per 6 hours and per 05:30–05:30 IST day, cropped to India, turned into ensemble counts and percentiles.</p>
    <p>Place names: <a href="https://www.geonames.org/" target="_blank" rel="noopener">GeoNames</a> (CC BY 4.0). Rain categories and probability words: India Meteorological Department terminology (not an IMD product).
    Basemap: <a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a> © <a href="https://openmaptiles.org" target="_blank" rel="noopener">OpenMapTiles</a> Data from <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>.
    Boundaries: Made with <a href="https://www.naturalearthdata.com" target="_blank" rel="noopener">Natural Earth</a> (India point of view).</p>
    <p><button class="btn" id="close-about">Close</button></p>`;
  $("close-about").onclick = () => $<HTMLDialogElement>("about").close();
}

// ---------- start ----------
// The answer's data gets the bandwidth first; the map follows when it has arrived, or after 1.5 s at most (D62).
let answerDataReady: () => void = () => undefined;
const ANSWER_DATA = new Promise<void>((ok) => { answerDataReady = ok; setTimeout(ok, 1500); });
const PRELOAD = preloadMap(ANSWER_DATA);

/** Place to open with: the URL's, else the last one seen on this device. */
function initialPlace(): { lat: number; lon: number; name: string } | null {
  if (view.lat !== undefined && view.lon !== undefined) return { lat: view.lat, lon: view.lon, name: view.name ?? "Selected point" };
  try {
    const last = JSON.parse(localStorage.getItem(LAST_PLACE) ?? "null");
    if (last && Number.isFinite(last.lat) && Number.isFinite(last.lon)) return last;
  } catch { /* storage unavailable */ }
  return null;
}

async function start(): Promise<void> {
  initSheet($("sheet"), $("handle"));
  initSearch();
  $("locate").onclick = locate;
  $("about-link").onclick = (e) => { e.preventDefault(); renderAbout(); $<HTMLDialogElement>("about").showModal(); };
  document.querySelectorAll<HTMLButtonElement>(".chip").forEach((b) => (b.onclick = () => { view.layer = b.dataset.layer as LayerId; renderAll(); }));
  document.querySelectorAll<HTMLButtonElement>("#models-seg button").forEach((b) =>
    (b.onclick = () => { view.models = b.dataset.mv as ModelView; renderAll(); }));
  void pingApi().then((s) => { apiState = s; if ($<HTMLDialogElement>("about").open) renderAbout(); });

  const first = initialPlace();
  // the answer never waits for the map; the map opens directly at the place (one set of tiles, no fly-in, D62)
  const mapReady = createMap("map", PRELOAD, first ? [first.lon, first.lat] : [80, 22], first ? 6.5 : 3.6).catch(() => null);
  meta = await loadMeta();
  kNow = currentBlock(meta, now());
  const fromUrl = view.block ? meta.blocks.findIndex((b) => blockKey(b) === view.block) : -1;
  sel = fromUrl >= Math.max(0, kNow ?? 0) ? fromUrl : kNow ?? 0;
  renderIssued();
  void mapReady.then((mp) => {
    if (!mp) { $("map").innerHTML = `<p class="map-fail card">The map didn’t load. The forecast in the panel still works.</p>`; return; }
    map = mp;
    map.once("idle", () => performance.mark("map-visible")); // first frame with basemap tiles drawn (speed check, D62)
    // inspection handle for checks like the disputed-label audit (D61); only with ?debug in the opening URL
    if (DEBUG) (window as unknown as { rtMap: MLMap }).rtMap = mp;
    map.on("click", (e: MapMouseEvent) => void setPlace(e.lngLat.lat, e.lngLat.lng, "Selected point"));
    if (place) placeMarker(place.lat, place.lon, false);
    void renderMap().catch(() => undefined);
  });
  if (first) return setPlace(first.lat, first.lon, first.name);
  renderAll();
  answerDataReady(); // no place yet: nothing else to wait for
  try {
    const perm = await navigator.permissions?.query({ name: "geolocation" as PermissionName });
    if (perm?.state === "granted") locate();
  } catch { /* no permissions API: wait for the user */ }
}

start().catch((e) => {
  $("sheet-body").innerHTML = `<p class="summary">Couldn’t load the forecast. Check your connection and reload.</p><p class="note">${esc(String(e))}</p>`;
});
