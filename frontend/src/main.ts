import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "./style.css";
import { Marker, type Map as MLMap, type MapMouseEvent } from "maplibre-gl";
import { API_BASE, REPO_URL } from "./config";
import { loadLayer, loadMeta, loadPlaces, loadTile, pingApi, type ApiState } from "./data";
import { cellCentre, cellIndex } from "./grid";
import { AMOUNT_BINS, CHANCE_BINS, amountBin, chanceBin, paintSlot } from "./layers";
import { createMap, rowsFor, showRain } from "./map";
import { searchPlaces } from "./search";
import { initSheet } from "./sheet";
import { blockKey, blockParts, currentBlock, dataStatus, formatIst } from "./time";
import type { Cell, Meta, Tile } from "./types";
import { parseState, stateToSearch, type LayerId, type ViewState } from "./url";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
const LAST_PLACE = "rain-trust:last-place";

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
  el.title = `ECMWF run ${meta.run_id.slice(8)} UTC on ${meta.run_id.slice(6, 8)}/${meta.run_id.slice(4, 6)}; products built ${formatIst(meta.processed_at_utc)}`;
}

function dayIndexOf(k: number): number {
  return meta.days.findIndex((d) => d.app_day === meta.blocks[k].app_day);
}

function renderLegend(): void {
  const el = $("legend");
  if (dataStatus(meta, new Date()) === "expired") { el.innerHTML = "<b>No current forecast</b>"; return; }
  const swatch = (color: string, short: string, long: string) =>
    `<span class="row"><i style="background:${color}"></i>${short}<span class="long">&nbsp;${long}</span></span>`;
  if (view.layer === "chance") {
    el.innerHTML = `<b>Chance of ≥ 2.5 mm · ${esc(meta.blocks[sel].label)}</b><div class="swatches">` +
      CHANCE_BINS.map((b) => swatch(b.color, b.label.split(" (")[1].replace(")", ""), b.label.split(" (")[0].toLowerCase())).join("") +
      `</div><div class="note">Forecasts of 100 with ≥ 2.5 mm. Under 25: no colour. Faded = forecast unsettled.</div>`;
  } else {
    const d = dayIndexOf(sel);
    const title = d < 0 ? "Day total · not available for this part-day" : `Day total · ${esc(meta.days[d].label)}`;
    el.innerHTML = `<b>${title}</b><div class="swatches">` +
      AMOUNT_BINS.map((b) => swatch(b.color, b.label.split(" (")[0], `(${b.label.split(" (")[1]}`)).join("") +
      `</div><div class="note">Median of 100 forecasts, IMD categories. Same for every block of the day.</div>`;
  }
}

async function renderMap(): Promise<void> {
  if (!map) return;
  const g = meta.grid;
  if (dataStatus(meta, new Date()) === "expired") { showRain(map, g, null); return; }
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
    html += `<button class="tb${dayStart ? " daystart" : ""}" data-k="${k}" aria-pressed="${k === sel}"
      aria-label="${esc(meta.blocks[k].label)}: ${n} of 100 forecasts give at least 2.5 mm">
      <span class="now">${k === kNow ? "now" : ""}</span><span class="bar${n >= 25 ? " wet" : ""}" style="height:${Math.max(2, n * 0.34)}px"></span>
      <span class="n">${n}</span><span class="d">${p.day} ${p.name.slice(0, 3)}</span><span class="t">${p.start}</span></button>`;
  }
  return `<div class="timeline" id="timeline" aria-label="Chance of at least 2.5 mm per 6-hour block, of 100 forecasts">${html}</div>`;
}

