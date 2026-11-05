"""Packed map layers (DECISIONS.md D44, D52): one gzip file per layer, all time slots, row-major (slot, lat, lon).

uint8 layers: member counts (255 = missing); 'settled' = bit 0 decided, bit 1 models agree, bit 2 stable;
'change' = pooled count now - previous + 100 (0..200; 255 = no previous). uint16 'median': 0.1 mm (65535 = missing).
"""

import gzip
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

from common import config

U8_MISSING, U16_MISSING = 255, 65535


def _grid(da: xr.DataArray, slot_dim: str) -> np.ndarray:
    return da.transpose(slot_dim, "latitude", "longitude").values


def settled_bits(ds: xr.Dataset, slot_dim: str) -> np.ndarray:
    """decided | agree << 1 | stable << 2 as uint8."""
    return (_grid(ds["decided"], slot_dim).astype(np.uint8) | _grid(ds["agree"], slot_dim).astype(np.uint8) << 1
            | _grid(ds["stable"], slot_dim).astype(np.uint8) << 2)


def change_u8(n_now: np.ndarray, n_prev: np.ndarray) -> np.ndarray:
    """Pooled count difference + 100 as uint8; 255 where there is no previous run."""
    out = np.full(n_now.shape, U8_MISSING, dtype=np.uint8)
    ok = ~np.isnan(n_prev)
    out[ok] = (n_now[ok].astype(np.int16) - n_prev[ok].astype(np.int16) + 100).astype(np.uint8)
    return out


def tenth_mm_u16(mm: np.ndarray) -> np.ndarray:
    """mm -> uint16 tenths of mm (max error 0.05 mm); NaN or too large -> missing."""
    out = np.full(mm.shape, U16_MISSING, dtype=np.uint16)
    ok = np.isfinite(mm) & (mm >= 0) & (mm < (U16_MISSING - 0.5) / 10)
    out[ok] = np.round(mm[ok] * 10).astype(np.uint16)
    return out


def layer_arrays(bp: xr.Dataset, dp: xr.Dataset) -> dict[str, np.ndarray]:
    """All map layers of a run, keyed by file stem."""
    out = {f"block_{k}": _grid(bp[f"n_{k}"], "step_h").astype(np.uint8) for k in ("ifs", "aifs", "pooled")}
    out["block_settled"] = settled_bits(bp, "step_h")
    out["block_change"] = change_u8(_grid(bp["n_pooled"], "step_h"), _grid(bp["n_prev"], "step_h"))
    for t in config.DAY_THRESHOLDS_MM:
        ni, na = _grid(dp[f"n_ifs_{t:g}"], "app_day"), _grid(dp[f"n_aifs_{t:g}"], "app_day")
        out[f"day_ifs_{t:g}"], out[f"day_aifs_{t:g}"] = ni.astype(np.uint8), na.astype(np.uint8)
        out[f"day_pooled_{t:g}"] = (ni.astype(np.uint8) + na.astype(np.uint8)).astype(np.uint8)
    out["day_median"] = tenth_mm_u16(_grid(dp["pct_mm"].sel(pct=50), "app_day"))
    out["day_settled"] = settled_bits(dp, "app_day")
    out["day_change"] = change_u8(_grid(dp["n_pooled"], "app_day"), _grid(dp["n_prev"], "app_day"))
    return out


def write_layers(arrays: dict[str, np.ndarray], out_dir: Path) -> dict[str, Any]:
    """Write each layer as <stem>.<dtype>.gz; return their descriptions for the run metadata."""
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {}
    for stem, a in arrays.items():
        dtype = {np.dtype(np.uint8): "u8", np.dtype(np.uint16): "u16"}[a.dtype]
        name = f"{stem}.{dtype}.gz"
        (out_dir / name).write_bytes(gzip.compress(np.ascontiguousarray(a).astype(f"<{a.dtype.str[1:]}").tobytes(),
                                                   mtime=0))
        meta[stem] = {"file": name, "dtype": dtype, "shape": list(a.shape),
                      "missing": U8_MISSING if dtype == "u8" else U16_MISSING, "byte_order": "little"}
    return meta
