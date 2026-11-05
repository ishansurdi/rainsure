"""All project constants, each with its source (CLAUDE.md §4)."""

from datetime import timedelta
from typing import NamedTuple

# Indian Standard Time is UTC+05:30 (fixed offset, no daylight saving).
IST_OFFSET = timedelta(hours=5, minutes=30)

# Runs we use: 00z and 12z only (DECISIONS.md D7). Both reach 360 h for IFS-ens and AIFS-ens
# (verified on data.ecmwf.int listings for 20261104, PLAN.md "Verified data facts").
RUN_HOURS_UTC: tuple[int, ...] = (0, 12)

# Block length: AIFS-ens (all steps) and IFS-ens beyond 144 h are only 6-hourly
# (ECMWF open data page + live listings, PLAN.md). DECISIONS.md D1.
BLOCK_HOURS = 6

# App day runs 00:00-00:00 UTC = 05:30-05:30 IST (DECISIONS.md D1).
DAY_START_HOUR_UTC = 0

# Block names keyed by block start hour in UTC (DECISIONS.md D1, D5):
# 00 UTC = 05:30 IST, 06 UTC = 11:30 IST, 12 UTC = 17:30 IST, 18 UTC = 23:30 IST.
# Labels always carry explicit times because IMD part-of-day terms differ
# (RSMC New Delhi terminology: "Night" = 2000-2400 IST).
BLOCK_NAMES_BY_START_HOUR_UTC: dict[int, str] = {0: "morning", 6: "afternoon", 12: "evening", 18: "night"}

# Lead time shown in the app, in full app days after the run's first day boundary (DECISIONS.md D11).
LEAD_DAYS = 10

# Factor from the GRIB `units` key of `tp` to mm (DECISIONS.md D9). Verified by ecCodes decode of
# 20261104 00z: IFS-ens tp units = "m", AIFS-ens tp units = "kg m**-2" (1 kg/m2 of water = 1 mm).
TP_UNIT_TO_MM: dict[str, float] = {"m": 1000.0, "kg m**-2": 1.0}


# --- Data sources (DECISIONS.md D34): same paths and bytes on both (index MD5 + 110.5 MB range test, 2026-11-05).
SOURCE_URLS: dict[str, str] = {
    "google": "https://storage.googleapis.com/ecmwf-open-data",
    "ecmwf": "https://data.ecmwf.int/forecasts",
    # AWS mirrors (ECMWF open data page): only timed by ingest/runner_checks.py, not used for downloads (D34).
    "aws-eu-central-1": "https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com",
    "aws": "https://ecmwf-forecasts.s3.amazonaws.com",
}
SOURCE_ORDER: tuple[str, ...] = ("google", "ecmwf")
MIRROR_CHECK_TIMEOUT_S = 60  # one attempt per mirror in the runner checks; a slow mirror should show as slow


class ModelSpec(NamedTuple):
    """Where a model's ensemble files live on the open-data server."""

    directory: str  # path under {date}/{HH}z/
    file_type: str  # last part of the file name, e.g. ...-24h-enfo-ef.grib2
    member_type: str  # GRIB `type` of the members we use


# Verified on live listings and .index files for 20261104 (PLAN.md facts): IFS members are in `-enfo-ef`
# files with type pf; AIFS members in `-enfo-pf` files with type pf. Control members not used (D8).
MODELS: dict[str, ModelSpec] = {
    "ifs-ens": ModelSpec(directory="ifs/0p25/enfo", file_type="ef", member_type="pf"),
    "aifs-ens": ModelSpec(directory="aifs-ens/0p25/enfo", file_type="pf", member_type="pf"),
}
EXPECTED_MEMBERS = 50  # perturbed members 1..50 for both models (live index files, D8)

# --- HTTP (DECISIONS.md D40). Retry codes follow the ecmwf-opendata client's list (github.com/ecmwf/ecmwf-opendata).
HTTP_TIMEOUT_S = 60
HTTP_MAX_ATTEMPTS = 6
HTTP_BACKOFF_BASE_S = 2.0  # waits 2, 4, 8, 16, 32 s unless the server sends Retry-After
HTTP_RETRY_STATUS: frozenset[int] = frozenset({408, 429, 500, 502, 503, 504})
HTTP_WORKERS = 8  # parallel downloads; far below the 500-connection limit (ECMWF open data page)
HTTP_USER_AGENT = "rain-trust/0.1 (+https://github.com/ishansurdi/rainsure)"


class GridSpec(NamedTuple):
    """Regular lat/lon grid as stored in the GRIB message (scanning west->east, north->south)."""

    ni: int
    nj: int
    lat_first: float
    lon_first: float
    step_deg: float


