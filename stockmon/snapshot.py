"""Build the JSON snapshot the dashboard reads."""

from __future__ import annotations

import datetime as dt
import os
import sys
import time

from . import analysis, providers, universe


def cache_path(root: str, provider_name: str, symbol: str) -> str:
    safe = symbol.replace("/", "_").replace(":", "_")
    return os.path.join(root, "data", "cache", provider_name, f"{safe}.csv")


def read_cache(path: str, max_age_hours: float) -> analysis.Series | None:
    if not os.path.exists(path):
        return None
    age_hours = (time.time() - os.path.getmtime(path)) / 3600
    if age_hours > max_age_hours:
        return None
    try:
        with open(path) as handle:
            return providers.parse_stooq_csv(handle.read())
    except Exception:
        return None


def write_cache(path: str, series: analysis.Series) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write("Date,Close\n")
        for date, close in series:
            handle.write(f"{date.isoformat()},{close}\n")


def build(
    root: str,
    provider: providers.Provider,
    exchanges: list[str] | None = None,
    basis: str = "rolling",
    lookback_days: int = 500,
    cache_hours: float = 0.0,
    limit: int | None = None,
    progress=lambda msg: None,
) -> dict:
    companies = universe.load(root, exchanges)
    if limit:
        companies = companies[:limit]

    rows: list[dict] = []
    errors: list[dict] = []
    total = len(companies)

    for index, company in enumerate(companies, start=1):
        symbol = provider.symbol_for(company)
        progress(f"[{index}/{total}] {company['exchange']}:{company['ticker']} ({symbol})")

        series = None
        path = cache_path(root, provider.name, symbol)
        if cache_hours > 0:
            series = read_cache(path, cache_hours)

        if series is None:
            try:
                series = providers.fetch_with_retry(provider, company, lookback_days)
            except providers.ProviderError as exc:
                errors.append({"ticker": company["ticker"], "exchange": company["exchange"], "error": str(exc)})
                progress(f"    ! {exc}")
                continue
            if cache_hours > 0:
                write_cache(path, series)
            if provider.delay:
                time.sleep(provider.delay)

        metrics = analysis.compute(series, basis=basis)
        if metrics.status != analysis.OK:
            errors.append(
                {"ticker": company["ticker"], "exchange": company["exchange"], "error": metrics.note or metrics.status}
            )
            continue

        row = {
            "ticker": company["ticker"],
            "name": company["name"],
            "sector": company["sector"],
            "exchange": company["exchange"],
            "currency": company["currency"],
            "sustained": analysis.is_sustained_decline(metrics),
        }
        row.update(metrics.to_dict())
        rows.append(row)

    rows.sort(key=lambda r: (r["mom_pct"] is None, r["mom_pct"]))
    return {
        "meta": _meta(provider, basis, lookback_days, rows, errors, exchanges),
        "exchanges": [
            {k: v for k, v in universe.EXCHANGES[code].items() if k != "file"}
            for code in (exchanges or list(universe.EXCHANGES))
        ],
        "companies": rows,
    }


def _meta(provider, basis, lookback_days, rows, errors, exchanges) -> dict:
    decliners = [r for r in rows if r["mom_pct"] is not None and r["mom_pct"] < 0]
    as_of = sorted({r["as_of"] for r in rows if r.get("as_of")})
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "provider": provider.name,
        "is_demo": provider.name == "demo",
        "basis": basis,
        "lookback_days": lookback_days,
        "exchanges": exchanges or list(universe.EXCHANGES),
        "latest_close": as_of[-1] if as_of else None,
        "counts": {
            "tracked": len(rows),
            "decliners": len(decliners),
            "sustained": len([r for r in rows if r["sustained"]]),
            "errors": len(errors),
        },
        "errors": errors,
    }
