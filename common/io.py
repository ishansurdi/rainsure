"""Archive file format and names: compressed .npz values + .json metadata (CLAUDE.md §4)."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

_DIMS = ("step_h", "member", "latitude", "longitude")


def archive_stem(model: str, run_time_utc: datetime) -> str:
    """Base file name of one model run in the archive, e.g. 'tp_ifs-ens_2026110500'."""
    return f"tp_{model}_{run_time_utc:%Y%m%d%H}"


def write_archive(tp_accum_mm: xr.DataArray, meta: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    """Write accumulated tp in mm (step_h, member, latitude, longitude) as .npz plus .json metadata."""
    if tp_accum_mm.dims != _DIMS:
        raise ValueError(f"expected dims {_DIMS}, got {tp_accum_mm.dims}")
    if tp_accum_mm.attrs.get("units") != "mm":
        raise ValueError(f"expected units 'mm', got {tp_accum_mm.attrs.get('units')!r}")
    out_dir.mkdir(parents=True, exist_ok=True)
    npz, js = out_dir / f"{meta['stem']}.npz", out_dir / f"{meta['stem']}.json"
    np.savez_compressed(npz, tp_accum_mm=tp_accum_mm.values.astype(np.float32),
                        **{d: tp_accum_mm[d].values for d in _DIMS})
    js.write_text(json.dumps({**meta, "units": "mm", "dims": list(_DIMS), "shape": list(tp_accum_mm.shape)}, indent=1))
    return npz, js


def read_archive(npz_path: Path) -> xr.DataArray:
    """Read an archive .npz (and its .json metadata as attrs) back into a labelled array."""
    meta = json.loads(npz_path.with_suffix(".json").read_text())
    with np.load(npz_path) as z:
        return xr.DataArray(z["tp_accum_mm"], dims=_DIMS, coords={d: z[d] for d in _DIMS},
                            name="tp_accum_mm", attrs=meta)
