"""Loading the watchlists that define what each exchange view contains."""

from __future__ import annotations

import json
import os

EXCHANGES = {
    "NYSE": {"code": "NYSE", "name": "New York Stock Exchange", "file": "nyse.json", "currency": "USD"},
    "NASDAQ": {"code": "NASDAQ", "name": "Nasdaq", "file": "nasdaq.json", "currency": "USD"},
    "LSE": {"code": "LSE", "name": "London Stock Exchange", "file": "lse.json", "currency": "GBX"},
}

REQUIRED_FIELDS = ("ticker", "name", "sector", "exchange", "currency", "symbols")


def universe_dir(root: str) -> str:
    return os.path.join(root, "universe")


def load(root: str, exchanges: list[str] | None = None) -> list[dict]:
    """Load and validate the company lists for the given exchange codes."""
    wanted = [e.upper() for e in (exchanges or list(EXCHANGES))]
    companies: list[dict] = []
    for code in wanted:
        if code not in EXCHANGES:
            raise ValueError(f"unknown exchange {code!r}; choose from {sorted(EXCHANGES)}")
        path = os.path.join(universe_dir(root), EXCHANGES[code]["file"])
        with open(path) as handle:
            rows = json.load(handle)
        for row in rows:
            missing = [f for f in REQUIRED_FIELDS if f not in row]
            if missing:
                raise ValueError(f"{path}: {row.get('ticker', '?')} is missing {missing}")
            if row["exchange"] != code:
                raise ValueError(f"{path}: {row['ticker']} claims exchange {row['exchange']!r}")
        companies.extend(rows)
    return companies
