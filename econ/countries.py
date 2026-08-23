"""The five markets this tracker follows.

Everything downstream keys off `ISO3`, which is what the World Bank API uses.
`inflation_target` is the number the country's central bank actually aims at,
so "how far from target" means the same thing in Abuja as it does in Ottawa.
"""

from __future__ import annotations

COUNTRIES: list[dict] = [
    {
        "iso3": "USA",
        "iso2": "US",
        "name": "United States",
        "short": "US",
        "flag": "\U0001F1FA\U0001F1F8",
        "currency": "USD",
        "central_bank": "Federal Reserve",
        "policy_rate_name": "Federal funds target (upper bound)",
        "inflation_target": 2.0,
        "index": {"name": "S&P 500", "yahoo": "^GSPC", "stooq": "^spx"},
    },
    {
        "iso3": "GBR",
        "iso2": "GB",
        "name": "United Kingdom",
        "short": "UK",
        "flag": "\U0001F1EC\U0001F1E7",
        "currency": "GBP",
        "central_bank": "Bank of England",
        "policy_rate_name": "Bank Rate",
        "inflation_target": 2.0,
        "index": {"name": "FTSE 100", "yahoo": "^FTSE", "stooq": "^ukx"},
    },
    {
        "iso3": "IRL",
        "iso2": "IE",
        "name": "Ireland",
        "short": "Ireland",
        "flag": "\U0001F1EE\U0001F1EA",
        "currency": "EUR",
        "central_bank": "European Central Bank",
        "policy_rate_name": "ECB deposit facility rate",
        "inflation_target": 2.0,
        "index": {"name": "ISEQ Overall", "yahoo": "^ISEQ", "stooq": None},
    },
    {
        "iso3": "CAN",
        "iso2": "CA",
        "name": "Canada",
        "short": "Canada",
        "flag": "\U0001F1E8\U0001F1E6",
        "currency": "CAD",
        "central_bank": "Bank of Canada",
        "policy_rate_name": "Overnight rate target",
        "inflation_target": 2.0,
        "index": {"name": "S&P/TSX Composite", "yahoo": "^GSPTSE", "stooq": None},
    },
    {
        "iso3": "NGA",
        "iso2": "NG",
        "name": "Nigeria",
        "short": "Nigeria",
        "flag": "\U0001F1F3\U0001F1EC",
        "currency": "NGN",
        "central_bank": "Central Bank of Nigeria",
        "policy_rate_name": "Monetary Policy Rate (MPR)",
        # The CBN targets a 6-9% band; 7.5 is its midpoint, so "distance from
        # target" does not permanently punish Nigeria for not being the euro area.
        "inflation_target": 7.5,
        "index": {"name": "NGX All-Share", "yahoo": None, "stooq": None},
    },
]

BY_ISO3: dict[str, dict] = {c["iso3"]: c for c in COUNTRIES}
ISO3_CODES: list[str] = [c["iso3"] for c in COUNTRIES]


def get(iso3: str) -> dict:
    try:
        return BY_ISO3[iso3]
    except KeyError:
        raise KeyError(f"unknown country {iso3!r}; expected one of {ISO3_CODES}") from None
