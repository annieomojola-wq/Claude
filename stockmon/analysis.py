"""Month-on-month price analysis.

A "month on month" drop has two reasonable readings, and this module supports
both because they can disagree by a lot mid-month:

  rolling  - the latest close against the last close on or before the same day
             one calendar month earlier. Always up to date.
  calendar - the last close of the most recently completed calendar month
             against the last close of the month before it. Matches how
             monthly performance is usually reported.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, asdict
from typing import Iterable, Optional

# A price series is a list of (date, close) sorted ascending by date.
Series = list[tuple[dt.date, float]]

INSUFFICIENT = "insufficient_data"
OK = "ok"


def shift_months(d: dt.date, months: int) -> dt.date:
    """Shift a date by whole months, clamping to the end of the target month.

    31 March shifted back one month is 28/29 February, not 3 March.
    """
    total = (d.year * 12 + (d.month - 1)) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(d.day, _days_in_month(year, month))
    return dt.date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        nxt = dt.date(year + 1, 1, 1)
    else:
        nxt = dt.date(year, month + 1, 1)
    return (nxt - dt.date(year, month, 1)).days


def close_on_or_before(series: Series, target: dt.date) -> Optional[tuple[dt.date, float]]:
    """Last observation on or before `target` (markets are shut some days)."""
    found = None
    for date, close in series:
        if date <= target:
            found = (date, close)
        else:
            break
    return found


def last_close_of_month(series: Series, year: int, month: int) -> Optional[tuple[dt.date, float]]:
    found = None
    for date, close in series:
        if date.year == year and date.month == month:
            found = (date, close)
        elif (date.year, date.month) > (year, month):
            break
    return found


def pct_change(new: float, old: float) -> Optional[float]:
    if old is None or new is None or old == 0:
        return None
    return (new - old) / old * 100.0


@dataclass
class Metrics:
    status: str
    as_of: Optional[str] = None          # date of the latest close used
    price: Optional[float] = None        # latest close
    ref_date: Optional[str] = None       # date of the month-ago comparison close
    ref_price: Optional[float] = None
    mom_pct: Optional[float] = None      # this month vs last month
    prev_mom_pct: Optional[float] = None # last month vs the month before
    chg_3m_pct: Optional[float] = None
    high_3m: Optional[float] = None
    drawdown_pct: Optional[float] = None # from the 3-month high
    yoy_pct: Optional[float] = None      # this month vs the same point a year ago
    yoy_ref_date: Optional[str] = None
    yoy_ref_price: Optional[float] = None
    high_52w: Optional[float] = None
    drawdown_52w_pct: Optional[float] = None
    spark: Optional[list[float]] = None       # last ~90 closes, for the month view
    spark_year: Optional[list[float]] = None  # ~weekly closes over 12 months
    note: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _rolling_pair(series: Series, anchor: dt.date, months_back: int):
    """(reference observation, anchor observation) for a rolling comparison."""
    ref = close_on_or_before(series, shift_months(anchor, -months_back))
    return ref


def compute(series: Series, basis: str = "rolling", spark_days: int = 90) -> Metrics:
    """Compute month-on-month metrics for one instrument."""
    series = sorted((d, float(c)) for d, c in series if c is not None)
    if len(series) < 2:
        return Metrics(status=INSUFFICIENT, note="fewer than 2 closes")

    if basis == "calendar":
        return _compute_calendar(series, spark_days)
    if basis != "rolling":
        raise ValueError(f"unknown basis: {basis!r}")
    return _compute_rolling(series, spark_days)


def _compute_rolling(series: Series, spark_days: int) -> Metrics:
    anchor_date, anchor_price = series[-1]

    ref = _rolling_pair(series, anchor_date, 1)
    if ref is None:
        return Metrics(
            status=INSUFFICIENT,
            as_of=anchor_date.isoformat(),
            price=anchor_price,
            note="no close on or before one month ago",
        )
    ref_date, ref_price = ref

    prev_ref = _rolling_pair(series, anchor_date, 2)
    prev_mom = None
    if prev_ref is not None and prev_ref[0] != ref_date:
        prev_mom = pct_change(ref_price, prev_ref[1])

    # A year of history is optional: without it the year-on-year figures are
    # simply absent, and the month-on-month view still works.
    yoy_ref = close_on_or_before(series, shift_months(anchor_date, -12))

    return _finish(
        series, anchor_date, anchor_price, ref_date, ref_price, prev_mom, spark_days, yoy_ref
    )


def _compute_calendar(series: Series, spark_days: int) -> Metrics:
    last_date = series[-1][0]
    # The most recently *completed* month, relative to the latest observation.
    completed = shift_months(dt.date(last_date.year, last_date.month, 1), -1)
    prior = shift_months(completed, -1)
    before = shift_months(prior, -1)

    anchor = last_close_of_month(series, completed.year, completed.month)
    ref = last_close_of_month(series, prior.year, prior.month)
    if anchor is None or ref is None:
        return Metrics(
            status=INSUFFICIENT,
            as_of=last_date.isoformat(),
            price=series[-1][1],
            note="missing a full calendar month of closes",
        )

    before_obs = last_close_of_month(series, before.year, before.month)
    prev_mom = pct_change(ref[1], before_obs[1]) if before_obs else None

    # The same completed month, one year earlier.
    year_ago = shift_months(completed, -12)
    yoy_ref = last_close_of_month(series, year_ago.year, year_ago.month)

    return _finish(
        series, anchor[0], anchor[1], ref[0], ref[1], prev_mom, spark_days, yoy_ref
    )


def _finish(
    series: Series,
    anchor_date: dt.date,
    anchor_price: float,
    ref_date: dt.date,
    ref_price: float,
    prev_mom: Optional[float],
    spark_days: int,
    yoy_ref: Optional[tuple[dt.date, float]] = None,
) -> Metrics:
    window = [(d, c) for d, c in series if d <= anchor_date]
    recent = [c for d, c in window if d >= shift_months(anchor_date, -3)]
    high_3m = max(recent) if recent else None

    three_m = close_on_or_before(series, shift_months(anchor_date, -3))
    chg_3m = pct_change(anchor_price, three_m[1]) if three_m else None

    spark = [c for d, c in window][-spark_days:]

    year_window = [(d, c) for d, c in window if d >= shift_months(anchor_date, -12)]
    high_52w = max((c for _, c in year_window), default=None)
    # Only claim a 52-week high once there is close to a year behind it.
    if yoy_ref is None:
        high_52w = None
    spark_year = _weekly(year_window) if yoy_ref is not None else None

    return Metrics(
        status=OK,
        as_of=anchor_date.isoformat(),
        price=round(anchor_price, 4),
        ref_date=ref_date.isoformat(),
        ref_price=round(ref_price, 4),
        mom_pct=_r(pct_change(anchor_price, ref_price)),
        prev_mom_pct=_r(prev_mom),
        chg_3m_pct=_r(chg_3m),
        high_3m=round(high_3m, 4) if high_3m is not None else None,
        drawdown_pct=_r(pct_change(anchor_price, high_3m)) if high_3m else None,
        yoy_pct=_r(pct_change(anchor_price, yoy_ref[1])) if yoy_ref else None,
        yoy_ref_date=yoy_ref[0].isoformat() if yoy_ref else None,
        yoy_ref_price=round(yoy_ref[1], 4) if yoy_ref else None,
        high_52w=round(high_52w, 4) if high_52w is not None else None,
        drawdown_52w_pct=_r(pct_change(anchor_price, high_52w)) if high_52w else None,
        spark=[round(c, 4) for c in spark],
        spark_year=spark_year,
    )


def _weekly(observations: Series, step: int = 5) -> list[float]:
    """Thin a daily series to roughly one point per trading week.

    A year of daily closes is ~250 points per company; the sparkline cannot
    show that much detail and the snapshot should not carry it.
    """
    if not observations:
        return []
    closes = [c for _, c in observations]
    sampled = closes[::step]
    if sampled[-1] != closes[-1]:
        sampled.append(closes[-1])
    return [round(c, 4) for c in sampled]


def _r(v: Optional[float]) -> Optional[float]:
    return round(v, 2) if v is not None else None


def is_sustained_decline(m: Metrics) -> bool:
    """Down this month and down the month before - a two-month slide."""
    return (
        m.status == OK
        and m.mom_pct is not None
        and m.prev_mom_pct is not None
        and m.mom_pct < 0
        and m.prev_mom_pct < 0
    )