function renderSheet(): void {
  const body = $("sheet-body");
  const status = dataStatus(meta, new Date());
  if (!place) {
    body.innerHTML = `<h2 class="place">Will it rain where you are?</h2>
      <p class="summary">Search for a place in India, tap the map, or use your location.</p>
      <div><button class="btn dark" id="use-loc">Use my location</button></div>
      <p class="note">100 forecasts from ECMWF: 50 from the physics model (IFS) and 50 from the AI model (AIFS).</p>`;
    $("use-loc").onclick = locate;
    return;
  }
  const head = `<h2 class="place">${esc(place.name)}</h2>`;
  if (placeError === "outside") {
    body.innerHTML = `${head}<p class="summary">We cover India and nearby areas (6.5–37.25 N, 68–97.5 E). This point is outside.</p>`;
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
  const sub = `<p class="sub">Next 48 hours · grid point ${c.lat.toFixed(2)} N, ${c.lon.toFixed(2)} E</p>`;
  if (status === "expired" || kNow === null) {
    body.innerHTML = `${head}<p class="summary">Forecast out of date. The newest forecast we have was issued ${formatIst(meta.processed_at_utc)}, more than 72 hours ago. We don’t show old numbers as a forecast.</p>`;
    return;
  }
  const settled = S[cell.bt[sel][1]];
  body.innerHTML = `${head}${sub}
    <p class="summary">${esc(S[cell.s[kNow]])}</p>
    <p class="block-answer">${esc(S[cell.bt[sel][0]])}</p>
    <p class="pill ${settled.startsWith("Forecast settled.") ? "settled" : "unsettled"}">${esc(settled)}</p>
    ${timelineHtml(cell)}
    <p class="note">Each 6-hour block counts how many of 100 forecasts give at least 2.5 mm. Days run 05:30–05:30 IST.</p>`;
  $("timeline").querySelectorAll<HTMLButtonElement>(".tb").forEach((b) => (b.onclick = () => selectBlock(Number(b.dataset.k))));
  const tl = $("timeline"), pressed = tl.querySelector<HTMLElement>('[aria-pressed="true"]');
  if (pressed) tl.scrollLeft = pressed.offsetLeft - tl.offsetLeft - tl.clientWidth / 2 + pressed.clientWidth / 2; // sideways only
}

function syncUrl(): void {
  view = { ...view, lat: place?.lat, lon: place?.lon, name: place?.name, block: blockKey(meta.blocks[sel]) };
  history.replaceState(null, "", `${location.pathname}${stateToSearch(view)}`);
}

function renderAll(): void {
  renderLegend();
  renderSheet();
  void renderMap().catch(() => showRain(map!, meta.grid, null));
  document.querySelectorAll<HTMLButtonElement>(".chip").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.layer === view.layer)));
  syncUrl();
}

// ---------- actions ----------
function selectBlock(k: number): void {
  sel = k;
  renderAll();
}

async function setPlace(lat: number, lon: number, name: string): Promise<void> {
  place = { lat, lon, name };
  cellData = null;
  placeError = null;
  placeMarker(lat, lon);
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
}

function placeMarker(lat: number, lon: number): void {
  marker?.remove();
  if (!map) return;
  const el = document.createElement("div");
  el.className = "marker";
  marker = new Marker({ element: el }).setLngLat([lon, lat]).addTo(map);
  const phone = innerWidth < 1024;
  map.flyTo({ center: [lon, lat], zoom: Math.max(map.getZoom(), 6.5),
    padding: { bottom: phone ? innerHeight * 0.4 : 0, top: phone ? 150 : 0, left: 0, right: 0 } });
}

function locate(): void {
  if (!navigator.geolocation) return;
  navigator.geolocation.getCurrentPosition(
    (p) => void setPlace(p.coords.latitude, p.coords.longitude, "Your location"),
    () => { /* denied or unavailable: search and map tap still work; no nagging */ },
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
      : `<li class="none">No place called “${esc(text)}” in our list of Indian places.</li>`;
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
async function start(): Promise<void> {
  initSheet($("sheet"), $("handle"));
  initSearch();
  $("locate").onclick = locate;
  $("about-link").onclick = (e) => { e.preventDefault(); renderAbout(); $<HTMLDialogElement>("about").showModal(); };
  document.querySelectorAll<HTMLButtonElement>(".chip").forEach((b) => (b.onclick = () => { view.layer = b.dataset.layer as LayerId; renderAll(); }));
  void pingApi().then((s) => { apiState = s; if ($<HTMLDialogElement>("about").open) renderAbout(); });

  const mapReady = createMap("map").catch(() => null); // the answer never waits for the map
  meta = await loadMeta();
  kNow = currentBlock(meta, new Date());
  const fromUrl = view.block ? meta.blocks.findIndex((b) => blockKey(b) === view.block) : -1;
  sel = fromUrl >= Math.max(0, kNow ?? 0) ? fromUrl : kNow ?? 0;
  renderIssued();
  void mapReady.then((mp) => {
    if (!mp) return;
    map = mp;
    map.on("click", (e: MapMouseEvent) => void setPlace(e.lngLat.lat, e.lngLat.lng, "Selected point"));
    if (place) placeMarker(place.lat, place.lon);
    void renderMap().catch(() => undefined);
  });
  if (view.lat !== undefined && view.lon !== undefined) return setPlace(view.lat, view.lon, view.name ?? "Selected point");
  let last: { lat: number; lon: number; name: string } | null = null;
  try { last = JSON.parse(localStorage.getItem(LAST_PLACE) ?? "null"); } catch { last = null; }
  if (last && Number.isFinite(last.lat) && Number.isFinite(last.lon)) return setPlace(last.lat, last.lon, last.name);
  renderAll();
  try {
    const perm = await navigator.permissions?.query({ name: "geolocation" as PermissionName });
    if (perm?.state === "granted") locate();
  } catch { /* no permissions API: wait for the user */ }
}

start().catch((e) => {
  $("sheet-body").innerHTML = `<p class="summary">Couldn’t load the forecast. Check your connection and reload.</p><p class="note">${esc(String(e))}</p>`;
});
