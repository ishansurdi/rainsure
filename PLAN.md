# PLAN.md — rain-trust

Clock started: 2026-11-05 ~04:00 UTC (09:30 IST), first prompt of the session.
Hard deadline: final commit by **2026-11-08 04:00 UTC (09:30 IST)**.
Deliverables: public repo, live app, video.
Status: approved; P0 and P1 done, P2 in progress.

## Status
- [x] CLAUDE.md committed
- [x] ECMWF Open Data facts checked (section below)
- [x] Plan approved by author; open questions answered (2026-11-05, two reviews)
- [x] P0: `common/config.py`, `common/time.py` + 12 tests (stdlib only)
- [x] P0: `common/units.py`, `common/grid.py` + tests; Python 3.12 conda env `rainsure` (PYTHONNOUSERSITE=1), pins in requirements-pipeline.txt; 22 tests OK
- [x] P1 runner checks: fetch 7–9 MB/s, ~5 min per run (D36); AWS eu-central-1 works, Google fastest (D34); Linux pulls eccodeslib + eckitlib, pinned for Linux; archive ~65 MB per run (D47)
- [x] P1 archive: Actions job every 3 h saves each 00z/12z run (tp, 50 members, India) to release `archive`; 8 runs saved from 20261101 12z
- [x] P1 validation before upload (D48); a bad run is not uploaded and is retried. "Keep serving the previous run" is part of the publish step (P2/P5)
- [ ] P2 process: de-accumulate (D46 clip + log), 6-h and day totals, probabilities, agreement, stability, confidence, template sentence

## Verified data facts (checked 2026-11-05)
Sources: [OD] https://www.ecmwf.int/en/forecasts/datasets/open-data ·
[CF] https://confluence.ecmwf.int/display/DAC/ECMWF+open+data%3A+real-time+forecasts+from+IFS+and+AIFS ·
[GH] https://github.com/ecmwf/ecmwf-opendata ·
[LIVE] directory listings and `.index` files on https://data.ecmwf.int/forecasts/20261104/

| | IFS ens (`ifs/0p25/enfo`) | AIFS ens (`aifs-ens/0p25/enfo`) | IFS HRES (`ifs/0p25/oper`) | AIFS single |
|---|---|---|---|---|
| Runs (UTC) | 00/06/12/18 [CF][LIVE] | 00/06/12/18 [OD][LIVE] | 00/06/12/18 | 00/06/12/18 |
| Steps 00/12z | 0–144 by 3, 150–360 by 6 [OD][LIVE: 85 files] | 0–360 by 6 [OD][LIVE: 61 files] | same as IFS ens [LIVE] | 0–360 by 6 [LIVE] |
| Steps 06/18z | 0–144 by 3 [OD][LIVE: 49 files] | 0–360 by 6 [OD] | 0–144 by 3 [LIVE]; CF/GH say 90 h — **outdated** | 0–360 by 6 |
| Members with `tp` | 50 perturbed (`pf` 1–50) only; **no `cf` at 0.25°** (index types at steps 0/24/150 are all `pf`) [LIVE] | 50 `pf` + 1 `cf` [LIVE index] | 1 | 1 |
| `tp` units (GRIB `units` key) | **`m`** [LIVE decode] | **`kg m**-2` = mm** [LIVE decode] | `m` | not decoded |
| Grid / format | 0.25° GRIB2 (0.1° also from 2026-10-20) [OD] | 0.25° only, GRIB2 [OD] | 0.25° / 0.1° | 0.25° |
| `tp` field size | ~400 KB per global field [LIVE `_length`] | ~450 KB | ~390 KB | ~365 KB |
| `ep` probabilities | 00/12z only [OD][GH][LIVE: none at 06z] | present at 00z [LIVE] | – | – |

