# DECISIONS.md

One line per decision: date | decision | reason | alternative rejected.

- 2026-11-05 | Keep PLAN.md and DECISIONS.md at the repo root | CLAUDE.md §9 reads them first on every task | a docs/ folder (harder to find)

## 2026-11-05 — review of plan (author-approved unless marked PROPOSED)

### Time windows
- D1 | App day = 00–00 UTC = 05:30–05:30 IST, split into four 6-h blocks (05:30–11:30, 11:30–17:30, 17:30–23:30, 23:30–05:30 IST) | AIFS (all steps) and IFS >144 h exist only at 00/06/12/18 UTC, so a 03 UTC IMD-day total cannot be computed; one window for both models keeps the comparison fair | IMD day (impossible for AIFS); mixed IMD/00 UTC days (unfair comparison); interpolating to 03 UTC (invents values, CLAUDE.md §6). CLAUDE.md §4 line updated accordingly.
- D2 | Daily/event probabilities are computed per member (sum the member's blocks, then count members over threshold) | summing per-block probabilities is mathematically wrong | –
- D3 | Day/block logic is written for any run hour: 00z run → day boundaries at steps 0, 24, 48…; 12z run → 12, 36, 60…, with a partial first day (blocks at steps 0–6, 6–12) | data comes from both 00z and 12z runs | 00z-only logic
- D4 | Blocks already over at view time are greyed and labelled "past — not a forecast"; a block in progress is labelled "started HH:MM IST"; today's total is shown as "rest of today from HH:MM IST", built from remaining blocks only | data arrives 7–9 h after run start [GH], so day 1 is partly past | showing past blocks as forecasts
- D5 | Block labels always carry explicit times and dates, e.g. "Thu night · 23:30 Thu – 05:30 Fri IST" | a night block crosses midnight; IMD's own part-of-day terms differ (IMD "Night" = 20:00–24:00 IST, RSMC terminology), so names alone would mislead | names without times
- D6 | No IMD-day view for now | author decision | IFS-only IMD-day panel

### Data
- D7 | Runs: 00z and 12z only; stability compares against the previous run (00z vs previous 12z, 12z vs same-day 00z) | full 360 h range and half the downloads | all four runs
- D8 | Members: IFS-ens 50 `pf` and AIFS-ens 50 `pf`; AIFS `cf` not used | IFS publishes no control at 0.25° (verified); equal 50 vs 50 keeps "N of 50" comparable | 51 vs 50
- D9 | Convert `tp` using the GRIB `units` key per message: `m` → ×1000, `kg m**-2` → ×1, anything else → error | verified: IFS stores `m`, AIFS stores `kg m**-2` | assume metres for both (would make AIFS 1000× too large)
- D10 | De-accumulate by differencing consecutive 6-h steps; clip negatives ≥ −0.1 mm to 0 and log the count; any value < −0.1 mm fails the run | observed packing negatives down to −0.0625 mm | silent clipping of everything
- D11 | Lead time 10 days, 6-hourly steps: measured 2.23 GB (00z) / 2.37 GB (12z) per run, ~4,200 byte-range requests, low concurrency (≤ 8, far below the 500-connection limit [OD/GH]) | measured, not estimated; fits a GitHub runner (14 GB SSD, 6 h job limit) | downloading full GRIB files. Fallback if too slow: day-only steps (~¼ of the volume)
- D12 | Normalise longitudes (grid starts at lon 180) before cropping to the India box; box values live in config.py | verified grid header | crop on raw 0–360 indices
- D13 | `--ssl-no-revoke` was used only with curl on this Windows machine to read public listings (CRYPT_E_REVOCATION_OFFLINE). Never in pipeline code: Python/requests use normal TLS verification | security | disabling verification in code

### Confidence and wording
- D14 | Confidence = points from three checks: decided probability, models agree, stable since last run. 3 = high, 2 = medium, 0–1 = low. The sentence names each failed check ("models disagree") | an all-or-nothing rule would make almost everything "low" | high/low only
- D15 | PROPOSED thresholds (config.py): decided = P(rain ≥ 2.5 mm) < 20 % or > 80 %; agree = |P_IFS − P_AIFS| < 20 points; stable = |P_now − P_prev| < 20 points. No previous run → check counts as not passed and the sentence says "no earlier run to compare" | 2.5 mm = IMD "rainy day" (IMD Pune glossary p.4) | –
- D16 | Rain categories, lower bounds in mm per 24 h: very light > 0 (trace) – 2.4, light 2.5, moderate 15.6, heavy 64.5, very heavy 115.6, extremely heavy 204.5 | IMD Ahmedabad state bulletin 2026-11-04 legend (https://mausam.imd.gov.in/ahmedabad/mcdata/state.pdf, p.3) and RSMC New Delhi terminology (https://rsmcnewdelhi.imd.gov.in/images/pdf/terminology.pdf, pp.3–7) agree | IMD Pune glossary (https://imdpune.gov.in/Reports/glossary.pdf) has older bands (moderate 7.6–35.5, heavy 64.5–124.4)
- D17 | Probability words from IMD: Unlikely < 25 %, Likely 25–50 %, Very likely 50–75 %, Most likely > 75 % | same IMD bulletin legend p.3 | inventing our own words
- D18 | Categories are applied to our 05:30–05:30 IST totals and labelled "IMD categories applied to 05:30–05:30 IST totals" | IMD defines them for 24 h ending 08:30 IST | calling it an IMD product

### Hosting and data publishing
- D19 | Pipeline runs on GitHub Actions (cron) and publishes products to GitHub Pages via the deploy-pages artifact; nothing data-related is committed to git | Pages sends `Access-Control-Allow-Origin: *` (tested); free for public repos; 1 GB site, 100 GB/month soft limit [GitHub Pages limits doc] | release assets: no CORS header (tested), so the browser cannot read them; Render cron: $1/month minimum [render.com/docs/cronjobs]
- D20 | Each deploy replaces the whole Pages site, so the pipeline first downloads the previous products from the live site (needed for stability). Long-term per-run archive for verification goes to release assets (pipeline-only, no CORS needed; < 2 GiB/file, 1000 assets/release) | keeps history without committing data | Actions artifacts (expire)
- D21 | (frontend part superseded by D30) FastAPI = Render free web service; frontend = Render free static site; no Render Postgres (expires after 30 days); no data on Render disk (ephemeral) [render.com/docs/free] | author decision | –
- D22 | Frontend loads map data straight from Pages and pings the API on page open; API fetches latest products from Pages and caches them in memory | free web service spins down after 15 min idle, ~1 min to wake [render.com/docs/free] | frontend depending on the API for first paint
- D23 | Keep Render traffic small: map data never goes through Render; the frontend bundle stays light | Hobby workspace has 5 GB/month outbound shared by all services; if exceeded with no card, services spin down until next month [render.com/docs/outbound-bandwidth, /docs/free] | serving data through the API
- D24 | Repo must be public for free Pages and free Actions minutes | GitHub docs | private repo (would need a paid plan)
- D25 | README notes: public-repo scheduled workflows are disabled after 60 days with no repo activity | GitHub "events that trigger workflows" doc | –

### Location search
- D26 | Place search from a static file built from GeoNames cities1000 (India: 7,229 places, all with a state name) → [name, state, lat, lon]; 287 kB JSON, 91 kB gzip; built by a script in the repo; GeoNames CC-BY 4.0 attribution in the app | no external API; spot-checked Pune, Mumbai, Chennai, Leh, Port Blair, Kavaratti | geocoding API; cities15000 (3,787 places, drops small towns)

### Secrets and verification
- D27 | `NASA_TOKEN` is read only from the environment; `.env` is git-ignored (fixed today: it was not ignored, never tracked); the token goes into GitHub and Render as secrets; never printed, logged or committed; the agent never reads `.env` | author rule | –
- D28 | IMERG verification is built last (stretch) | author decision | –

## 2026-11-05 — second review
- D15 approved as proposed (20 % / 80 %, 20 points, 20 points; event = rain ≥ 2.5 mm).
- D29 | Headline pools both ensembles (100 members). Pooling assumes **equal weight** for IFS and AIFS. If the agreement check fails, the headline does not show the pooled number; it says the models disagree and shows both ("Models disagree: physics 34 of 50, AI 6 of 50") | pooling would hide the disagreement the app is about | pooled number always; IFS-only headline
- D30 | Frontend is hosted on GitHub Pages together with the data; only FastAPI runs on Render | Render's 5 GB/month outbound is shared by all services; Pages has 100 GB/month soft, no spin-down, CDN, same origin as data (no CORS needed). Cost: each Pages deploy replaces the whole site, so the pipeline workflow must deploy frontend + data together, and a frontend change triggers that same workflow | Render static site (eats the shared 5 GB)
- D31 | Basemap = OpenFreeMap vector tiles (style e.g. https://tiles.openfreemap.org/styles/positron; OpenMapTiles schema): no key, no registration, no request limits stated; "as-is", no SLA, may be discontinued [openfreemap.org, /tos]. If tiles fail, the app still works on a plain background with our own boundaries | simplest: one style URL | self-hosted PMTiles on Pages (needs a build step and the pmtiles tool, planet is ~120 GB so an extract is needed, eats the 1 GB Pages limit, Pages range-request support unverified)
- D32 | Hide all basemap boundary layers; draw boundaries from Natural Earth `ne_10m_admin_0_countries_ind` v5.1.1 (India point of view, de jure). Verified: only the 10m scale exists (50m/110m 404); India extends to 37.05° N in the IND file vs 35.5° N default; public domain [naturalearthdata.com/about/terms-of-use]. File is 13.2 MB, so it is simplified and clipped in a build step (tool to be proposed before the frontend phase) | matches India's official map | basemap borders; NE default (de facto) boundaries
- D33 | ecCodes (2.50.0) is a pipeline-only dependency. The Render API reads processed products only, no GRIB code; separate requirement files for pipeline and API | keep the API light | one shared requirements file
- D34 | Fetch from the Google Cloud mirror (https://storage.googleapis.com/ecmwf-open-data), fallback data.ecmwf.int. Verified: index file byte-identical (same MD5); range requests return the same 110.5 MB. AWS (`ecmwf-forecasts` eu-central-1) timed out from this machine and its global endpoint returned 503; re-test from Actions in P1 | less load on ECMWF's connection limit | ECMWF only
- D35 | Fetching uses the standard library (urllib, byte ranges, retry) instead of the `ecmwf-opendata` package | working code exists from the checks; avoids a dependency (CLAUDE.md §5) | ecmwf-opendata client
- D36 | Fetch time: on this machine 2.1 MB/s (ECMWF) and 2.5 MB/s (Google) with 8 workers → a full run would take ~15–18 min here. Real time is measured on a GitHub runner as the first job in P1; lead time / step choice is revisited if it is over ~30 min | local network is not the runner | –
- D37 | Credits in app footer and README (see PLAN.md "Credits") | licence obligations (ECMWF CC-BY-4.0 terms, GeoNames CC-BY 4.0, OpenFreeMap/OpenMapTiles/OSM) and sources we rely on (IMD, Natural Earth) | –