# GRIB header of IFS-ens and AIFS-ens tp, verified by ecCodes decode of 20261104 00z:
# 1440 x 721 points, first point lat 90 / lon 180, 0.25 deg, iScansNegatively=0, jScansPositively=0.
SOURCE_GRID = GridSpec(ni=1440, nj=721, lat_first=90.0, lon_first=180.0, step_deg=0.25)

# Archive: runs to look back for. ECMWF keeps "the most recent 12 forecast runs ... approximately 2-3 days"
# (ecmwf.int open-data page); 4 date folders were seen live on 2026-11-05, so look back 4 days.
ARCHIVE_LOOKBACK_H = 96

# Plausibility ceiling for one 6-h block (mm): the world's greatest 12-hour point rainfall, 1144 mm, Foc-Foc,
# La Reunion, 7-8 Jan 1966 (WMO "Records of Weather and Climate Extremes" table, as of 31 July 2025,
# https://wmo.int/sites/default/files/2025-07/Table_Records_25Jul2025.pdf). A 0.25 deg grid-box 6-h value above
# this is a decoding or unit error, not weather.
MAX_RAIN_6H_MM = 1144.0

# --- Rain thresholds (mm, inclusive lower bounds).
# Event "rain" = 2.5 mm: IMD rainy day (IMD Pune glossary p.4); also IMD "light" lower bound (D15, D16).
EVENT_MM = 2.5
# Day totals use IMD 24-h category lower bounds: light 2.5, moderate 15.6, heavy 64.5 mm (IMD Ahmedabad state
# bulletin 2026-11-04 legend p.3; RSMC New Delhi terminology pp.3-7; DECISIONS.md D16).
DAY_THRESHOLDS_MM: tuple[float, ...] = (2.5, 15.6, 64.5)
# 6-h blocks use only the event threshold: IMD categories are defined for 24 h, so e.g. 64.5 mm in 6 h is not
# IMD "heavy" (DECISIONS.md D49).
BLOCK_THRESHOLDS_MM: tuple[float, ...] = (EVENT_MM,)

# --- Confidence checks on P(rain >= EVENT_MM), in percent / percentage points (DECISIONS.md D14, D15; strict bounds).
DECIDED_BELOW_PCT = 20.0  # decided if P < 20 % ...
DECIDED_ABOVE_PCT = 80.0  # ... or P > 80 %
AGREE_MAX_DIFF_PCT = 20.0  # models agree if |P_IFS - P_AIFS| < 20 points
STABLE_MAX_DIFF_PCT = 20.0  # stable if |P_now - P_previous run| < 20 points
CONFIDENCE_BY_POINTS: dict[int, str] = {0: "low", 1: "low", 2: "medium", 3: "high"}
# What users read for each level: how settled the forecast is, kept apart from the chance of rain (DECISIONS.md D51).
SETTLED_TEXT_BY_POINTS: dict[int, str] = {0: "Forecast unsettled", 1: "Forecast unsettled",
                                          2: "Forecast fairly settled", 3: "Forecast settled"}

# --- IMD probability words (IMD Ahmedabad state bulletin 2026-11-04 legend p.3): Unlikely "less than 25%",
# Likely "25% to 50%", Very likely "50% to 75 %", Most likely "more than 75%". IMD's ranges share 50 %; we give it
# to the weaker word (DECISIONS.md D50). So: [0, 25) unlikely, [25, 50] likely, (50, 75] very likely, (75, 100] most.
LIKELY_FROM_PCT = 25.0
VERY_LIKELY_ABOVE_PCT = 50.0
MOST_LIKELY_ABOVE_PCT = 75.0

# --- IMD 24-h rain categories, lower bounds in mm (D16 sources), applied to the displayed value rounded to 0.1 mm.
# Below 0.1 mm (shown as 0.0) there is no category: a 0.0 median can hide up to 49 wet forecasts, so the sentence
# counts forecasts instead (D51). IMD "very light" is trace-2.4 mm.
RAIN_CATEGORIES_MM: tuple[tuple[float, str], ...] = (
    (204.5, "extremely heavy rain"), (115.6, "very heavy rain"), (64.5, "heavy rain"),
    (15.6, "moderate rain"), (2.5, "light rain"), (0.1, "very light rain"),
)
NEXT_HOURS_BLOCKS = 8  # 48-h summary on the answer card = 8 six-hour blocks


class Box(NamedTuple):
    """Lat/lon box in degrees; longitudes in [-180, 180)."""

    west: float
    east: float
    south: float
    north: float


# India box: Natural Earth ne_10m_admin_0_countries_ind v5.1.1 India extent
# (68.14-97.36 E, 6.75-37.05 N, checked 2026-11-05) rounded outward to the 0.25 deg grid (DECISIONS.md D39).
INDIA_BOX = Box(west=68.0, east=97.5, south=6.5, north=37.25)
