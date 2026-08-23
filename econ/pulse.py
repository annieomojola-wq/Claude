"""Scoring: where does today sit against the country's own economic history?

The whole tracker rests on one idea. A raw number like "inflation is 3.1%"
means nothing on its own - it is good in Lagos and bad in Ottawa. So every
reading is scored as a **percentile against that same country's own record**
over the period being tracked. 90 means "better than 90% of the years this
country has on file"; 10 means only a tenth of its history was worse.

That makes the score answer the question actually being asked - is this good
or bad *for here* - and it makes a 50-year composite possible, because the
same transformation applies to every year in the series, not just the last one.

Nothing in here touches the network, so all of it is unit-tested directly.
"""

from __future__ import annotations

import statistics

#: A percentile needs a distribution. Below this many observations we report
#: the value but refuse to grade it, rather than pretending 3 points is a record.
MIN_OBSERVATIONS = 8

#: A composite built from two indicators is noise, not a pulse.
MIN_PULSE_COMPONENTS = 4


def orient(value: float, direction: str, target: float | None = None) -> float | None:
    """Turn a raw reading into 'goodness', where higher is always better.

    This is what lets unemployment falling and FDI rising both count as an
    improvement, and it is why `direction` is carried in the catalogue.
    """
    if value is None:
        return None
    if direction == "up_good":
        return float(value)
    if direction == "down_good":
        return -float(value)
    if direction == "target":
        if target is None:
            return None
        # Distance from target, so overshoot and deflation are both penalised.
        return -abs(float(value) - float(target))
    return None  # "neutral" - shown for context, never graded


def percentile_rank(sample: list[float], value: float) -> float:
    """Percent of `sample` that `value` beats, counting ties as half.

    The mid-rank convention keeps a flat series from scoring either 0 or 100
    purely on tie-breaking.
    """
    if not sample:
        raise ValueError("percentile_rank needs a non-empty sample")
    below = sum(1 for x in sample if x < value)
    equal = sum(1 for x in sample if x == value)
    return 100.0 * (below + 0.5 * equal) / len(sample)


def score_series(series: dict[int, float], direction: str,
                 target: float | None = None) -> dict[int, float]:
    """Score every year in one country-indicator series against the whole series.

    The baseline is the full history deliberately: the question is "where does
    this year sit in the country's own record", which needs a fixed yardstick.
    Returns {} for neutral indicators and for series too short to grade.
    """
    oriented = {year: orient(value, direction, target) for year, value in series.items()}
    oriented = {year: value for year, value in oriented.items() if value is not None}
    if len(oriented) < MIN_OBSERVATIONS:
        return {}
    sample = list(oriented.values())
    return {year: round(percentile_rank(sample, value), 1) for year, value in oriented.items()}


def describe(series: dict[int, float]) -> dict:
    """Min/max/mean/median plus the best and worst years, for one raw series."""
    if not series:
        return {"count": 0}
    years = sorted(series)
    values = [series[y] for y in years]
    lowest = min(years, key=lambda y: series[y])
    highest = max(years, key=lambda y: series[y])
    return {
        "count": len(values),
        "first_year": years[0],
        "last_year": years[-1],
        "min": round(min(values), 4),
        "min_year": lowest,
        "max": round(max(values), 4),
        "max_year": highest,
        "mean": round(statistics.fmean(values), 4),
        "median": round(statistics.median(values), 4),
    }


def latest_reading(series: dict[int, float], scores: dict[int, float]) -> dict | None:
    """The most recent observation, with the context that makes it readable.

    Change is measured against the previous *observation*, not the previous
    calendar year, because these series have gaps and a five-year-old
    comparison dressed up as year-on-year would be a lie.
    """
    if not series:
        return None
    years = sorted(series)
    year = years[-1]
    value = series[year]

    reading: dict = {
        "year": year,
        "value": round(value, 4),
        "score": scores.get(year),
    }

    if len(years) >= 2:
        previous = years[-2]
        reading["prev_year"] = previous
        reading["prev_value"] = round(series[previous], 4)
        reading["change"] = round(value - series[previous], 4)

    # Where it sits against the last decade of its own history.
    decade = [series[y] for y in years if year - 10 < y <= year]
    if len(decade) >= 3:
        reading["decade_mean"] = round(statistics.fmean(decade), 4)
        reading["vs_decade"] = round(value - reading["decade_mean"], 4)

    return reading


def composite(scores_by_code: dict[str, dict[int, float]]) -> dict[int, float]:
    """Average the component scores into one pulse value per year.

    Equal weights: any weighting scheme would be a hidden opinion about which
    part of an economy matters most, and this way the components stay legible.
    Years with too few components are left out rather than averaged thin.
    """
    per_year: dict[int, list[float]] = {}
    for series in scores_by_code.values():
        for year, score in series.items():
            per_year.setdefault(year, []).append(score)
    return {
        year: round(statistics.fmean(values), 1)
        for year, values in per_year.items()
        if len(values) >= MIN_PULSE_COMPONENTS
    }


def trend(scores: dict[int, float], span: int = 3) -> dict | None:
    """Is the pulse better or worse than it was `span` years ago?"""
    if not scores:
        return None
    years = sorted(scores)
    latest = years[-1]
    earlier = [y for y in years if y <= latest - span]
    if not earlier:
        return None
    reference = earlier[-1]
    delta = scores[latest] - scores[reference]
    if delta >= 5:
        direction = "improving"
    elif delta <= -5:
        direction = "deteriorating"
    else:
        direction = "steady"
    return {
        "from_year": reference,
        "from_score": scores[reference],
        "to_year": latest,
        "to_score": scores[latest],
        "change": round(delta, 1),
        "direction": direction,
    }


def band(score: float | None) -> str:
    """Plain-English bucket for a 0-100 score, used for colour and copy."""
    if score is None:
        return "unknown"
    if score >= 75:
        return "strong"
    if score >= 55:
        return "firm"
    if score >= 45:
        return "middling"
    if score >= 25:
        return "soft"
    return "weak"
