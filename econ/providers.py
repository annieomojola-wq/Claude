"""Data sources for the economic tracker.

As in `stockmon.providers`, parsing is kept separate from HTTP so the response
shapes can be unit-tested against recorded fixtures without touching the network.

  worldbank   free JSON API, no key, ~65 years of annual data for every country.
  demo        deterministic synthetic series, no network. Not real data.

Equity index levels reuse the price providers the stock dashboard already has,
so there is one place that knows how to talk to Stooq and Yahoo.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import random
import urllib.error
import urllib.parse
import urllib.request

from . import countries, indicators

WORLDBANK_BASE = "https://api.worldbank.org/v2"
USER_AGENT = "econ-pulse-tracker/1.0 (+https://github.com/)"

# (iso3, year) -> value
Observations = dict[tuple[str, int], float]


class ProviderError(RuntimeError):
    pass


def _get(url: str, timeout: float = 60.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"HTTP {exc.code} for {url}") from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"{exc.reason} for {url}") from exc


# --------------------------------------------------------------------------
# parsers (pure - unit tested)
# --------------------------------------------------------------------------

def parse_worldbank_json(payload) -> Observations:
    """World Bank API v2 -> {(iso3, year): value}.

    The response is `[metadata, rows]`. Two things it does instead of failing
    loudly, both of which have to be handled:
      - an unknown indicator returns `[{"message": [...]}]` with no rows list
      - a country/year with no observation returns a row with `"value": null`
    """
    if isinstance(payload, dict):
        raise ProviderError(f"world bank returned an object, not a result pair: {payload}")
    if not isinstance(payload, list) or not payload:
        raise ProviderError("world bank returned an empty response")

    head = payload[0]
    if isinstance(head, dict) and "message" in head:
        messages = head.get("message") or []
        detail = "; ".join(str(m.get("value", m)) for m in messages) or "unknown error"
        raise ProviderError(f"world bank error: {detail}")

    if len(payload) < 2 or payload[1] is None:
        # A valid query that matched no rows at all.
        return {}

    rows = payload[1]
    if not isinstance(rows, list):
        raise ProviderError("world bank rows were not a list")

    out: Observations = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        iso3 = (row.get("countryiso3code") or "").strip().upper()
        raw_year = (row.get("date") or "").strip()
        value = row.get("value")
        if not iso3 or not raw_year or value is None:
            continue
        try:
            year = int(raw_year)
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(number):
            continue
        out[(iso3, year)] = number
    return out


# --------------------------------------------------------------------------
# providers
# --------------------------------------------------------------------------

class WorldBankProvider:
    """Pulls annual indicator series straight from the World Bank."""

    name = "worldbank"
    is_demo = False

    def __init__(self, timeout: float = 60.0) -> None:
        self.timeout = timeout

    def url_for(self, code: str, iso3_codes: list[str], start: int, end: int,
                source: int | None = None) -> str:
        path = ";".join(iso3_codes)
        # The date range is written literally: the API wants `date=1975:2025`,
        # and percent-encoding the colon is asking for trouble.
        query = f"format=json&per_page=20000&date={start}:{end}"
        # Not every series lives in the default WDI database. The governance
        # indicators sit in source 3 (Worldwide Governance Indicators) and
        # return "indicator not found" unless you ask for them there.
        if source is not None:
            query += f"&source={source}"
        return f"{WORLDBANK_BASE}/country/{path}/indicator/{code}?{query}"

    def fetch(self, code: str, iso3_codes: list[str], start: int, end: int) -> Observations:
        source = indicators.BY_CODE.get(code, {}).get("source")
        raw = _get(self.url_for(code, iso3_codes, start, end, source), timeout=self.timeout)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderError(f"world bank returned unparseable JSON for {code}: {exc}") from exc
        return parse_worldbank_json(payload)


class DemoProvider:
    """Deterministic synthetic series so the dashboard renders with no network.

    Shaped to look plausible (trends, cycles, a 2008 and a 2020 shock) but the
    numbers are invented. Everything downstream flags `is_demo`.
    """

    name = "demo"
    is_demo = True

    def __init__(self, seed: str = "2026") -> None:
        self.seed = seed

    def fetch(self, code: str, iso3_codes: list[str], start: int, end: int) -> Observations:
        meta = indicators.get(code)
        out: Observations = {}
        for iso3 in iso3_codes:
            rng = random.Random(f"{self.seed}:{code}:{iso3}")
            base = {
                "pct": 3.0, "pct_gdp": 40.0, "usd": 5.0e11, "count": 1500.0,
                "index": 100.0, "score": 0.8, "ratio": 3.0, "months": 6.0, "rate": 1.2,
            }.get(meta["unit"], 10.0)
            level = base * rng.uniform(0.6, 1.4)
            first = max(start, meta["since"])
            for year in range(first, end + 1):
                shock = 1.0
                if year in (2008, 2009):
                    shock = 0.82
                elif year == 2020:
                    shock = 0.75
                level *= rng.uniform(0.94, 1.07) * shock
                out[(iso3, year)] = round(level, 4)
        return out


def get_provider(name: str, seed: str = "2026", timeout: float = 60.0):
    if name == "worldbank":
        return WorldBankProvider(timeout=timeout)
    if name == "demo":
        return DemoProvider(seed=seed)
    raise ProviderError(f"unknown provider {name!r}; expected 'worldbank' or 'demo'")


# --------------------------------------------------------------------------
# equity indices - reuses the price providers the stock dashboard already has
# --------------------------------------------------------------------------

def fetch_index_levels(provider_name: str = "yahoo", lookback_days: int = 500,
                       progress=lambda msg: None) -> dict:
    """Latest level plus 1m/1y moves for each market's headline index.

    Returns {iso3: {...}}. A market whose index the provider does not carry
    (Nigeria's NGX, on both free providers) is reported as unavailable rather
    than quietly missing, so the dashboard can say so.
    """
    try:
        from stockmon import providers as price_providers
    except ImportError as exc:  # pragma: no cover - only if the repo is split up
        raise ProviderError(f"cannot import stockmon price providers: {exc}") from exc

    provider = price_providers.get_provider(provider_name)
    # Only Stooq has its own symbol spelling; everything else uses Yahoo's.
    key = "stooq" if provider_name == "stooq" else "yahoo"
    out: dict[str, dict] = {}

    for country in countries.COUNTRIES:
        index = country["index"]
        symbol = index.get(key)
        entry = {"name": index["name"], "symbol": symbol, "provider": provider_name}
        if not symbol:
            entry.update(status="unavailable",
                         detail=f"{provider_name} does not carry {index['name']}")
            out[country["iso3"]] = entry
            continue

        progress(f"index {country['short']}: {symbol}")
        # The price providers key off a company dict, so hand them a stand-in
        # whose symbol map already resolves to the index ticker.
        stand_in = {"ticker": symbol, "name": index["name"], "exchange": "INDEX",
                    # Index levels are points, not money - the price providers only
                    # need *a* currency, and the demo one recognises USD.
                    "currency": "USD", "sector": "Index",
                    "symbols": {"yahoo": symbol, "stooq": symbol}}
        try:
            series = provider.fetch(stand_in, lookback_days)
        except Exception as exc:  # provider errors are per-symbol, never fatal
            entry.update(status="error", detail=str(exc))
            out[country["iso3"]] = entry
            continue

        if not series:
            entry.update(status="error", detail="provider returned no rows")
            out[country["iso3"]] = entry
            continue

        as_of, level = series[-1]
        entry.update(status="ok", as_of=as_of.isoformat(), level=round(level, 2))
        for label, days in (("change_1m_pct", 30), ("change_1y_pct", 365)):
            ref = _level_on_or_before(series, as_of - dt.timedelta(days=days))
            entry[label] = round((level / ref - 1) * 100, 2) if ref else None
        entry["history"] = [[d.isoformat(), round(v, 2)] for d, v in series[-260:]]
        out[country["iso3"]] = entry

    return out


def _level_on_or_before(series, target: dt.date):
    """Last close at or before `target`. Markets shut, so exact dates miss."""
    candidates = [value for date, value in series if date <= target]
    return candidates[-1] if candidates else None
