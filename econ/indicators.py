"""The indicator catalogue: what we pull, what it means, and which way is up.

Each entry is one World Bank series. The fields that matter downstream:

  family     which panel of the dashboard it belongs to
  unit       how to format it ("pct", "pct_gdp", "usd", "count", "index", "score", "ratio")
  direction  "up_good" | "down_good" | "target" | "neutral"
             - target: scored on distance from the country's inflation target
             - neutral: shown, never scored (context, not a verdict)
  pulse      True if it feeds the composite economic pulse score
  since      first year the series realistically has data, for honest coverage notes
  source     World Bank database id, when the series is not in the default WDI one
             (the governance indicators live in source 3)

Direction is the whole reason a single "pulse" number is possible: it is what
lets unemployment falling and FDI rising both count as "better".
"""

from __future__ import annotations

INDICATORS: list[dict] = [
    # ---- growth and output -------------------------------------------------
    {
        "code": "NY.GDP.MKTP.KD.ZG", "family": "growth", "pulse": True,
        "label": "GDP growth", "short": "GDP growth",
        "unit": "pct", "direction": "up_good", "since": 1961,
        "note": "Annual % change in real GDP. The headline 'is the economy growing' number.",
    },
    {
        "code": "NY.GDP.PCAP.KD.ZG", "family": "growth", "pulse": True,
        "label": "GDP per capita growth", "short": "GDP/capita growth",
        "unit": "pct", "direction": "up_good", "since": 1961,
        "note": "Growth per person. Strips out the part of GDP growth that is just more people.",
    },
    {
        "code": "NY.GDP.PCAP.CD", "family": "growth", "pulse": False,
        "label": "GDP per capita", "short": "GDP/capita",
        "unit": "usd", "direction": "up_good", "since": 1960,
        "note": "Current US$. Cross-country comparison at market exchange rates.",
    },
    {
        "code": "NY.GDP.MKTP.CD", "family": "growth", "pulse": False,
        "label": "GDP", "short": "GDP",
        "unit": "usd", "direction": "up_good", "since": 1960,
        "note": "Total economy size in current US$.",
    },

    # ---- prices and interest rates ----------------------------------------
    {
        "code": "FP.CPI.TOTL.ZG", "family": "prices", "pulse": True,
        "label": "Inflation (CPI)", "short": "Inflation",
        "unit": "pct", "direction": "target", "since": 1960,
        "note": "Annual consumer price inflation. Scored on distance from the central bank's target, "
                "so deflation counts against a country too.",
    },
    {
        "code": "FR.INR.LEND", "family": "prices", "pulse": False,
        "label": "Lending interest rate", "short": "Lending rate",
        "unit": "pct", "direction": "down_good", "since": 1960,
        "note": "What banks charge prime borrowers. A rough proxy for the cost of credit "
                "where a long policy-rate history is not available.",
    },
    {
        "code": "FR.INR.RINR", "family": "prices", "pulse": False,
        "label": "Real interest rate", "short": "Real rate",
        "unit": "pct", "direction": "neutral", "since": 1960,
        "note": "Lending rate minus inflation. Neither high nor low is straightforwardly good.",
    },
    {
        "code": "FM.LBL.BMNY.ZG", "family": "prices", "pulse": False,
        "label": "Broad money growth", "short": "Money growth",
        "unit": "pct", "direction": "neutral", "since": 1960,
        "note": "How fast the money supply is expanding.",
    },

    # ---- labour ------------------------------------------------------------
    {
        "code": "SL.UEM.TOTL.ZS", "family": "labour", "pulse": True,
        "label": "Unemployment rate", "short": "Unemployment",
        "unit": "pct", "direction": "down_good", "since": 1991,
        "note": "Modelled ILO estimate, so it is comparable across all five markets.",
    },
    {
        "code": "SL.UEM.1524.ZS", "family": "labour", "pulse": False,
        "label": "Youth unemployment", "short": "Youth unemployment",
        "unit": "pct", "direction": "down_good", "since": 1991,
        "note": "Ages 15-24. Usually the first rate to move when hiring freezes.",
    },
    {
        "code": "SL.TLF.CACT.ZS", "family": "labour", "pulse": False,
        "label": "Labour force participation", "short": "Participation",
        "unit": "pct", "direction": "up_good", "since": 1990,
        "note": "Share of working-age people in the labour force.",
    },

    # ---- fiscal ------------------------------------------------------------
    {
        "code": "GC.DOD.TOTL.GD.ZS", "family": "fiscal", "pulse": True,
        "label": "Government debt", "short": "Govt debt",
        "unit": "pct_gdp", "direction": "down_good", "since": 1990,
        "note": "Central government debt as % of GDP. Patchy for Nigeria.",
    },
    {
        "code": "GC.NLD.TOTL.GD.ZS", "family": "fiscal", "pulse": False,
        "label": "Fiscal balance", "short": "Fiscal balance",
        "unit": "pct_gdp", "direction": "up_good", "since": 1990,
        "note": "Net lending (+) or net borrowing (-) as % of GDP.",
    },
    {
        "code": "DT.DOD.DECT.CD", "family": "fiscal", "pulse": False,
        "label": "External debt stocks", "short": "External debt",
        "unit": "usd", "direction": "down_good", "since": 1970,
        "note": "Total external debt. Reported for developing economies, so Nigeria only.",
    },

    # ---- investment flows --------------------------------------------------
    {
        "code": "BX.KLT.DINV.WD.GD.ZS", "family": "investment", "pulse": True,
        "label": "Foreign direct investment", "short": "FDI inflows",
        "unit": "pct_gdp", "direction": "up_good", "since": 1970,
        "note": "Net FDI inflows as % of GDP. Ireland's swings are enormous because of "
                "multinational balance-sheet moves, not factories being built.",
    },
    {
        "code": "BX.KLT.DINV.CD.WD", "family": "investment", "pulse": False,
        "label": "FDI inflows (US$)", "short": "FDI (US$)",
        "unit": "usd", "direction": "up_good", "since": 1970,
        "note": "The same flow in dollars rather than as a share of GDP.",
    },
    {
        "code": "BX.PEF.TOTL.CD.WD", "family": "investment", "pulse": False,
        "label": "Portfolio equity inflows", "short": "Portfolio equity",
        "unit": "usd", "direction": "up_good", "since": 1970,
        "note": "Net foreign buying of listed shares. Hot money: it leaves fast.",
    },
    {
        "code": "NE.GDI.TOTL.ZS", "family": "investment", "pulse": True,
        "label": "Gross capital formation", "short": "Investment",
        "unit": "pct_gdp", "direction": "up_good", "since": 1960,
        "note": "Domestic investment as % of GDP. What the economy spends on its own future.",
    },

    # ---- markets and business formation ------------------------------------
    {
        "code": "CM.MKT.LCAP.GD.ZS", "family": "markets", "pulse": False,
        "label": "Stock market capitalisation", "short": "Market cap",
        "unit": "pct_gdp", "direction": "up_good", "since": 1975,
        "note": "Listed domestic companies' market value as % of GDP. The long-run read on "
                "whether the stock market is growing relative to the economy.",
    },
    {
        "code": "CM.MKT.LDOM.NO", "family": "markets", "pulse": False,
        "label": "Listed domestic companies", "short": "Listed companies",
        "unit": "count", "direction": "up_good", "since": 1975,
        "note": "Company count on the domestic exchange. The closest long-run proxy for "
                "IPOs net of delistings: a falling count means take-privates are outpacing floats.",
    },
    {
        "code": "CM.MKT.TRAD.GD.ZS", "family": "markets", "pulse": False,
        "label": "Stocks traded", "short": "Turnover",
        "unit": "pct_gdp", "direction": "neutral", "since": 1975,
        "note": "Total value traded as % of GDP. High can mean liquidity or panic.",
    },
    {
        "code": "IC.BUS.NDNS.ZS", "family": "markets", "pulse": False,
        "label": "New business density", "short": "New business density",
        "unit": "ratio", "direction": "up_good", "since": 2006,
        "note": "New limited-liability companies per 1,000 working-age adults. The best "
                "cross-country business-formation series, but it only starts in 2006.",
    },
    {
        "code": "IC.BUS.NREG", "family": "markets", "pulse": False,
        "label": "New businesses registered", "short": "New businesses",
        "unit": "count", "direction": "up_good", "since": 2006,
        "note": "Absolute count of new company registrations.",
    },

    # ---- external ----------------------------------------------------------
    {
        "code": "BN.CAB.XOKA.GD.ZS", "family": "external", "pulse": True,
        "label": "Current account balance", "short": "Current account",
        "unit": "pct_gdp", "direction": "up_good", "since": 1960,
        "note": "Surplus (+) or deficit (-) as % of GDP. Whether the country is paying its own way.",
    },
    {
        "code": "NE.EXP.GNFS.ZS", "family": "external", "pulse": False,
        "label": "Exports", "short": "Exports",
        "unit": "pct_gdp", "direction": "up_good", "since": 1960,
        "note": "Exports of goods and services as % of GDP.",
    },
    {
        "code": "NE.TRD.GNFS.ZS", "family": "external", "pulse": False,
        "label": "Trade openness", "short": "Trade",
        "unit": "pct_gdp", "direction": "neutral", "since": 1960,
        "note": "Exports plus imports as % of GDP.",
    },
    {
        "code": "FI.RES.TOTL.MO", "family": "external", "pulse": False,
        "label": "Reserves", "short": "Reserves",
        "unit": "months", "direction": "up_good", "since": 1960,
        "note": "Import cover in months. Below three months is the classic warning line.",
    },
    {
        "code": "PA.NUS.FCRF", "family": "external", "pulse": False,
        "label": "Exchange rate vs US$", "short": "FX rate",
        "unit": "rate", "direction": "neutral", "since": 1960,
        "note": "Local currency units per US dollar, annual average. Rising means depreciation.",
    },

    # ---- governance (Worldwide Governance Indicators, 1996 onwards) ---------
    {
        "code": "PV.EST", "family": "governance", "pulse": False, "source": 3,
        "label": "Political stability", "short": "Political stability",
        "unit": "score", "direction": "up_good", "since": 1996,
        "note": "WGI estimate, roughly -2.5 to +2.5. Absence of violence and disorderly power transfer.",
    },
    {
        "code": "GE.EST", "family": "governance", "pulse": False, "source": 3,
        "label": "Government effectiveness", "short": "Govt effectiveness",
        "unit": "score", "direction": "up_good", "since": 1996,
        "note": "Quality of public services and policy implementation.",
    },
    {
        "code": "RQ.EST", "family": "governance", "pulse": False, "source": 3,
        "label": "Regulatory quality", "short": "Regulatory quality",
        "unit": "score", "direction": "up_good", "since": 1996,
        "note": "Whether policy lets the private sector function.",
    },
    {
        "code": "RL.EST", "family": "governance", "pulse": False, "source": 3,
        "label": "Rule of law", "short": "Rule of law",
        "unit": "score", "direction": "up_good", "since": 1996,
        "note": "Contract enforcement, property rights, courts.",
    },
    {
        "code": "CC.EST", "family": "governance", "pulse": False, "source": 3,
        "label": "Control of corruption", "short": "Control of corruption",
        "unit": "score", "direction": "up_good", "since": 1996,
        "note": "How far public power is exercised for private gain.",
    },
    {
        "code": "VA.EST", "family": "governance", "pulse": False, "source": 3,
        "label": "Voice and accountability", "short": "Voice & accountability",
        "unit": "score", "direction": "up_good", "since": 1996,
        "note": "Free expression, free media, ability to select a government.",
    },

    # ---- context -----------------------------------------------------------
    {
        "code": "SP.POP.TOTL", "family": "context", "pulse": False,
        "label": "Population", "short": "Population",
        "unit": "count", "direction": "neutral", "since": 1960,
        "note": "Used to put the absolute numbers in proportion.",
    },
]

FAMILIES: list[dict] = [
    {"id": "growth", "label": "Growth & output"},
    {"id": "prices", "label": "Prices & rates"},
    {"id": "labour", "label": "Labour market"},
    {"id": "fiscal", "label": "Government & debt"},
    {"id": "investment", "label": "Investment flows"},
    {"id": "markets", "label": "Markets & business formation"},
    {"id": "external", "label": "Trade & external position"},
    {"id": "governance", "label": "Political & institutional"},
    {"id": "context", "label": "Context"},
]

BY_CODE: dict[str, dict] = {i["code"]: i for i in INDICATORS}
CODES: list[str] = [i["code"] for i in INDICATORS]
PULSE_CODES: list[str] = [i["code"] for i in INDICATORS if i["pulse"]]


def get(code: str) -> dict:
    try:
        return BY_CODE[code]
    except KeyError:
        raise KeyError(f"unknown indicator {code!r}") from None
