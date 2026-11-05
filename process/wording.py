"""Answer sentences from fixed templates filled with computed values (CLAUDE.md §6, DECISIONS.md D50).

Counts are members with rain >= EVENT_MM: pooled out of 2 x 50 forecasts, per model out of 50.
"""

from dataclasses import dataclass

from common import config
from common.time import Block, block_label, block_name, span_label, time_label

POOLED = 2 * config.EXPECTED_MEMBERS


def prob_word(count: int, members: int) -> str:
    """IMD probability word for count of members: 'unlikely', 'likely', 'very likely' or 'most likely'."""
    if not 0 <= count <= members:
        raise ValueError(f"count {count} outside 0..{members}")
    pct = 100.0 * count / members
    if pct < config.LIKELY_FROM_PCT:
        return "unlikely"
    if pct <= config.VERY_LIKELY_ABOVE_PCT:
        return "likely"
    return "very likely" if pct <= config.MOST_LIKELY_ABOVE_PCT else "most likely"


def rain_category(mm: float) -> str:
    """IMD category of an amount as displayed (rounded to 0.1 mm), or 'no rain' below 0.1 mm."""
    shown = round(mm, 1)
    for lower, name in config.RAIN_CATEGORIES_MM:
        if shown >= lower:
            return name
    return "no rain"


def block_sentence(label: str, n_pooled: int) -> str:
    """'Rain very likely Thu afternoon · 11:30–17:30 IST: 54 of 100 forecasts give ≥ 2.5 mm.'"""
    return (f"Rain {prob_word(n_pooled, POOLED)} {label}: {n_pooled} of {POOLED} forecasts "
            f"give ≥ {config.EVENT_MM:g} mm.")


def disagree_sentence(label: str, n_ifs: int, n_aifs: int) -> str:
    """'Models disagree on rain {label}: physics n of 50, AI n of 50.' (D29)"""
    m = config.EXPECTED_MEMBERS
    return f"Models disagree on rain {label}: physics {n_ifs} of {m}, AI {n_aifs} of {m}."


def confidence_sentence(n_pooled: int, decided: bool, agree: bool, stable: bool, n_previous: int | None) -> str:
    """'Confidence low: not clear-cut (54 of 100), up 34 points since the previous forecast.' (D14, D15)

    decided/agree/stable come from process.confidence.confidence_checks; n_previous only gives the direction.
    """
    clauses = []
    if not decided:
        clauses.append(f"not clear-cut ({n_pooled} of {POOLED})")
    if not agree:
        clauses.append("physics and AI models disagree")
    if not stable:
        if n_previous is None:
            clauses.append("no earlier forecast to compare")
        else:
            d = round(100.0 * (n_pooled - n_previous) / POOLED)
            clauses.append(f"{'up' if d > 0 else 'down'} {abs(d)} points since the previous forecast")
    level = config.CONFIDENCE_BY_POINTS[int(decided) + int(agree) + int(stable)]
    return f"Confidence {level}." if not clauses else f"Confidence {level}: {', '.join(clauses)}."


def _mm(x: float) -> str:
    return f"{round(x, 1):.1f}"


def day_sentence(label: str, agree: bool, p25_mm: float, p50_mm: float, p75_mm: float,
                 median_ifs_mm: float, median_aifs_mm: float) -> str:
    """Day total: pooled median category and middle half, or each model's median if the models disagree."""
    if not agree:
        return (f"Day total {label}: models disagree: physics median {_mm(median_ifs_mm)} mm "
                f"({rain_category(median_ifs_mm)}), AI median {_mm(median_aifs_mm)} mm ({rain_category(median_aifs_mm)}).")
    middle = "" if _mm(p25_mm) == _mm(p75_mm) else f", middle half {_mm(p25_mm)}–{_mm(p75_mm)} mm"
    return f"Day total {label}: likely {rain_category(p50_mm)} (median {_mm(p50_mm)} mm{middle})."


@dataclass(frozen=True)
class BlockCounts:
    """One block of the 48-h window with its member counts (rain >= EVENT_MM)."""

    block: Block
    n_ifs: int
    n_aifs: int

    @property
    def n_pooled(self) -> int:
        return self.n_ifs + self.n_aifs


def _is_wet(b: BlockCounts) -> bool:
    return prob_word(b.n_pooled, POOLED) != "unlikely"


def summary_48h(window: list[BlockCounts]) -> str:
    """Answer-card summary over the next blocks: dry stretch, wet spells, on/off, biggest model disagreement."""
    if len(window) != config.NEXT_HOURS_BLOCKS:
        raise ValueError(f"expected {config.NEXT_HOURS_BLOCKS} blocks, got {len(window)}")
    spells: list[list[BlockCounts]] = []
    for prev, b in zip([None] + window[:-1], window):
        if _is_wet(b):
            if prev is not None and _is_wet(prev):
                spells[-1].append(b)
            else:
                spells.append([b])
    end = time_label(window[-1].block.end_utc)
    if not spells:
        text = f"Dry for the next 48 hours, until {end}."
    else:
        text = "" if spells[0][0] is window[0] else f"Dry until {block_name(spells[0][0].block)}. "
        word = lambda s: prob_word(max(b.n_pooled for b in s), POOLED)  # noqa: E731
        if len(spells) <= 2:
            parts = [f"Rain {word(spells[0])} {span_label(spells[0][0].block, spells[0][-1].block)}"]
            if len(spells) == 2:
                parts.append(f"and {word(spells[1])} again {span_label(spells[1][0].block, spells[1][-1].block)}")
            text += ", ".join(parts) + "."
        else:
            all_wet = [b for s in spells for b in s]
            text += (f"{'Then on' if text else 'On'} and off until {time_label(spells[-1][-1].block.end_utc)}: rain "
                     f"{prob_word(max(b.n_pooled for b in all_wet), POOLED)} in {len(all_wet)} of {len(window)} blocks.")
    m = config.EXPECTED_MEMBERS
    gaps = [(abs(b.n_ifs - b.n_aifs) * 100 / m, b) for b in window]
    gap, worst = max(gaps, key=lambda g: g[0])
    if gap >= config.AGREE_MAX_DIFF_PCT:
        text += (f" Models disagree on {block_label(worst.block)}: physics {worst.n_ifs} of {m}, "
                 f"AI {worst.n_aifs} of {m}.")
    return text
