"""Price-history providers.

Parsing is kept separate from HTTP so the response formats can be unit-tested
against recorded fixtures without touching the network.

Providers, in rough order of "works without signing up for anything":

  stooq       free CSV, no API key. US tickers as `aapl.us`, LSE as `hsba.uk`.
  yahoo       free JSON chart endpoint, no key. LSE tickers as `HSBA.L`.
              Unofficial - it can rate-limit or change shape without notice.
  twelvedata  needs TWELVEDATA_API_KEY. Reliable LSE coverage on the free tier.
  demo        deterministic synthetic prices, no network. Not real data.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request

Series = list[tuple[dt.date, float]]

USER_AGENT = "stock-drop-monitor/1.0 (+https://github.com/)"


class ProviderError(RuntimeError):
    pass


def _get(url: str, timeout: float = 30.0, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
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

def parse_stooq_csv(text: str) -> Series:
    """Stooq daily CSV: Date,Open,High,Low,Close,Volume."""
    text = text.strip()
    if not text or text.lower().startswith("no data"):
        raise ProviderError("stooq returned no data (unknown symbol or rate limited)")
    rows = list(csv.DictReader(io.StringIO(text)))
    out: Series = []
    for row in rows:
        raw_date = (row.get("Date") or "").strip()
        raw_close = (row.get("Close") or "").strip()
        if not raw_date or not raw_close or raw_close.upper() == "N/A":
            continue
        try:
            out.append((dt.date.fromisoformat(raw_date), float(raw_close)))
        except ValueError:
            continue
    if not out:
        raise ProviderError("stooq CSV contained no usable rows")
    return sorted(out)


def parse_yahoo_json(payload: dict) -> Series:
    """Yahoo v8 chart JSON -> series of (date, adjusted close)."""
    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise ProviderError(f"yahoo error: {chart['error']}")
    results = chart.get("result") or []
    if not results:
        raise ProviderError("yahoo returned no result block")
    result = results[0]
    stamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    closes = None
    adj = indicators.get("adjclose") or []
    if adj and adj[0].get("adjclose"):
        closes = adj[0]["adjclose"]
    else:
        quotes = indicators.get("quote") or []
        if quotes:
            closes = quotes[0].get("close")
    if not stamps or not closes:
        raise ProviderError("yahoo result had no closes")

    out: Series = []
    for stamp, close in zip(stamps, closes):
        if close is None:
            continue
        out.append((dt.datetime.fromtimestamp(stamp, dt.timezone.utc).date(), float(close)))
    if not out:
        raise ProviderError("yahoo series was entirely null")
    return sorted(out)


def parse_twelvedata_json(payload: dict) -> Series:
    if payload.get("status") == "error":
        raise ProviderError(f"twelvedata error: {payload.get('message')}")
    values = payload.get("values") or []
    out: Series = []
    for row in values:
        raw_date = (row.get("datetime") or "")[:10]
        raw_close = row.get("close")
        if not raw_date or raw_close is None:
            continue
        try:
            out.append((dt.date.fromisoformat(raw_date), float(raw_close)))
        except ValueError:
            continue
    if not out:
        raise ProviderError("twelvedata returned no usable rows")
    return sorted(out)


# --------------------------------------------------------------------------
# providers
# --------------------------------------------------------------------------

class Provider:
    name = "base"
    #: polite pause between requests, seconds
    delay = 0.0

    def symbol_for(self, company: dict) -> str:
        return company["symbols"].get(self.name) or company["ticker"]

    def fetch(self, company: dict, days: int) -> Series:  # pragma: no cover - interface
        raise NotImplementedError


class StooqProvider(Provider):
    name = "stooq"
    delay = 0.4

    def fetch(self, company: dict, days: int) -> Series:
        end = dt.date.today()
        start = end - dt.timedelta(days=days)
        query = urllib.parse.urlencode(
            {
                "s": self.symbol_for(company),
                "i": "d",
                "d1": start.strftime("%Y%m%d"),
                "d2": end.strftime("%Y%m%d"),
            }
        )
        return parse_stooq_csv(_get(f"https://stooq.com/q/d/l/?{query}").decode("utf-8", "replace"))


class YahooProvider(Provider):
    name = "yahoo"
    delay = 0.3

    def fetch(self, company: dict, days: int) -> Series:
        rng = "6mo" if days <= 180 else "1y"
        symbol = urllib.parse.quote(self.symbol_for(company))
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            f"?range={rng}&interval=1d&events=div%2Csplit"
        )
        return parse_yahoo_json(json.loads(_get(url).decode("utf-8", "replace")))


class TwelveDataProvider(Provider):
    name = "twelvedata"
    delay = 8.0  # free tier allows 8 requests/minute

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("TWELVEDATA_API_KEY", "")
        if not self.api_key:
            raise ProviderError("TWELVEDATA_API_KEY is not set")

    def symbol_for(self, company: dict) -> str:
        override = company["symbols"].get("twelvedata")
        if override:
            return override
        if company["exchange"] == "LSE":
            return f"{company['ticker'].rstrip('.')}:LSE"
        return company["ticker"]

    def fetch(self, company: dict, days: int) -> Series:
        query = urllib.parse.urlencode(
            {
                "symbol": self.symbol_for(company),
                "interval": "1day",
                "outputsize": max(days // 7 * 5 + 10, 30),
                "apikey": self.api_key,
            }
        )
        url = f"https://api.twelvedata.com/time_series?{query}"
        return parse_twelvedata_json(json.loads(_get(url).decode("utf-8", "replace")))


class DemoProvider(Provider):
    """Synthetic but plausible price paths. Deterministic per ticker.

    This exists so the dashboard runs with zero setup and so the UI can be
    developed offline. The numbers are NOT real market data.
    """

    name = "demo"
    delay = 0.0

    def __init__(self, seed: str = "2026"):
        self.seed = seed

    def fetch(self, company: dict, days: int) -> Series:
        rnd = random.Random(f"{self.seed}:{company['exchange']}:{company['ticker']}")
        base = {"USD": rnd.uniform(28, 480), "GBX": rnd.uniform(320, 5200)}[company["currency"]]
        # Give roughly a third of the universe a genuine downward drift so the
        # "decliners" view has something to show.
        drift = rnd.choice([-0.0016, -0.0011, -0.0006, 0.0003, 0.0007, 0.0012])
        vol = rnd.uniform(0.008, 0.026)

        today = dt.date.today()
        series: Series = []
        price = base
        for offset in range(days, -1, -1):
            day = today - dt.timedelta(days=offset)
            if day.weekday() >= 5:
                continue
            price *= 1 + drift + rnd.gauss(0, vol)
            price = max(price, 0.5)
            series.append((day, round(price, 2)))
        return series


def get_provider(name: str, **kwargs) -> Provider:
    providers = {
        "stooq": StooqProvider,
        "yahoo": YahooProvider,
        "twelvedata": TwelveDataProvider,
        "demo": DemoProvider,
    }
    if name not in providers:
        raise ProviderError(f"unknown provider {name!r}; choose from {sorted(providers)}")
    if name == "demo" and "seed" in kwargs:
        return DemoProvider(seed=kwargs["seed"])
    if name == "twelvedata" and kwargs.get("api_key"):
        return TwelveDataProvider(api_key=kwargs["api_key"])
    return providers[name]()


def fetch_with_retry(provider: Provider, company: dict, days: int, attempts: int = 3) -> Series:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return provider.fetch(company, days)
        except ProviderError as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(2 ** attempt)
    raise last  # type: ignore[misc]
