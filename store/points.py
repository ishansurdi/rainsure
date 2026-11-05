"""Point tiles: per grid cell numbers plus finished sentences, so the answer card needs no API (DECISIONS.md D52).

Tile JSON: {"run", "tile": [ti, tj], "strings": [...], "cells": {"j_i": cell}} where j, i index the run grid
(north->south, west->east). Sentences are stored once per tile in "strings" and referenced by index:
  cell["b"][k]  = [n_ifs, n_aifs, n_prev or -1, dots]  per 6-h block k; dots = 26 hex chars, bit n (MSB first) =
                  forecast n wet (>= 2.5 mm): 0-49 IFS members 1-50, 50-99 AIFS members 1-50
  cell["bt"][k] = [answer, settled]                    sentence indices for block k
  cell["d"][k]  = [n_ifs, n_aifs] per DAY_THRESHOLDS_MM, then n_prev or -1, p10, p25, p50, p75, p90 (mm),
                  median_ifs, median_aifs (mm), n_zero                 per full app day k
  cell["dt"][k] = [day total, settled]                 sentence indices for day k
  cell["s"][s]  = 48-h summary index when "now" falls in block s, s < SUMMARY_START_BLOCKS
"""

from collections.abc import Iterator
from typing import Any

import numpy as np
import xarray as xr

from common import config
from common.time import Block, block_label, day_label
from process.wording import (BlockCounts, block_sentence, confidence_sentence, day_sentence, disagree_sentence,
                             summary_48h)


class StringTable:
    """Distinct sentences of one tile, each stored once."""

    def __init__(self) -> None:
        self.strings: list[str] = []
        self._index: dict[str, int] = {}

    def add(self, s: str) -> int:
        """Index of s, adding it if new."""
        if s not in self._index:
            self._index[s] = len(self.strings)
            self.strings.append(s)
        return self._index[s]


def dots_hex(wet: np.ndarray) -> np.ndarray:
    """Wet flags (..., 100) -> 26-char hex strings (...,): bit n, MSB first, = forecast n."""
    packed = np.packbits(wet.astype(bool), axis=-1)  # 100 bits -> 13 bytes (last 4 bits padding)
    return np.apply_along_axis(lambda b: b.tobytes().hex(), -1, packed)


def _mm(x: float) -> float:
    return round(float(x), 1)


def build_tiles(run_id: str, blocks: list[Block], bp: xr.Dataset, dp: xr.Dataset,
                summary_counts: list[dict]) -> Iterator[tuple[tuple[int, int], dict[str, Any]]]:
    """Yield ((ti, tj), tile dict) for every tile of the grid.

    bp, dp: store.products block/day datasets; summary_counts[s] = window_day_counts(...) for start block s.
    """
    n_lat, n_lon = bp.sizes["latitude"], bp.sizes["longitude"]
    nb, nd = bp.sizes["step_h"], dp.sizes["app_day"]
    if nb != len(blocks):
        raise ValueError(f"{nb} block slots but {len(blocks)} blocks")
    if len(summary_counts) + config.NEXT_HOURS_BLOCKS - 1 > nb:
        raise ValueError("summary windows run past the last block")
    b = {k: bp[k].transpose("step_h", "latitude", "longitude").values for k in
         ("n_ifs", "n_aifs", "n_pooled", "n_prev", "decided", "agree", "stable")}
    dots = dots_hex(bp["wet"].transpose("latitude", "longitude", "step_h", "member").values)  # (J, I, S)
    dvars = [f"n_{m}_{t:g}" for t in config.DAY_THRESHOLDS_MM for m in ("ifs", "aifs")]
    d = {k: dp[k].transpose("app_day", "latitude", "longitude").values for k in
         dvars + ["n_pooled", "n_prev", "median_ifs_mm", "median_aifs_mm", "n_zero", "decided", "agree", "stable"]}
    pct = dp["pct_mm"].transpose("pct", "app_day", "latitude", "longitude").values
    summary_counts = [{day: np.asarray(g) for day, g in c.items()} for c in summary_counts]
    b_labels = [block_label(x) for x in blocks]
    d_labels = [day_label(np.datetime64(x, "D").item()) for x in dp["app_day"].values]
    t = config.TILE_CELLS
    for ti in range(0, n_lat, t):
        for tj in range(0, n_lon, t):
            table, cells = StringTable(), {}
            for j in range(ti, min(ti + t, n_lat)):
                for i in range(tj, min(tj + t, n_lon)):
                    cells[f"{j}_{i}"] = _cell(j, i, b, dots, d, dvars, pct, blocks, b_labels, d_labels,
                                              summary_counts, table, nb, nd)
            yield (ti // t, tj // t), {"run": run_id, "tile": [ti // t, tj // t], "strings": table.strings,
                                        "cells": cells}


def _prev(x: float) -> int | None:
    return None if np.isnan(x) else int(x)


def _cell(j, i, b, dots, d, dvars, pct, blocks, b_labels, d_labels, summary_counts, table, nb, nd) -> dict:
    """Numbers and sentence indices for grid cell (j, i)."""
    cb, cbt = [], []
    for k in range(nb):
        ni, na, npool, prev = int(b["n_ifs"][k, j, i]), int(b["n_aifs"][k, j, i]), int(b["n_pooled"][k, j, i]), \
            _prev(b["n_prev"][k, j, i])
        dec, agr, stb = bool(b["decided"][k, j, i]), bool(b["agree"][k, j, i]), bool(b["stable"][k, j, i])
        answer = block_sentence(b_labels[k], npool) if agr else disagree_sentence(b_labels[k], ni, na)
        cb.append([ni, na, -1 if prev is None else prev, str(dots[j, i, k])])
        cbt.append([table.add(answer), table.add(confidence_sentence(npool, dec, agr, stb, prev))])
    cd, cdt = [], []
    for k in range(nd):
        prev = _prev(d["n_prev"][k, j, i])
        q = [_mm(pct[p, k, j, i]) for p in range(pct.shape[0])]
        mi, ma = _mm(d["median_ifs_mm"][k, j, i]), _mm(d["median_aifs_mm"][k, j, i])
        npool, nzero = int(d["n_pooled"][k, j, i]), int(d["n_zero"][k, j, i])
        dec, agr, stb = bool(d["decided"][k, j, i]), bool(d["agree"][k, j, i]), bool(d["stable"][k, j, i])
        cd.append([int(d[v][k, j, i]) for v in dvars] + [-1 if prev is None else prev] + q + [mi, ma, nzero])
        cdt.append([table.add(day_sentence(d_labels[k], agr, q[1], q[2], q[3], mi, ma, nzero, npool)),
                    table.add(confidence_sentence(npool, dec, agr, stb, prev))])
    summaries = []
    for s, counts in enumerate(summary_counts):
        window = [BlockCounts(blocks[k], int(b["n_ifs"][k, j, i]), int(b["n_aifs"][k, j, i]))
                  for k in range(s, s + config.NEXT_HOURS_BLOCKS)]
        summaries.append(table.add(summary_48h(window, {day: int(g[j, i]) for day, g in counts.items()})))
    return {"b": cb, "bt": cbt, "d": cd, "dt": cdt, "s": summaries}
