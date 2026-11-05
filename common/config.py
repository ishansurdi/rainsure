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
}
SOURCE_ORDER: tuple[str, ...] = ("google", "ecmwf")


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


class Box(NamedTuple):
    """Lat/lon box in degrees; longitudes in [-180, 180)."""

    west: float
    east: float
    south: float
    north: float


# India box: Natural Earth ne_10m_admin_0_countries_ind v5.1.1 India extent
# (68.14-97.36 E, 6.75-37.05 N, checked 2026-11-05) rounded outward to the 0.25 deg grid (DECISIONS.md D39).
INDIA_BOX = Box(west=68.0, east=97.5, south=6.5, north=37.25)
