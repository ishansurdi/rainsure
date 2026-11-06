"""Build the static place-search file from GeoNames cities1000 (DECISIONS.md D26). Standard library only.

Usage: python -I tools/build_places.py <cities1000.zip> <admin1CodesASCII.txt> <out.json>
Source: https://download.geonames.org/export/dump/ (CC BY 4.0, credit "GeoNames" in the app).
Output: JSON list of [name, state, lat, lon, population], Indian places only, most populous first, so the
frontend can rank equal-name matches (e.g. the several Aurangabads) without extra logic.
"""

import csv
import io
import json
import sys
import zipfile
from pathlib import Path

COUNTRY = "IN"
COORD_DP = 3  # ~100 m; places are matched to a 0.25 deg grid cell anyway


def read_admin1(path: Path) -> dict[str, str]:
    """'IN.16' -> 'Maharashtra' from admin1CodesASCII.txt (tab-separated: code, name, ascii name, id)."""
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].startswith(f"{COUNTRY}."):
            out[parts[0]] = parts[1]
    return out


def read_places(zip_path: Path, states: dict[str, str]) -> list[list]:
    """Indian rows of cities1000.txt as [name, state, lat, lon, population]; missing state -> error."""
    rows = []
    with zipfile.ZipFile(zip_path) as z, z.open("cities1000.txt") as f:
        for r in csv.reader(io.TextIOWrapper(f, encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE):
            if r[8] != COUNTRY:
                continue
            key = f"{COUNTRY}.{r[10]}"
            if key not in states:
                raise ValueError(f"no state name for admin1 code {key} ({r[1]})")
            rows.append([r[1], states[key], round(float(r[4]), COORD_DP), round(float(r[5]), COORD_DP), int(r[14])])
    rows.sort(key=lambda x: (-x[4], x[0]))
    return rows


def main() -> None:
    """Command-line entry point."""
    zip_path, admin1, out = map(Path, sys.argv[1:4])
    rows = read_places(zip_path, read_admin1(admin1))
    out.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(rows)} places, {out.stat().st_size / 1e3:.0f} kB -> {out}")


if __name__ == "__main__":
    main()
