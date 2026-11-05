"""rain-trust API: precipitation answers for a point in India from the published ECMWF ensemble products.

Run locally: uvicorn api.main:app --reload   (docs at /docs). Reads only published JSON (DECISIONS.md D42, D52).
"""

import urllib.error
from datetime import datetime, timezone
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api.data import Store, cell_index, current_block, data_status
from common import config

app = FastAPI(
    title="rain-trust API",
    version="0.1.0",
    summary="Rain chances for India from 100 ECMWF forecasts (IFS physics ensemble + AIFS AI ensemble).",
    description=("All times UTC in fields named *_utc; labels and sentences are in IST. Amounts in mm. "
                 "Counts are forecasts with at least 2.5 mm: out of 50 per model, out of 100 pooled. "
                 "This service is based on data and products of the European Centre for Medium-Range Weather "
                 "Forecasts (ECMWF), CC BY 4.0."),
)
app.add_middleware(CORSMiddleware, allow_origins=["https://ishansurdi.github.io"], allow_methods=["GET"])
store = Store()


class Meta(BaseModel):
    run_id: str = Field(description="Run start as YYYYMMDDHH (UTC)")
    run_time_utc: datetime
    previous_run_id: str | None = Field(description="Run used for 'since the previous forecast'")
    processed_at_utc: datetime = Field(description="When these products were built")
    data_status: str = Field(description="fresh | stale (a run was missed) | expired (no 48-h summary for now)")
    now_utc: datetime
    first_block_utc: datetime
    last_block_end_utc: datetime


class Block(BaseModel):
    label: str = Field(description="6-h block in IST, e.g. 'Thu afternoon · 11:30–17:30 IST'")
    start_utc: datetime
    end_utc: datetime
    past: bool = Field(description="Block already over: not a forecast any more")
    n_ifs: int = Field(description="IFS forecasts (of 50) with ≥ 2.5 mm")
    n_aifs: int = Field(description="AIFS forecasts (of 50) with ≥ 2.5 mm")
    n_pooled: int = Field(description="Forecasts (of 100) with ≥ 2.5 mm")
    n_previous: int | None = Field(description="Same, from the previous run; null if none")
    answer: str
    settled: str
    dots: str = Field(description="26 hex chars; bit n (MSB first) = forecast n wet: 0-49 IFS, 50-99 AIFS")


class Day(BaseModel):
    label: str = Field(description="App day 05:30–05:30 IST")
    app_day: str
    counts: dict[str, dict[str, int]] = Field(description="threshold mm -> {ifs, aifs, pooled} forecasts at or above")
    n_previous: int | None = Field(description="Pooled forecasts ≥ 2.5 mm in the previous run; null if none")
    percentiles_mm: dict[str, float] = Field(description="Pooled 100 forecasts: p10, p25, p50, p75, p90")
    median_ifs_mm: float
    median_aifs_mm: float
    n_under_0_1_mm: int = Field(description="Pooled forecasts shown as 0.0 mm")
    text: str
    settled: str


class Point(BaseModel):
    meta: Meta
    lat: float = Field(description="Grid cell centre used (nearest 0.25° point)")
    lon: float
    current_block: int | None = Field(description="Index into blocks of the block containing now")
    summary_48h: str | None = Field(description="Answer-card sentence; null when the data is expired")
    blocks: list[Block]
    days: list[Day]


def _now(at: datetime | None) -> datetime:
    if at is None:
        return datetime.now(timezone.utc)
    if at.tzinfo is None:
        raise HTTPException(422, "'at' must include a timezone, e.g. 2026-11-05T06:00:00Z")
    return at.astimezone(timezone.utc)


def _meta() -> dict:
    try:
        return store.meta()
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise HTTPException(503, f"published data unavailable: {e}") from e


def _meta_out(m: dict, now: datetime) -> Meta:
    return Meta(run_id=m["run_id"], run_time_utc=m["run_time_utc"], previous_run_id=m["previous_run_id"],
                processed_at_utc=m["processed_at_utc"], data_status=data_status(m, now), now_utc=now,
                first_block_utc=m["blocks"][0]["start_utc"], last_block_end_utc=m["blocks"][-1]["end_utc"])


@app.get("/meta", response_model=Meta, summary="Latest published run and data status")
def meta(at: Annotated[datetime | None, Query(description="View time (ISO, with zone); default now")] = None) -> Meta:
    """Which run is being served, when it was processed, and whether it is fresh, stale or expired."""
    now = _now(at)
    return _meta_out(_meta(), now)


@app.get("/point", response_model=Point, summary="Answer for one place",
         responses={404: {"description": "Outside the forecast area"}, 503: {"description": "Data unavailable"}})
def point(lat: Annotated[float, Query(ge=-90, le=90, description="Latitude, degrees north")],
          lon: Annotated[float, Query(ge=-180, le=180, description="Longitude, degrees east")],
          at: Annotated[datetime | None, Query(description="View time (ISO, with zone); default now")] = None) -> Point:
    """48-h summary, every 6-h block and every day for the nearest 0.25° grid point, with the numbers behind them."""
    now = _now(at)
    m = _meta()
    try:
        j, i = cell_index(m, lat, lon)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    t = m["tile_cells"]
    try:
        tile = store.tile(m["run_id"], j // t, i // t)
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise HTTPException(503, f"point data unavailable: {e}") from e
    cell, s = tile["cells"][f"{j}_{i}"], tile["strings"]
    k_now = current_block(m, now)
    summary = None
    if k_now is not None and k_now < m["summary_start_blocks"]:
        summary = s[cell["s"][k_now]]
    blocks = []
    for k, (b, (ni, na, prev, dots), (ta, ts)) in enumerate(zip(m["blocks"], cell["b"], cell["bt"])):
        blocks.append(Block(label=b["label"], start_utc=b["start_utc"], end_utc=b["end_utc"],
                            past=datetime.fromisoformat(b["end_utc"]) <= now, n_ifs=ni, n_aifs=na, n_pooled=ni + na,
                            n_previous=None if prev < 0 else prev, answer=s[ta], settled=s[ts], dots=dots))
    days = []
    thresholds = m["day_thresholds_mm"]
    for dmeta, row, (tt, ts) in zip(m["days"], cell["d"], cell["dt"]):
        counts = {f"{th:g}": {"ifs": row[2 * n], "aifs": row[2 * n + 1], "pooled": row[2 * n] + row[2 * n + 1]}
                  for n, th in enumerate(thresholds)}
        rest = row[2 * len(thresholds):]
        prev, q, mi, ma, nzero = rest[0], rest[1:6], rest[6], rest[7], rest[8]
        days.append(Day(label=dmeta["label"], app_day=dmeta["app_day"], counts=counts,
                        n_previous=None if prev < 0 else prev,
                        percentiles_mm=dict(zip(("p10", "p25", "p50", "p75", "p90"), q)),
                        median_ifs_mm=mi, median_aifs_mm=ma, n_under_0_1_mm=nzero, text=s[tt], settled=s[ts]))
    g = m["grid"]
    return Point(meta=_meta_out(m, now), lat=g["lat_first"] - j * g["step_deg"], lon=g["lon_first"] + i * g["step_deg"],
                 current_block=k_now, summary_48h=summary, blocks=blocks, days=days)


@app.get("/", include_in_schema=False)
def root() -> dict:
    """Pointer to the docs."""
    return {"service": "rain-trust API", "docs": "/docs", "endpoints": ["/meta", "/point?lat=13.08&lon=80.27"]}
