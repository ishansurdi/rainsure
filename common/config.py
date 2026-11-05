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


class Box(NamedTuple):
    """Lat/lon box in degrees; longitudes in [-180, 180)."""

    west: float
    east: float
    south: float
    north: float


# India box: Natural Earth ne_10m_admin_0_countries_ind v5.1.1 India extent
# (68.14-97.36 E, 6.75-37.05 N, checked 2026-11-05) rounded outward to the 0.25 deg grid (DECISIONS.md D39).
INDIA_BOX = Box(west=68.0, east=97.5, south=6.5, north=37.25)
