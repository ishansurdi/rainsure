"""Classify HOW the two models disagree in each 6-h block, with explicit rules (DECISIONS.md D60).

Only computed facts: which model is drier, its median, where/when the drier model has comparable rain. No reasons.
Rules in order (first match wins): lighter, timing, position, day, other. Arrays are (block, lat, lon), counts of 50.
"""

from dataclasses import dataclass

import numpy as np

from common import config

KIND = {name: n for n, name in enumerate(config.DISAGREE_KINDS)}
COMPASS = ("north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west")
EARTH_KM = 6371.0


@dataclass
class Disagreement:
    """Per block and cell: kind code, drier model and the facts each template needs."""

    kind: np.ndarray  # uint8, KIND codes ("none" where the models agree)
    drier: np.ndarray  # uint8, 0 = physics (IFS) drier, 1 = AI (AIFS) drier
    shift: np.ndarray  # int8, timing: +1 = drier model has it 6 h later, -1 = 6 h earlier
    other_n: np.ndarray  # uint8, drier model's count in that other block (timing) or at that grid point (position)
    dist_km: np.ndarray  # float32, position: distance to that grid point
    bearing: np.ndarray  # uint8, position: COMPASS index from here to there
    match_count: np.ndarray  # uint8, how many of the four rules matched (overlap statistics)


def _comparable(n_drier_there: np.ndarray, n_wetter_here: np.ndarray, members: int) -> np.ndarray:
    """Drier model's count elsewhere/elsewhen is within the agreement bar of the wetter count here, and likely."""
    gap = np.abs(n_drier_there.astype(np.int16) - n_wetter_here.astype(np.int16)) * 100.0 / members
    return (gap < config.AGREE_MAX_DIFF_PCT) & (n_drier_there * 100.0 / members >= config.LIKELY_FROM_PCT)


def neighbour_offsets(lat_deg: float, step_deg: float) -> list[tuple[int, int, float, int]]:
    """(dj, di, km, compass index) of grid offsets within POSITION_RADIUS_KM, nearest first (dj > 0 = south)."""
    out = []
    reach = 1 + int(config.POSITION_RADIUS_KM // (EARTH_KM * np.radians(step_deg) * np.cos(np.radians(min(abs(lat_deg) + 1, 89)))))
    p1 = np.radians(lat_deg)
    for dj in range(-reach, reach + 1):
        for di in range(-reach, reach + 1):
            if dj == di == 0:
                continue
            p2, dl = np.radians(lat_deg - dj * step_deg), np.radians(di * step_deg)
            a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
            d = float(2 * EARTH_KM * np.arcsin(np.sqrt(a)))
            if d <= config.POSITION_RADIUS_KM:
                y = np.sin(dl) * np.cos(p2)
                x = np.cos(p1) * np.sin(p2) - np.sin(p1) * np.cos(p2) * np.cos(dl)
                bearing = (np.degrees(np.arctan2(y, x)) + 360) % 360
                out.append((dj, di, d, int(((bearing + 22.5) % 360) // 45)))
    return sorted(out, key=lambda o: o[2])


def _lon_shift(a: np.ndarray, di: int) -> np.ndarray:
    """a[..., i + di] at every i; 0 beyond the grid edge."""
    if di == 0:
        return a
    out = np.zeros_like(a)
    if di > 0:
        out[..., :-di] = a[..., di:]
    else:
        out[..., -di:] = a[..., :di]
    return out


def classify(n_ifs: np.ndarray, n_aifs: np.ndarray, med_ifs: np.ndarray, med_aifs: np.ndarray,
             day_agree: np.ndarray, lat: np.ndarray, step_deg: float, members: int = config.EXPECTED_MEMBERS
             ) -> Disagreement:
    """Kind of disagreement per (block, lat, lon). day_agree: the block's app-day agreement (False on a partial day)."""
    n_ifs, n_aifs = n_ifs.astype(np.int16), n_aifs.astype(np.int16)
    shape = n_ifs.shape
    disagree = np.abs(n_ifs - n_aifs) * 100.0 / members >= config.AGREE_MAX_DIFF_PCT
    drier = (n_aifs < n_ifs).astype(np.uint8)
    n_wet = np.where(drier == 1, n_ifs, n_aifs)
    n_dry = np.where(drier == 1, n_aifs, n_ifs)
    med_dry = np.where(drier == 1, med_aifs, med_ifs)
    med_wet = np.where(drier == 1, med_ifs, med_aifs)

    # 1. lighter: both expect rain here and now; the drier model's median is real rain but under 2.5 mm
    lighter = disagree & (med_dry >= config.LIGHTER_MIN_MM) & (med_dry < config.EVENT_MM) & (med_dry < med_wet)

    # 2. timing: the drier model has comparable rain in the block before or after (same cell)
    timing = np.zeros(shape, bool)
    shift = np.zeros(shape, np.int8)
    n_timing = np.zeros(shape, np.int16)
    for s in (+1, -1):  # "later" first
        there = np.zeros_like(n_dry)
        if s == +1:
            there[:-1] = np.where(drier[:-1] == 1, n_aifs[1:], n_ifs[1:])
        else:
            there[1:] = np.where(drier[1:] == 1, n_aifs[:-1], n_ifs[:-1])
        hit = disagree & ~timing & _comparable(there, n_wet, members)
        shift[hit], n_timing[hit] = s, there[hit]
        timing |= hit

    # 3. position: the drier model has comparable rain within POSITION_RADIUS_KM in the same block (nearest wins)
    position = np.zeros(shape, bool)
    dist = np.zeros(shape, np.float32)
    bearing = np.zeros(shape, np.uint8)
    n_position = np.zeros(shape, np.int16)
    for j0, lat0 in enumerate(lat):
        for dj, di, d, b in neighbour_offsets(float(lat0), step_deg):
            jj = j0 + dj
            if not 0 <= jj < shape[1]:
                continue
            there = _lon_shift(np.where(drier[:, j0, :] == 1, n_aifs[:, jj, :], n_ifs[:, jj, :]), di)
            hit = disagree[:, j0, :] & ~position[:, j0, :] & _comparable(there, n_wet[:, j0, :], members)
            position[:, j0, :] |= hit
            dist[:, j0, :][hit], bearing[:, j0, :][hit], n_position[:, j0, :][hit] = d, b, there[hit]

    # 4. day: the models agree on the day's total, so the difference is timing within the day
    day = disagree & day_agree.astype(bool)

    rules = [("lighter", lighter), ("timing", timing), ("position", position), ("day", day)]
    kind = np.full(shape, KIND["none"], np.uint8)
    kind[disagree] = KIND["other"]
    for name, mask in reversed(rules):  # earlier rules overwrite later ones
        kind[mask] = KIND[name]
    other_n = np.where(kind == KIND["timing"], n_timing, np.where(kind == KIND["position"], n_position, 0))
    matches = sum(m.astype(np.uint8) for _, m in rules)
    return Disagreement(kind, drier, np.where(kind == KIND["timing"], shift, 0).astype(np.int8),
                        other_n.astype(np.uint8), dist, bearing, np.asarray(matches, np.uint8))
