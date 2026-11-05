"""Run/step math, UTC->IST, and app-day 6-h blocks (DECISIONS.md D1, D3, D5)."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from common import config

# Fixed English names so labels do not depend on the machine's locale.
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_IST = timezone(config.IST_OFFSET, "IST")


@dataclass(frozen=True)
class Block:
    """One 6-h block of a forecast run: steps in hours since run start, times in UTC."""

    start_step_h: int
    end_step_h: int
    start_utc: datetime
    end_utc: datetime
    app_day: date  # app day (05:30-05:30 IST) the block belongs to; equals the UTC date of start
    name: str  # morning / afternoon / evening / night


def _require_utc(t_utc: datetime) -> None:
    """Raise if a datetime is naive or not UTC."""
    if t_utc.tzinfo is None or t_utc.utcoffset() != timedelta(0):
        raise ValueError(f"expected a timezone-aware UTC datetime, got {t_utc!r}")


def to_ist(t_utc: datetime) -> datetime:
    """Convert an aware UTC datetime to IST (UTC+05:30)."""
    _require_utc(t_utc)
    return t_utc.astimezone(_IST)


def validate_run_time(run_time_utc: datetime) -> None:
    """Raise unless run_time_utc is an aware UTC time on a supported run hour (00z/12z)."""
    _require_utc(run_time_utc)
    if (run_time_utc.minute, run_time_utc.second, run_time_utc.microsecond) != (0, 0, 0):
        raise ValueError(f"run time must be on the hour, got {run_time_utc.isoformat()}")
    if run_time_utc.hour not in config.RUN_HOURS_UTC:
        raise ValueError(f"run hour {run_time_utc.hour:02d}z not in {config.RUN_HOURS_UTC}")


def recent_runs(now_utc: datetime, hours_back: int) -> list[datetime]:
    """Run times (00z/12z) that started in the last hours_back hours, newest first."""
    _require_utc(now_utc)
    t = now_utc.replace(minute=0, second=0, microsecond=0)
    oldest = now_utc - timedelta(hours=hours_back)
    runs = []
    while t >= oldest:
        if t.hour in config.RUN_HOURS_UTC:
            runs.append(t)
        t -= timedelta(hours=1)
    return runs


def blocks_for_run(run_time_utc: datetime, n_full_days: int = config.LEAD_DAYS) -> list[Block]:
    """Return 6-h blocks from run start to the end of the n-th full app day after it."""
    validate_run_time(run_time_utc)
    if n_full_days < 1:
        raise ValueError(f"n_full_days must be >= 1, got {n_full_days}")
    first_boundary_h = (config.DAY_START_HOUR_UTC - run_time_utc.hour) % 24  # 0 for 00z, 12 for 12z
    last_step_h = first_boundary_h + 24 * n_full_days
    blocks = []
    for start_h in range(0, last_step_h, config.BLOCK_HOURS):
        start = run_time_utc + timedelta(hours=start_h)
        end = start + timedelta(hours=config.BLOCK_HOURS)
        name = config.BLOCK_NAMES_BY_START_HOUR_UTC[start.hour]
        blocks.append(Block(start_h, start_h + config.BLOCK_HOURS, start, end, start.date(), name))
    return blocks


def block_name(block: Block) -> str:
    """Short name without times, e.g. 'Thu night' (weekday of the block's app day)."""
    return f"{_WEEKDAYS[block.app_day.weekday()]} {block.name}"


def time_label(t_utc: datetime) -> str:
    """A moment in IST, e.g. 'Thu 11:30 IST'."""
    t = to_ist(t_utc)
    return f"{_WEEKDAYS[t.weekday()]} {t:%H:%M} IST"


def _ist_range(start_utc: datetime, end_utc: datetime) -> str:
    """'11:30–17:30 IST' within one IST date, else '23:30 Thu – 05:30 Fri IST'."""
    s, e = to_ist(start_utc), to_ist(end_utc)
    if s.date() == e.date():
        return f"{s:%H:%M}–{e:%H:%M} IST"
    return f"{s:%H:%M} {_WEEKDAYS[s.weekday()]} – {e:%H:%M} {_WEEKDAYS[e.weekday()]} IST"


def span_label(first: Block, last: Block) -> str:
    """Label for consecutive blocks, e.g. 'Thu afternoon – evening · 11:30–23:30 IST' (one block: block_label)."""
    names = block_name(first)
    if last != first:
        names += f" – {last.name}" if last.app_day == first.app_day else f" – {block_name(last)}"
    return f"{names} · {_ist_range(first.start_utc, last.end_utc)}"


def block_label(block: Block) -> str:
    """Human label in IST, e.g. 'Thu night · 23:30 Thu – 05:30 Fri IST' (dates shown when it crosses midnight)."""
    return span_label(block, block)


def short_span(first: Block, last: Block) -> str:
    """Compact IST span of consecutive blocks: 'Thu 11:30–17:30 IST' or 'Thu 23:30 – Fri 05:30 IST'."""
    s, e = to_ist(first.start_utc), to_ist(last.end_utc)
    if s.date() == e.date():
        return f"{_WEEKDAYS[s.weekday()]} {s:%H:%M}–{e:%H:%M} IST"
    return f"{_WEEKDAYS[s.weekday()]} {s:%H:%M} – {_WEEKDAYS[e.weekday()]} {e:%H:%M} IST"


def day_label(app_day: date) -> str:
    """App day in IST, e.g. 'Thu · 05:30 Thu – 05:30 Fri IST' (D1)."""
    start = datetime(app_day.year, app_day.month, app_day.day, config.DAY_START_HOUR_UTC, tzinfo=timezone.utc)
    return f"{_WEEKDAYS[app_day.weekday()]} · {_ist_range(start, start + timedelta(hours=24))}"