- `tp` accumulation, verified by ecCodes decode of 20261104 00z member 1 (+AIFS control), steps 6/24/48: both models `stepType=accum`, `stepRange=0-6/0-24/0-48`, PDT 4.11, `typeOfStatisticalProcessing=1` → accumulated from forecast start.
- **Units differ: IFS `m`, AIFS `kg m**-2` (mm).** GH's "m" applies to IFS only. Convert by reading the GRIB `units` key; unknown unit → error.
- Differencing gives small negatives (GRIB packing): IFS down to −0.122 mm (24→48 h, and 6→12 h in the India crop); AIFS −0.03/−0.06 mm. Corrected 2026-11-05: an earlier version of this line said "IFS ≥ −0.06 mm", which was wrong. Tolerance comes from `packingError` (D46).
- Grid 721×1440, first point lat 90, **lon 180**, 0.25° → normalise longitudes before cropping.
- Measured download, 10 days, 6-hourly, tp only, byte ranges (20261104): **00z 2,225 MB** (IFS 994 + AIFS 1,091 tp; 140 MB index files; 4,160 requests); **12z 2,371 MB** (4,368 requests). Global fields: cropping happens after download.
- Retention: "most recent 12 forecast runs ... approximately 2–3 days" [OD]. LIVE showed 4 date folders on 5 Nov. → **Past forecasts must be archived by us** for any verification.
- Release delay: "7 and 9 hours after" run start [GH]; AIFS released as soon as produced [OD].
- Download: `.index` files give `_offset`/`_length` per field → HTTP byte-range fetch of `tp` only [LIVE].
- Limits: 500–2000 simultaneous connections [OD][CF]; GH says 500. Retry on 429/5xx [GH].
- Licence: CC-BY-4.0 + ECMWF Terms of Use [OD]. Attribution wording still to read on the ECMWF terms page.
- **Consequence for IMD day (03 UTC boundaries):** AIFS (all steps) and IFS beyond 144 h are 6-hourly at 00/06/12/18 UTC valid times. A 03–03 UTC total **cannot be computed** from them. See open question Q1.

## Phases (draft; hours from clock start)
| Phase | Hours | Done when |
|---|---|---|
| P0 Skeleton | 0–4 | repo layout, pinned deps, `common/{config,time,units,grid}` + tests pass |
| P1 Ingest | 4–12 | byte-range fetch of `tp` (India crop) for IFS-ens + AIFS-ens; validation (NaN, negatives, members, freshness); tp accumulation verified |
| P1b Archive on | by 14 | scheduled job running every run, so stability and verification have history |
| P2 Process | 12–26 | de-accumulate → daily totals → P(≥ thresholds), mean/percentiles, IFS–AIFS agreement, run-to-run change, confidence + template sentence; tests with hand-computed arrays |
| P3 API | 26–32 | FastAPI: `/point`, `/layer`, `/meta`; every response carries model, run UTC, steps, processed time |
| P4 Frontend | 32–52 | answer card, MapLibre globe→flat, chips, timeline, details, split slider; phone + desktop screenshots |
| P5 Deploy | 52–60 | live URL, scheduled refresh, bad run → keep previous |
| P6 Verification (stretch) | 60–66 | IMERG vs archived forecasts for days we have |
| P7 Ship | 66–72 | README, video, final commit; 4 h buffer is inside this |

## Cut list (in this order)
1. IMERG verification (P6) → show "verification starts accumulating" note instead.
2. Split slider → simple IFS / AIFS toggle.
3. Globe at low zoom → flat map only.
4. Lead time 10 → 5 days.
5. Question chips → fixed layer list.

Never cut: correct de-accumulation, IST labels, units, the probabilities, IFS–AIFS agreement, honest "missing data" states.

## Credits (app footer + README) — D37
- **ECMWF** (required by https://apps.ecmwf.int/datasets/licences/general/, "service" wording): "This service is based on data and products of the European Centre for Medium-Range Weather Forecasts (ECMWF)." · Source: www.ecmwf.int · "This ECMWF data is published under a Creative Commons Attribution 4.0 International (CC BY 4.0). https://creativecommons.org/licenses/by/4.0/" · Disclaimer: "ECMWF does not accept any liability whatsoever for any error or omission in the data, their availability, or for any loss or damage arising from their use." · Modifications: precipitation de-accumulated, converted to mm, aggregated to 6-h/24-h totals, cropped to India, turned into ensemble statistics. Displayed prominently, not hidden.
- **GeoNames** (CC BY 4.0): place names from GeoNames, https://www.geonames.org/
- **IMD**: rainfall categories and probability terms from IMD terminology (Ahmedabad bulletin 2026-11-04, RSMC New Delhi terminology). Not an IMD product.
- **Basemap**: "OpenFreeMap © OpenMapTiles Data from OpenStreetMap" with links (MapLibre adds it automatically).
- **Natural Earth**: "Made with Natural Earth" (optional, public domain; we credit anyway).
- **NASA IMERG**: added when verification ships.

## Open questions
See conversation 2026-11-05; answers recorded in DECISIONS.md.
