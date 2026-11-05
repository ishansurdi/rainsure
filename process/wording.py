"""Answer sentences from fixed templates filled with computed values (CLAUDE.md §6, DECISIONS.md D50).

Counts are members with rain >= EVENT_MM: pooled out of 2 x 50 forecasts, per model out of 50.
"""

from dataclasses import dataclass
from datetime import date

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


def rain_category(mm: float) -> str | None:
    """IMD category of an amount as displayed (rounded to 0.1 mm); None when it shows as 0.0 mm (D51)."""
    shown = round(mm, 1)
    for lower, name in config.RAIN_CATEGORIES_MM:
        if shown >= lower:
            return name
    return None


def block_sentence(label: str, n_pooled: int) -> str:
    """'Rain very likely Thu afternoon · 11:30–17:30 IST: 54 of 100 forecasts give ≥ 2.5 mm.'"""
    return (f"Rain {prob_word(n_pooled, POOLED)} {label}: {n_pooled} of {POOLED} forecasts "
            f"give ≥ {config.EVENT_MM:g} mm.")


def disagree_sentence(label: str, n_ifs: int, n_aifs: int) -> str:
    """'Models disagree on rain {label}: physics n of 50, AI n of 50.' (D29)"""
    m = config.EXPECTED_MEMBERS
    return f"Models disagree on rain {label}: physics {n_ifs} of {m}, AI {n_aifs} of {m}."


def confidence_sentence(n_pooled: int, decided: bool, agree: bool, stable: bool, n_previous: int | None) -> str:
    """'Forecast unsettled: not clear-cut (54 of 100), up 34 points since the previous forecast.' (D14, D15, D51)

    decided/agree/stable come from process.confidence.confidence_checks; n_previous only gives the direction.
    The text says what the confidence level means, so it does not read as a second chance of rain.
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
    head = config.SETTLED_TEXT_BY_POINTS[int(decided) + int(agree) + int(stable)]
    return f"{head}." if not clauses else f"{head}: {', '.join(clauses)}."


def _mm(x: float) -> str:
    return f"{round(x, 1):.1f}"


def _median_text(mm: float) -> str:
    """'median 4.0 mm (light rain)', or 'median 0.0 mm' with no category."""
    cat = rain_category(mm)
    return f"median {_mm(mm)} mm" + (f" ({cat})" if cat else "")


def day_sentence(label: str, agree: bool, p25_mm: float, p50_mm: float, p75_mm: float,
                 median_ifs_mm: float, median_aifs_mm: float, n_zero: int, n_event: int) -> str:
    """Day total sentence (D50, D51).

    n_zero: pooled forecasts shown as 0.0 mm (< 0.05 mm); n_event: pooled forecasts >= EVENT_MM.
    Models disagree -> each model's median. Pooled median shows 0.0 -> how many are under 0.1 mm and how many wet.
    """
    if not agree:
        return (f"Day total {label}: models disagree: physics {_median_text(median_ifs_mm)}, "
                f"AI {_median_text(median_aifs_mm)}.")
    if rain_category(p50_mm) is None:
        wet = f"; {n_event} of {POOLED} give ≥ {config.EVENT_MM:g} mm" if n_event else ""
        return f"Day total {label}: under 0.1 mm in {n_zero} of {POOLED} forecasts{wet}."
    middle = "" if _mm(p25_mm) == _mm(p75_mm) else f", middle half {_mm(p25_mm)}–{_mm(p75_mm)} mm"
    return f"Day total {label}: {_median_text(p50_mm)}{middle}."


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


def _word_range(blocks: list[BlockCounts]) -> str:
    """'very likely' if every block has the same word, else 'up to very likely' (the wettest block's word)."""
    words = {prob_word(b.n_pooled, POOLED) for b in blocks}
    top = prob_word(max(b.n_pooled for b in blocks), POOLED)
    return top if len(words) == 1 else f"up to {top}"


def summary_48h(window: list[BlockCounts], day_counts: dict[date, int]) -> str:
    """Answer-card summary over the next blocks: wet spells, on/off, spread-out rain, biggest model disagreement.

    day_counts[d]: pooled forecasts with >= EVENT_MM summed over the window's blocks of app day d (D51). A day with
    no wet block but day_counts >= 25 of 100 gets a 'spread over' sentence instead of being called unlikely.
    """
    if len(window) != config.NEXT_HOURS_BLOCKS:
        raise ValueError(f"expected {config.NEXT_HOURS_BLOCKS} blocks, got {len(window)}")
    spells: list[list[BlockCounts]] = []
    for prev, b in zip([None] + window[:-1], window):
        if _is_wet(b):
            if prev is not None and _is_wet(prev):
                spells[-1].append(b)
            else:
                spells.append([b])
    wet_days = {b.block.app_day for s in spells for b in s}
    spread = []  # (first block, last block, count) for days wet only in total
    for day in sorted({b.block.app_day for b in window}):
        if day not in wet_days and prob_word(day_counts[day], POOLED) != "unlikely":
            in_day = [b for b in window if b.block.app_day == day]
            spread.append((in_day[0], in_day[-1], day_counts[day]))
    timed: list[tuple[object, str]] = []  # (start time, sentence), told in time order
    if not spells and not spread:
        timed.append((window[0].block.start_utc,
                      f"Rain unlikely for the next 48 hours, until {time_label(window[-1].block.end_utc)}."))
    if spells:
        t0 = spells[0][0].block.start_utc
        prefix = spells[0][0] is not window[0] and not any(f.block.start_utc < t0 for f, _, _ in spread)
        if prefix:
            timed.append((window[0].block.start_utc, f"Rain unlikely until {block_name(spells[0][0].block)}."))
        if len(spells) <= 2:
            parts = [f"Rain {_word_range(spells[0])} {span_label(spells[0][0].block, spells[0][-1].block)}"]
            if len(spells) == 2:
                parts.append(f"and {_word_range(spells[1])} again {span_label(spells[1][0].block, spells[1][-1].block)}")
            timed.append((t0, ", ".join(parts) + "."))
        else:
            all_wet = [b for s in spells for b in s]
            timed.append((t0, f"{'Then on' if prefix else 'On'} and off until "
                              f"{time_label(spells[-1][-1].block.end_utc)}: rain {_word_range(all_wet)} in "
                              f"{len(all_wet)} of {len(window)} blocks."))
    for first, last, n in spread:
        timed.append((first.block.start_utc,
                      f"Rain {prob_word(n, POOLED)} spread over {span_label(first.block, last.block)}: {n} of "
                      f"{POOLED} forecasts give ≥ {config.EVENT_MM:g} mm in total, but no single 6-hour block "
                      f"is likely wet."))
    text = " ".join(s for _, s in sorted(timed, key=lambda x: x[0]))
    m = config.EXPECTED_MEMBERS
    gaps = [(abs(b.n_ifs - b.n_aifs) * 100 / m, b) for b in window]
    gap, worst = max(gaps, key=lambda g: g[0])
    if gap >= config.AGREE_MAX_DIFF_PCT:
        text += (f" Models disagree on {block_label(worst.block)}: physics {worst.n_ifs} of {m}, "
                 f"AI {worst.n_aifs} of {m}.")
    return text
