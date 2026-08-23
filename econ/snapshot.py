"""Build the JSON snapshot the economic dashboard reads."""

from __future__ import annotations

import datetime as dt
import json
import os
import time

from . import countries, indicators, providers, pulse

DEFAULT_START = 1975


def _pairs(mapping: dict[int, float]) -> list[list]:
    """{year: value} -> [[year, value], ...], sorted. Compact and ordered,
    which object keys in JSON are not."""
    return [[year, mapping[year]] for year in sorted(mapping)]


def build(
    root: str,
    provider,
    start: int = DEFAULT_START,
    end: int | None = None,
    index_provider: str | None = None,
    lookback_days: int = 500,
    delay: float = 0.2,
    progress=lambda msg: None,
) -> dict:
    end = end or dt.date.today().year
    iso3_codes = countries.ISO3_CODES

    # ---- pull every indicator for all five countries in one request each ----
    raw: dict[str, providers.Observations] = {}
    errors: list[dict] = []
    total = len(indicators.CODES)
    for position, code in enumerate(indicators.CODES, start=1):
        meta = indicators.get(code)
        progress(f"[{position}/{total}] {code} - {meta['label']}")
        try:
            raw[code] = provider.fetch(code, iso3_codes, start, end)
        except providers.ProviderError as exc:
            errors.append({"indicator": code, "label": meta["label"], "error": str(exc)})
            raw[code] = {}
        if delay and position < total:
            time.sleep(delay)

    # ---- reshape into per-country series ------------------------------------
    series: dict[str, dict[str, dict[int, float]]] = {iso3: {} for iso3 in iso3_codes}
    for code, observations in raw.items():
        for (iso3, year), value in observations.items():
            if iso3 in series:
                series[iso3].setdefault(code, {})[year] = value

    # ---- score, then compose ------------------------------------------------
    scores: dict[str, dict[str, dict[int, float]]] = {}
    readings: dict[str, dict[str, dict]] = {}
    coverage: dict[str, dict[str, dict]] = {}
    pulses: dict[str, dict] = {}

    for iso3 in iso3_codes:
        country = countries.get(iso3)
        scores[iso3] = {}
        readings[iso3] = {}
        coverage[iso3] = {}

        for code, values in series[iso3].items():
            meta = indicators.get(code)
            graded = pulse.score_series(
                values, meta["direction"], target=country["inflation_target"]
            )
            scores[iso3][code] = graded
            stats = pulse.describe(values)
            reading = pulse.latest_reading(values, graded)
            if reading:
                reading["band"] = pulse.band(reading.get("score"))
                reading["stats"] = stats
                reading["trend"] = pulse.trend(graded)
                readings[iso3][code] = reading
            coverage[iso3][code] = {
                "count": stats.get("count", 0),
                "first_year": stats.get("first_year"),
                "last_year": stats.get("last_year"),
                "graded": bool(graded),
            }

        component_scores = {
            code: scores[iso3][code]
            for code in indicators.PULSE_CODES
            if scores[iso3].get(code)
        }
        history = pulse.composite(component_scores)
        latest_year = max(history) if history else None
        pulses[iso3] = {
            "history": _pairs(history),
            "components": sorted(component_scores),
            "component_count": len(component_scores),
            "latest_year": latest_year,
            "latest": history.get(latest_year) if latest_year else None,
            "band": pulse.band(history.get(latest_year) if latest_year else None),
            "trend": pulse.trend(history),
            "best_year": max(history, key=history.get) if history else None,
            "worst_year": min(history, key=history.get) if history else None,
        }

    # ---- cross-country league table per indicator ---------------------------
    rankings: dict[str, list[dict]] = {}
    for code in indicators.CODES:
        row = [
            {
                "iso3": iso3,
                "year": readings[iso3][code]["year"],
                "value": readings[iso3][code]["value"],
                "score": readings[iso3][code].get("score"),
            }
            for iso3 in iso3_codes
            if code in readings[iso3]
        ]
        # Rank on the score where we have one, so direction is already handled.
        graded = [r for r in row if r["score"] is not None]
        ungraded = [r for r in row if r["score"] is None]
        graded.sort(key=lambda r: r["score"], reverse=True)
        rankings[code] = graded + ungraded

    # ---- live equity indices (optional, never fatal) ------------------------
    markets: dict[str, dict] = {}
    if index_provider:
        try:
            markets = providers.fetch_index_levels(
                index_provider, lookback_days=lookback_days, progress=progress
            )
        except providers.ProviderError as exc:
            errors.append({"indicator": "equity-indices", "label": "Equity indices",
                           "error": str(exc)})

    observation_count = sum(len(v) for c in series.values() for v in c.values())

    return {
        "meta": {
            "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
            "provider": provider.name,
            "is_demo": bool(getattr(provider, "is_demo", False)),
            "start_year": start,
            "end_year": end,
            "countries": len(iso3_codes),
            "indicators": len(indicators.CODES),
            "observations": observation_count,
            "index_provider": index_provider,
            "errors": errors,
        },
        "countries": [
            {k: v for k, v in c.items() if k != "index"} | {"index": c["index"]}
            for c in countries.COUNTRIES
        ],
        "indicators": indicators.INDICATORS,
        "families": indicators.FAMILIES,
        "pulse_codes": indicators.PULSE_CODES,
        "series": {
            iso3: {code: _pairs(values) for code, values in series[iso3].items()}
            for iso3 in iso3_codes
        },
        "scores": {
            iso3: {code: _pairs(values) for code, values in scores[iso3].items() if values}
            for iso3 in iso3_codes
        },
        "readings": readings,
        "coverage": coverage,
        "pulse": pulses,
        "rankings": rankings,
        "markets": markets,
        "context": load_context(root),
    }


def load_context(root: str) -> dict:
    """Hand-maintained context: policy rates, politics, notes.

    Kept in its own file, and out of the fetcher's way, because none of it
    comes from an API that covers all five markets - it is curated, dated, and
    edited by hand. Missing file is not an error; the dashboard just shows less.
    """
    path = os.path.join(root, "data", "econ_context.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"could not read econ_context.json: {exc}"}
